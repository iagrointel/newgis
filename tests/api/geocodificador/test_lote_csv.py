"""Item L2-11-a-geocodificacao-csv: portão de pronto medido com 1.000 endereços do CNEFE de Boa Vista/RR (dado
aberto, com coordenada conhecida — a mesma base de RR que o L2-11-b instalou, `plat.geo_endereco`). Sobe um
worker temporário em subprocesso (mesmo padrão de `tests/api/jobs/conftest.py:WorkerExtra`, mas autocontido aqui
porque `tests/` não é pacote importável) para rodar o job `geocodificador.lote_csv` de ponta a ponta: CSV ->
mapeamento -> lote geocodificado -> camada nova com colunas de qualidade -> tela de revisão dos pendentes ->
arrasto manual -> re-geocodificar só os pendentes."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from app.geocodificador import motor

ROOT = Path(__file__).resolve().parents[3]
PORTA_WORKER = 18162
FINAIS = ("concluido", "falhou", "cancelado")


def _amostra_boa_vista(cur, n: int):
    """1.000 endereços de Boa Vista/RR com número e coordenada conhecida (CNEFE, dado aberto)."""
    cur.execute(
        "SELECT e.cod_unico_endereco, e.tipo_logradouro, e.nome_logradouro, e.numero, e.cep, "
        "  m.nome AS municipio, u.sigla AS uf, e.lat, e.lon, e.cod_municipio "
        "FROM plat.geo_endereco e JOIN plat.geo_municipio m ON m.cod = e.cod_municipio "
        "  JOIN plat.geo_uf u ON u.cod = m.cod_uf "
        "WHERE e.numero IS NOT NULL AND e.nome_logradouro <> 'SEM DENOMINACAO' AND m.nome = 'Boa Vista' "
        "  AND e.cod_uf = 14 "
        "ORDER BY e.cod_unico_endereco LIMIT %s",
        (n,),
    )
    return cur.fetchall()


@pytest.fixture(scope="module")
def amostra_1000(env):
    """Conexão própria (não `conexao_plat_app`, que é escopo de função): a amostra é lida uma vez por módulo."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            linhas = _amostra_boa_vista(cur, 1000)
    finally:
        con.rollback()
        con.close()
    assert len(linhas) >= 1000, "menos de 1.000 endereços elegíveis em Boa Vista/RR (RR precisa estar instalada)"
    return linhas


def _csv_limpo(amostra) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["logradouro", "numero", "municipio", "uf"])
    for r in amostra:
        via = f"{r['tipo_logradouro']} {r['nome_logradouro']}".strip()
        w.writerow([via, r["numero"], r["municipio"], r["uf"]])
    return buf.getvalue()


def _csv_ruidoso(amostra) -> str:
    """Refutação do item: abreviação (R., Av.), sem acento (o CNEFE já é ASCII), CEP errado e número
    inexistente — nenhum desses pode virar ponto no centroide do município sem marca 'centroide'."""
    inverso = {"RUA": "R.", "AVENIDA": "Av.", "TRAVESSA": "Tv."}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["logradouro", "numero", "municipio", "uf", "cep"])
    for i, r in enumerate(amostra):
        tipo = inverso.get(r["tipo_logradouro"], r["tipo_logradouro"])
        via = f"{tipo} {r['nome_logradouro']}"
        if i % 3 == 0:
            numero = 999999 + i  # número inexistente
        else:
            numero = r["numero"]
        cep = "00000000" if i % 4 == 0 else (r["cep"] or "")
        w.writerow([via, numero, r["municipio"], r["uf"], cep])
    return buf.getvalue()


class WorkerTemporario:
    """Sobe `python -m app.jobs.worker` em subprocesso com o ambiente da trilha, espera /saude e mata pelo PID
    no fim — nunca `systemctl`/`pkill` (regra do brief comum)."""

    def __init__(self, env: dict[str, str], porta: int = PORTA_WORKER):
        ambiente = dict(os.environ)
        ambiente.update({k: v for k, v in env.items() if v is not None})
        ambiente.update({
            "PYTHONNOUSERSITE": "1",
            "PLAT_WORKER_NOME": "teste-lote-csv",
            "PLAT_WORKER_PROCESSOS": "1",
            "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}",
        })
        # em worktree o `.git` é um arquivo-ponteiro (`gitdir: ...`), não um diretório: `app.versao._sha_do_git`
        # (ADR 0001 seção 7, lê sem subprocesso) não resolve esse caso e o worker recusa subir sem sha — achado
        # deste item, não corrigido aqui (arquivo compartilhado com a árvore principal); contorno local só do
        # ambiente do worker de teste.
        ambiente.setdefault(
            "PLAT_GIT_SHA",
            subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
            .stdout.strip(),
        )
        self.porta = porta
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        ok = False
        for _ in range(100):
            try:
                self.saude()
                ok = True
                break
            except OSError:
                time.sleep(0.2)
        if not ok:
            self.proc.kill()
            pytest.fail(f"worker temporário não respondeu em /saude (:{porta}) em 20 s")

    def saude(self) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/saude", timeout=1) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def parar(self) -> None:
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture(scope="module")
def worker_temporario(env):
    w = WorkerTemporario(env)
    yield w
    w.parar()


def _criar_job(sessao, csv_texto: str, mapeamento: dict, titulo: str, limiar_pendente: float = 50.0) -> dict:
    r = sessao.post("/api/jobs", json={
        "tipo": "geocodificador.lote_csv",
        "parametros": {
            "titulo": titulo, "csv_texto": csv_texto, "mapeamento": mapeamento,
            "limiar_pendente": limiar_pendente,
        },
    })
    assert r.status_code == 201, r.text
    return r.json()


def _esperar(sessao, job_id: str, timeout: float = 120) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in FINAIS:
            return ultimo
        time.sleep(0.3)
    pytest.fail(f"job {job_id} não terminou em {timeout} s: {json.dumps(ultimo)[:800]}")


MAPEAMENTO = {"logradouro": "logradouro", "numero": "numero", "municipio": "municipio", "uf": "uf"}


def test_1000_enderecos_boa_vista_85pct_numero_exato_0pct_fora_municipio(
    worker_temporario, sessao_a, amostra_1000, conexao_plat_app, medida
):
    """Cláusula literal do portão: teste api com 1.000 endereços do CNEFE de 1 município (RR/Boa Vista, dado
    aberto com coordenada conhecida), ≥85% com acerto 'numero_exato' a ≤50 m e 0% fora do município."""
    csv_texto = _csv_limpo(amostra_1000)
    t0 = time.monotonic()
    job = _criar_job(sessao_a, csv_texto, MAPEAMENTO, "teste L2-11-a — 1000 Boa Vista")
    resultado = _esperar(sessao_a, job["id"])
    duracao_s = time.monotonic() - t0
    assert resultado["estado"] == "concluido", resultado
    item_id = resultado["resultado"]["item_id"]

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
        item = cur.fetchone()
        schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
        cur.execute(
            f'SELECT c.linha_origem, c.tipo_acerto, c.pendente, c.cod_municipio, '
            f'  ST_X(c.geom) AS lon, ST_Y(c.geom) AS lat '
            f'FROM "{schema}"."{tabela}" c ORDER BY c.linha_origem'
        )
        pontos = cur.fetchall()

    assert len(pontos) == len(amostra_1000), "a camada tem que ter uma linha por endereço de entrada"
    cod_boa_vista = amostra_1000[0]["cod_municipio"]

    numero_exato_perto = 0
    fora_municipio = 0
    for ponto, esperado in zip(pontos, amostra_1000):
        if ponto["lon"] is not None and ponto["cod_municipio"] is not None:
            if ponto["cod_municipio"] != cod_boa_vista:
                fora_municipio += 1
            d = motor.distancia_m(ponto["lon"], ponto["lat"], esperado["lon"], esperado["lat"])
            if ponto["tipo_acerto"] == "numero_exato" and d <= 50:
                numero_exato_perto += 1

    pct_numero_exato = numero_exato_perto / len(amostra_1000) * 100
    pct_fora_municipio = fora_municipio / len(amostra_1000) * 100

    m = medida("L2-11-a-geocodificacao-csv")
    nome_teste = "test_1000_enderecos_boa_vista_85pct_numero_exato_0pct_fora_municipio"
    m("lote_numero_exato_50m", round(pct_numero_exato, 1), "%", nome_teste)
    m("lote_fora_municipio", round(pct_fora_municipio, 1), "%", nome_teste)
    m("lote_1000_enderecos_duracao_s", round(duracao_s, 2), "s", nome_teste)
    m("lote_1000_enderecos_job_duracao_s", resultado["resultado"]["duracao_s"], "s", nome_teste)

    assert pct_numero_exato >= 85, f"acerto numero_exato a <=50m = {pct_numero_exato:.1f}%, abaixo do portão (85%)"
    assert pct_fora_municipio == 0, f"{pct_fora_municipio:.1f}% dos pontos caíram fora do município"

    return item_id


def test_pendentes_aparecem_na_tela_de_revisao_e_arrasto_grava_origem_manual(worker_temporario, sessao_a, amostra_1000):
    """Cláusula: pendentes aparecem na tela de revisão e o arrasto grava a coordenada com origem 'manual'."""
    # lote com números inexistentes garante pendência real (sem depender de a base falhar sozinha)
    amostra = amostra_1000[:50]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["logradouro", "numero", "municipio", "uf"])
    for r in amostra:
        via = f"{r['tipo_logradouro']} {r['nome_logradouro']}".strip()
        w.writerow([via, 900000, r["municipio"], r["uf"]])  # número que não existe -> pendente
    job = _criar_job(sessao_a, buf.getvalue(), MAPEAMENTO, "teste L2-11-a — pendentes", limiar_pendente=95)
    resultado = _esperar(sessao_a, job["id"])
    assert resultado["estado"] == "concluido", resultado
    item_id = resultado["resultado"]["item_id"]

    r = sessao_a.get(f"/api/geocodificador/lote/{item_id}/pendentes", params={"limite": 10})
    assert r.status_code == 200, r.text
    pendentes = r.json()["itens"]
    assert r.json()["total"] > 0, "esperava pendentes com número inexistente"
    assert len(pendentes) > 0

    fid = pendentes[0]["fid"]
    lon_manual, lat_manual = -60.6733, 2.8235  # ponto conhecido dentro de Boa Vista/RR
    r = sessao_a.patch(f"/api/geocodificador/lote/{item_id}/pendentes/{fid}",
                        json={"lon": lon_manual, "lat": lat_manual})
    assert r.status_code == 200, r.text
    assert r.json()["origem"] == "manual"

    r = sessao_a.get(f"/api/geocodificador/lote/{item_id}/pendentes", params={"limite": 200})
    assert all(p["fid"] != fid for p in r.json()["itens"]), "o ponto corrigido não pode continuar pendente"


def test_regeocodificar_so_toca_pendentes(worker_temporario, sessao_a, amostra_1000):
    """Cláusula: re-geocodificar só os pendentes — um ponto já corrigido à mão nunca é tocado."""
    amostra = amostra_1000[:20]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["logradouro", "numero", "municipio", "uf"])
    for r in amostra:
        via = f"{r['tipo_logradouro']} {r['nome_logradouro']}".strip()
        w.writerow([via, 900001, r["municipio"], r["uf"]])
    job = _criar_job(sessao_a, buf.getvalue(), MAPEAMENTO, "teste L2-11-a — regeocodificar", limiar_pendente=95)
    resultado = _esperar(sessao_a, job["id"])
    item_id = resultado["resultado"]["item_id"]

    r = sessao_a.get(f"/api/geocodificador/lote/{item_id}/pendentes", params={"limite": 5})
    fid_manual = r.json()["itens"][0]["fid"]
    r = sessao_a.patch(f"/api/geocodificador/lote/{item_id}/pendentes/{fid_manual}", json={"lon": -60.7, "lat": 2.8})
    assert r.status_code == 200, r.text

    r = sessao_a.post(f"/api/geocodificador/lote/{item_id}/regeocodificar", json={})
    assert r.status_code == 200, r.text

    r = sessao_a.get(f"/api/geocodificador/lote/{item_id}/pendentes", params={"limite": 200})
    assert all(p["fid"] != fid_manual for p in r.json()["itens"]), \
        "regeocodificar não pode reintroduzir na fila um ponto já corrigido à mão"


def test_adversario_abreviacao_sem_acento_cep_errado_numero_inexistente(worker_temporario, sessao_a, amostra_1000, conexao_plat_app):
    """Refutação exigida pelo item: endereços com abreviação (R., Av.), sem acento, CEP errado e número
    inexistente — nenhum ponto pode cair no centroide do município sem estar marcado como tal."""
    amostra = amostra_1000[:200]
    csv_ruidoso = _csv_ruidoso(amostra)
    job = _criar_job(sessao_a, csv_ruidoso, {**MAPEAMENTO, "cep": "cep"}, "teste L2-11-a — adversario")
    resultado = _esperar(sessao_a, job["id"])
    assert resultado["estado"] == "concluido", resultado
    item_id = resultado["resultado"]["item_id"]

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (item_id,))
        item = cur.fetchone()
        schema, tabela = item["dados"]["schema"], item["dados"]["tabela"]
        cur.execute(f'SELECT tipo_acerto, avisos, pendente, ST_X(geom) AS lon, ST_Y(geom) AS lat, cod_municipio '
                    f'FROM "{schema}"."{tabela}"')
        pontos = cur.fetchall()

    with conexao_plat_app.cursor() as cur3:
        cur3.execute("SELECT centro_lon AS lon, centro_lat AS lat FROM plat.geo_municipio WHERE cod = %s",
                      (amostra[0]["cod_municipio"],))
        centroide = cur3.fetchone()

    for p in pontos:
        if p["lon"] is None or centroide["lon"] is None:
            continue
        no_centroide = abs(p["lon"] - centroide["lon"]) < 1e-6 and abs(p["lat"] - centroide["lat"]) < 1e-6
        if no_centroide:
            assert p["tipo_acerto"] == "aproximado_no_municipio", (
                "ponto caiu no centroide do município sem estar marcado como tal: "
                f"tipo_acerto={p['tipo_acerto']!r}"
            )
    # a base ruidosa tem de gerar alguma pendência real (número inexistente não some silenciosamente)
    assert any(p["pendente"] for p in pontos), "endereços com número inexistente deveriam gerar pendência"
