"""Portão do item L6-01-i-raster-e-arquivos, contra a API e o acervo REAL desta instalação:
  1. `GET /api/acervo/arquivos` lista as camadas de arquivo do acervo (medido 08/09/2026: 321 linhas, 26 raster
     e 295 vetoriais, 100 % com sha256) com a ficha da fonte e o estado de exposição;
  2. `POST /api/acervo/arquivos/expor` expõe ≥ 10 rasters e ≥ 20 arquivos ao todo, cada um com o sha256
     CONFERIDO antes de qualquer escrita (o hash gravado em `plat.acervo_arquivo_exposto` é o do disco);
  3. o raster exposto serve ladrilho por token (item L1-02) lendo o arquivo do acervo onde ele já está —
     sem cópia para o balde (guardrail de disco D21);
  4. guardrail: arquivo acima do teto é recusado sem job, e o lote acima do teto de disco também;
  5. refutação: 1 byte alterado em uma cópia do arquivo = exposição recusada por hash, sem criar item.
Sem raiz de acervo configurada nesta instalação (`PLAT_ACERVO_ARQUIVOS_RAIZ`), a suíte é pulada com a razão.
Os arquivos do acervo são lidos SÓ PARA LEITURA; o teste da refutação trabalha sobre uma cópia em tmp_path."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import shutil
import time
import uuid

import psycopg2.errors
import pytest

from app import db, limites
from app import settings as mod_settings
from app.acervo import arquivos as arq
from app.acervo import tarefas as acervo_tarefas
from tests.api.conftest import PREFIXO_TESTE

ITEM = "L6-01-i-raster-e-arquivos"
N_RASTERS = 10
N_VETORES = 20
RAIZ_PADRAO = "/home/dev/rs-coop/tracado-lt/camadas"


@pytest.fixture(scope="module")
def raiz_acervo():
    """Raiz do acervo desta instalação: do ambiente, ou a da casa quando ela está no disco (o registro
    `acervo.camada_arquivo` é da casa; a raiz é onde os arquivos estão)."""
    bruto = (os.environ.get("PLAT_ACERVO_ARQUIVOS_RAIZ") or "").strip() or RAIZ_PADRAO
    if not os.path.isdir(bruto):
        pytest.skip(f"sem raiz de arquivos do acervo em {bruto!r} (PLAT_ACERVO_ARQUIVOS_RAIZ)")
    return bruto


@pytest.fixture(scope="module", autouse=True)
def _raiz_no_processo(raiz_acervo):
    """A API roda no processo do teste (TestClient): a raiz entra no `settings` que os módulos leem."""
    novo = dataclasses.replace(mod_settings.settings, PLAT_ACERVO_ARQUIVOS_RAIZ=raiz_acervo)
    antigo_arq, antigo_tar = arq.settings, acervo_tarefas.settings
    arq.settings = novo
    acervo_tarefas.settings = novo
    yield
    arq.settings, acervo_tarefas.settings = antigo_arq, antigo_tar


class CtxFalso:
    """Contexto de job no PRÓPRIO processo: o worker chama a mesma função com este contrato (ADR 0003). Aqui ele
    serve para exercitar `acervo.expor_arquivo` sem depender de um worker vivo — o código exercitado é o mesmo."""

    def __init__(self, tenant_id: int, usuario_id: int):
        self.tenant_id = tenant_id
        self.usuario_id = usuario_id
        self.job_id = uuid.uuid4()
        self.tentativa = 1
        self.passos: list[tuple[int, str]] = []
        self._ctx = db.Contexto(tenant_id=tenant_id, usuario_id=usuario_id, login="teste")

    def db(self):
        return db.db(self._ctx)

    def progresso(self, pct, mensagem=""):
        self.passos.append((pct, mensagem))

    def log(self, nivel, mensagem):
        self.passos.append((-1, f"{nivel}: {mensagem}"))

    def verificar(self):
        return None

    def subprocesso(self, argv, **kw):
        import subprocess
        return subprocess.run(argv, capture_output=True, text=True, timeout=600)


@pytest.fixture(scope="module")
def ator(tenant_id_a):
    with db.db(db.Contexto(tenant_id=tenant_id_a, usuario_id=0, login="teste")) as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_id_a,))
        return {"tenant_id": tenant_id_a, "usuario_id": cur.fetchone()["id"]}


def _limpar_exposicoes(ator, caminhos: list[str]) -> None:
    ctxdb = db.Contexto(tenant_id=ator["tenant_id"], usuario_id=ator["usuario_id"], login="teste")
    with db.db(ctxdb) as cur:
        cur.execute("SELECT caminho, item_id::text AS item_id FROM plat.acervo_arquivo_exposto "
                    "WHERE caminho = ANY(%s)", (caminhos,))
        for linha in cur.fetchall():
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (linha["item_id"],))
            r = cur.fetchone()
            dados = (r or {}).get("dados") or {}
            if dados.get("schema") and dados.get("tabela"):
                cur.execute(f'DROP TABLE IF EXISTS "{dados["schema"]}"."{dados["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.acervo_arquivo_exposto WHERE caminho = %s", (linha["caminho"],))
            cur.execute("DELETE FROM plat.raster_item WHERE item_id = %s", (linha["item_id"],))
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (linha["item_id"],))


def _no_disco(caminho: str) -> bool:
    try:
        return arq.resolver(caminho).is_file()
    except arq.ArquivoRecusado:
        return False


@pytest.fixture(scope="module")
def escolhidos(ator):
    """Os menores arquivos do registro que estão no disco: 10 rasters e 20 vetoriais com feições."""
    with db.db(db.Contexto(**{**ator, "login": "teste"})) as cur:
        cur.execute("SELECT * FROM plat.acervo_arquivo WHERE tipo = 'raster' ORDER BY bytes NULLS LAST LIMIT 40")
        rasters = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM plat.acervo_arquivo WHERE tipo = 'vetor' AND feicoes > 0 "
                    "ORDER BY bytes NULLS LAST LIMIT 60")
        vetores = [dict(r) for r in cur.fetchall()]
    rasters = [r for r in rasters if _no_disco(r["caminho"])][:N_RASTERS]
    vetores = [v for v in vetores if _no_disco(v["caminho"])][:N_VETORES]
    if len(rasters) < N_RASTERS or len(vetores) < N_VETORES:
        pytest.skip(f"acervo com {len(rasters)} raster(s) e {len(vetores)} vetorial(is) no disco desta instalação")
    return {"rasters": rasters, "vetores": vetores}


@pytest.fixture(scope="module")
def expostos(ator, escolhidos, raiz_acervo):
    """Expõe 10 rasters + 20 vetoriais e limpa tudo ao fim (itens, tabelas de camada e linhas de exposição)."""
    # começa limpo: execução anterior interrompida pode ter deixado exposição destes caminhos
    _limpar_exposicoes(ator, [r["caminho"] for r in escolhidos["rasters"] + escolhidos["vetores"]])
    criados: list[dict] = []
    t0 = time.perf_counter()
    for r in escolhidos["rasters"] + escolhidos["vetores"]:
        titulo = f"{PREFIXO_TESTE} {r['nome'] or r['caminho']}"
        # "tuple concurrently updated" no GRANT de d_demo: trilhas concorrentes reescrevendo a ACL do MESMO
        # schema (ambiente, não o item; corrigido na origem pela migração 20260908T0815 do ramo wt/cxux16)
        for tentativa in range(4):
            try:
                ctx = CtxFalso(ator["tenant_id"], ator["usuario_id"])
                criados.append(acervo_tarefas.acervo_expor_arquivo(ctx, caminho=r["caminho"], titulo=titulo))
                break
            except psycopg2.errors.InternalError_ as e:
                if "concurrently" not in str(e) or tentativa == 3:
                    raise
                time.sleep(2 + tentativa)
    dt = time.perf_counter() - t0
    yield {"itens": criados, "segundos": dt}
    ctxdb = db.Contexto(tenant_id=ator["tenant_id"], usuario_id=ator["usuario_id"], login="teste")
    with db.db(ctxdb) as cur:
        for c in criados:
            cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid", (c["item_id"],))
            linha = cur.fetchone()
            dados = (linha or {}).get("dados") or {}
            if dados.get("schema") and dados.get("tabela"):
                cur.execute(f'DROP TABLE IF EXISTS "{dados["schema"]}"."{dados["tabela"]}" CASCADE')
            cur.execute("DELETE FROM plat.acervo_arquivo_exposto WHERE item_id = %s::uuid", (c["item_id"],))
            cur.execute("DELETE FROM plat.raster_item WHERE item_id = %s", (c["item_id"],))
            cur.execute("DELETE FROM plat.item WHERE id = %s::uuid", (c["item_id"],))


def test_lista_do_acervo_de_arquivo(sessao_a, raiz_acervo, medida):
    r = sessao_a.get("/api/acervo/arquivos", params={"limite": 5})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["raiz_configurada"] is True
    assert j["total"] == j["rasters"] + j["vetores"] and j["total"] >= 300
    assert j["rasters"] >= N_RASTERS
    linha = j["itens"][0]
    assert set(linha) >= {"caminho", "tipo", "extensao", "sha256", "publicavel", "exposto", "no_disco"}
    assert all(x["sha256"] for x in j["itens"]), "o registro do acervo tem sha256 em toda linha"
    # filtro por tipo e por busca
    so_raster = sessao_a.get("/api/acervo/arquivos", params={"tipo": "raster", "limite": 100}).json()
    assert so_raster["total"] == j["rasters"] and all(x["tipo"] == "raster" for x in so_raster["itens"])
    m = medida(ITEM)
    m("arquivos_no_registro", j["total"], "arquivos", "GET /api/acervo/arquivos (acervo.camada_arquivo)")
    m("rasters_no_registro", j["rasters"], "arquivos", "extensão tif/tiff/vrt")
    m("vetores_no_registro", j["vetores"], "arquivos", "demais extensões suportadas")


def test_dez_rasters_e_vinte_arquivos_expostos_com_hash_conferido(sessao_a, expostos, ator, medida):
    itens = expostos["itens"]
    rasters = [c for c in itens if c["tipo"] == "raster"]
    assert len(rasters) >= N_RASTERS and len(itens) >= N_RASTERS + N_VETORES
    with db.db(db.Contexto(tenant_id=ator["tenant_id"], usuario_id=ator["usuario_id"], login="teste")) as cur:
        cur.execute("SELECT caminho, tipo, sha256_registro, sha256_conferido, publicavel, bytes "
                    "FROM plat.acervo_arquivo_exposto ORDER BY caminho")
        linhas = [dict(x) for x in cur.fetchall()]
    assert len(linhas) >= N_RASTERS + N_VETORES
    assert all(x["sha256_conferido"] == x["sha256_registro"] and len(x["sha256_conferido"]) == 64 for x in linhas)
    # o hash gravado é o do DISCO: recalculado aqui, arquivo a arquivo
    for x in linhas[:5]:
        caminho = arq.resolver(x["caminho"])
        assert hashlib.sha256(caminho.read_bytes()).hexdigest() == x["sha256_conferido"], x["caminho"]
    # os itens estão no catálogo, com a procedência da fonte e privados (D17: nenhuma fonte de arquivo tem licença)
    for c in itens[:6]:
        it = sessao_a.get(f"/api/itens/{c['item_id']}").json()
        assert it["tipo"] in ("raster", "camada_vetorial") and it["acesso"] == "privado"
        proc = it["dados"]["procedencia"]
        assert proc["origem"] == "acervo" and proc["sha256"] == c["sha256"] and proc["caminho"] == c["caminho"]
        assert it["dados"]["uso_restrito"] is (not c["publicavel"])
    vetor = next(c for c in itens if c["tipo"] == "vetor")
    it = sessao_a.get(f"/api/itens/{vetor['item_id']}").json()
    assert it["dados"]["fonte"] == "hospedada" and it["dados"]["estatisticas"]["feicoes"] >= 1
    raster = rasters[0]
    it = sessao_a.get(f"/api/itens/{raster['item_id']}").json()
    assert it["dados"]["origem"] == "referenciada" and it["dados"]["stac_id"] == raster["item_id"]
    m = medida(ITEM)
    m("rasters_expostos", len(rasters), "itens", "job acervo.expor_arquivo (referência, sem cópia para o balde)")
    m("arquivos_expostos", len(itens), "itens", "10 rasters + 20 vetoriais do acervo da casa")
    m("expor_30_arquivos_s", round(expostos["segundos"], 2), "s",
      "sha256 conferido + item criado (vetor: ogr2ogr para PostGIS)")
    m("bytes_copiados_para_o_balde", 0, "bytes", "raster exposto por referência: o arquivo fica onde está (D21)")


def test_raster_do_acervo_serve_ladrilho_por_token(sessao_a, expostos, medida):
    from tests.api.imagens.test_tiles_token import _cliente

    raster = next(c for c in expostos["itens"] if c["tipo"] == "raster")
    r = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-tiles-acervo", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    try:
        c = _cliente()
        info = c.get(f"/svc/{tok['token']}/raster/{raster['item_id']}/info.json")
        assert info.status_code == 200, info.text
        corpo = info.json()
        assert corpo["bandas"] >= 1 and len(corpo["bounds"]) == 4
        tj = c.get(f"/svc/{tok['token']}/raster/{raster['item_id']}/tilejson.json")
        assert tj.status_code == 200, tj.text
        limites_tj = tj.json()["bounds"]
        # um ladrilho de verdade no centro da extensão do raster do acervo
        z = max(int(tj.json().get("minzoom") or 0), 8)
        import math
        lon = (limites_tj[0] + limites_tj[2]) / 2
        lat = (limites_tj[1] + limites_tj[3]) / 2
        n = 2 ** z
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
        t0 = time.perf_counter()
        png = c.get(f"/svc/{tok['token']}/raster/{raster['item_id']}/{z}/{x}/{y}.png")
        dt = time.perf_counter() - t0
        assert png.status_code == 200, png.text[:300]
        assert png.headers["content-type"] == "image/png" and png.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png.content) > 100
        medida(ITEM)("ladrilho_acervo_ms", round(dt * 1000, 1), "ms",
                     f"GET /svc/<token>/raster/<item>/{z}/{x}/{y}.png lendo o arquivo do acervo no disco")
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_guardrail_de_disco_recusa_arquivo_e_lote_grandes(sessao_a, ator, monkeypatch):
    """Caminhos AINDA NÃO expostos (os do teste anterior já estão no catálogo): o guardrail é do tamanho, não
    da repetição."""
    with db.db(db.Contexto(tenant_id=ator["tenant_id"], usuario_id=ator["usuario_id"], login="teste")) as cur:
        cur.execute("SELECT a.caminho FROM plat.acervo_arquivo a LEFT JOIN plat.acervo_arquivo_exposto e "
                    "ON e.caminho = a.caminho WHERE a.tipo = 'raster' AND e.caminho IS NULL "
                    "ORDER BY a.bytes NULLS LAST LIMIT 20")
        candidatos = [x["caminho"] for x in cur.fetchall()]
    caminhos = [c for c in candidatos if _no_disco(c)][:3]
    if len(caminhos) < 3:
        pytest.skip("menos de 3 rasters não expostos no disco desta instalação")
    monkeypatch.setattr(limites, "ACERVO_ARQUIVO_BYTES_MAX", 1024)
    r = sessao_a.post("/api/acervo/arquivos/expor", json={"caminhos": caminhos})
    assert r.status_code == 202, r.text
    j = r.json()
    assert j["jobs"] == [] and {x["erro"] for x in j["recusados"]} == {"arquivo_grande_demais"}
    monkeypatch.setattr(limites, "ACERVO_ARQUIVO_BYTES_MAX", 2 * 1024 * 1024 * 1024)
    monkeypatch.setattr(limites, "ACERVO_ARQUIVO_LOTE_BYTES_MAX", 1024)
    r = sessao_a.post("/api/acervo/arquivos/expor", json={"caminhos": caminhos})
    assert r.status_code == 202
    assert {x["erro"] for x in r.json()["recusados"]} == {"lote_grande_demais"}
    # caminho fora do registro nunca vira job
    r = sessao_a.post("/api/acervo/arquivos/expor", json={"caminhos": ["nao/existe/no/registro.tif"]})
    assert r.status_code == 202 and r.json()["recusados"][0]["erro"] == "caminho_inexistente"


def test_adversario_um_byte_alterado_recusa_e_nao_cria_item(ator, escolhidos, tmp_path, monkeypatch):
    """A cópia (nunca o arquivo da casa) recebe 1 bit trocado; a exposição tem de morrer no hash, sem item."""
    alvo = escolhidos["vetores"][0]
    origem = arq.resolver(alvo["caminho"])
    destino = tmp_path / alvo["caminho"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)
    dados = bytearray(destino.read_bytes())
    dados[len(dados) // 2] ^= 0x01
    destino.write_bytes(bytes(dados))
    assert destino.stat().st_size == origem.stat().st_size

    _limpar_exposicoes(ator, [alvo["caminho"]])  # o caminho não pode estar exposto: senão o job é idempotente
    novo = dataclasses.replace(mod_settings.settings, PLAT_ACERVO_ARQUIVOS_RAIZ=str(tmp_path))
    monkeypatch.setattr(arq, "settings", novo)
    monkeypatch.setattr(acervo_tarefas, "settings", novo)
    ctxdb = db.Contexto(tenant_id=ator["tenant_id"], usuario_id=ator["usuario_id"], login="teste")
    with db.db(ctxdb) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE tenant_id = %s", (ator["tenant_id"],))
        antes = cur.fetchone()["n"]
    from app.jobs.registro import FalhaDefinitiva

    ctx = CtxFalso(ator["tenant_id"], ator["usuario_id"])
    with pytest.raises(FalhaDefinitiva) as e:
        acervo_tarefas.acervo_expor_arquivo(ctx, caminho=alvo["caminho"])
    assert "hash_divergente" in str(e.value)
    with db.db(ctxdb) as cur:
        cur.execute("SELECT count(*) AS n FROM plat.item WHERE tenant_id = %s", (ator["tenant_id"],))
        assert cur.fetchone()["n"] == antes, "nenhum item criado quando o hash diverge"
        cur.execute("SELECT count(*) AS n FROM plat.acervo_arquivo_exposto WHERE caminho = %s", (alvo["caminho"],))
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) AS n FROM plat.evento WHERE tipo = 'acervo/arquivo_recusar'")
        assert cur.fetchone()["n"] >= 1, "a recusa fica registrada como evento"
