"""Vazão do receptor de fluxo (item L2-14-a-ingestao-de-fluxos) — a cláusula de desempenho do portão:

  "10 mil eventos/s pelo receptor HTTP em lote: perda 0 e atraso mediano <= 2 s medidos por 60 s
   (refutação do item-pai; RSS do plat-fluxo registrado)"

Medido contra o PROCESSO DE VERDADE: `python -m app.fluxo.servico` na porta de teste da trilha, com uvicorn,
soquete TCP e a mesma base. Não é o cliente ASGI em processo — a cláusula fala do receptor HTTP.

O que se mede, e como:
  perda        = eventos aceitos pelo receptor menos linhas gravadas na tabela (tem de ser zero);
  atraso       = mediana, no BANCO, de (recebido_em - tempo_evento), com o tempo do evento carimbado pelo
                 remetente no instante do envio — é o atraso de entrada, ponta a ponta até a fila;
  drenagem     = tempo entre o último envio e a última linha gravada (a escrita em lote é 1 por segundo);
  RSS          = memória residente do processo plat-fluxo no fim da medição.

A carga da máquina é gravada ao lado do número (regra da corrida): medida de tempo sem a carga ao lado não
vale como prova. O teste é marcado `lento` e só roda quando pedido explicitamente.
"""

import datetime
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.api.conftest import PREFIXO_TESTE

RAIZ = Path(__file__).resolve().parents[2]
ITEM = "L2-14-a-ingestao-de-fluxos"
PORTA = int(os.environ.get("PLAT_FLUXO_PORTA_TESTE", "8170"))
ALVO_EVENTOS_S = 10_000
SEGUNDOS = int(os.environ.get("PLAT_FLUXO_SEGUNDOS", "60"))
LOTE = 2_000                      # 5 pedidos por segundo de 2.000 eventos = 10 mil/s "em lote"
ATRASO_MEDIANO_MAX_MS = 2_000
UTC = datetime.UTC
MAPEAMENTO = {
    "campo_tempo": {"caminho": "ts", "tipo": "iso"},
    "campo_rastro": "placa",
    "geometria": {"modo": "lonlat", "lon": "lon", "lat": "lat"},
    "campos": [{"caminho": "velocidade", "coluna": "velocidade", "tipo": "numero"}],
}


def _carga_da_maquina() -> dict:
    livre_gb = None
    for linha in Path("/proc/meminfo").read_text().splitlines():
        if linha.startswith("MemAvailable:"):
            livre_gb = round(int(linha.split()[1]) / 1024 / 1024, 1)
    return {"carga_1min": round(os.getloadavg()[0], 2), "ram_livre_gb": livre_gb,
            "nucleos": os.cpu_count(),
            "medido_em": datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _rss_mb(pid: int) -> float | None:
    try:
        for linha in Path(f"/proc/{pid}/status").read_text().splitlines():
            if linha.startswith("VmRSS:"):
                return round(int(linha.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


@pytest.fixture
def processo_fluxo():
    """`plat-fluxo` de verdade, na porta da trilha, morto pelo identificador de processo no fim."""
    import socket

    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORTA)) == 0:
            pytest.skip(f"porta {PORTA} ocupada por outro processo desta máquina")
    ambiente = dict(os.environ, PYTHONPATH=str(RAIZ))
    processo = subprocess.Popen(
        [sys.executable, "-m", "app.fluxo.servico", "--porta", str(PORTA), "--host", "127.0.0.1"],
        cwd=str(RAIZ), env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    limite = time.monotonic() + 60
    while time.monotonic() < limite:
        if processo.poll() is not None:
            pytest.fail(f"plat-fluxo saiu com {processo.returncode}: "
                        f"{processo.stderr.read().decode('utf-8', 'replace')[-2000:]}")
        try:
            if httpx.get(f"http://127.0.0.1:{PORTA}/saude", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        processo.kill()
        pytest.fail("plat-fluxo não subiu em 60 s")
    yield processo
    processo.send_signal(signal.SIGTERM)
    try:
        processo.wait(timeout=30)
    except subprocess.TimeoutExpired:
        processo.kill()
        processo.wait(timeout=10)


@pytest.mark.lento
def test_dez_mil_eventos_por_segundo_sem_perda_e_com_atraso_baixo(sessao_a, processo_fluxo, medida, env):
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente
    from tests.api.test_rls import contexto, ids_por_slug

    def _conexao():
        """Conexão NOVA, aberta depois do minuto de envio. A conexão de uma fixture aberta antes do envio
        morre no caminho ("SSL connection has been closed unexpectedly", visto nesta máquina sob disputa):
        60 s ociosa num banco compartilhado com dezenas de frentes não é conexão confiável."""
        return psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)

    r = sessao_a.post("/api/fluxos", json={
        "tipo": "http", "nome": f"{PREFIXO_TESTE}-vazao-{secrets.token_hex(4)}",
        "mapeamento": MAPEAMENTO, "limite_eventos_s": 100_000})
    assert r.status_code == 201, r.text
    fonte = r.json()
    token = sessao_a.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-vazao-{secrets.token_hex(3)}",
                                               "escopos": [f"fluxo:escrever:{fonte['id']}"]}).json()
    url = f"http://127.0.0.1:{PORTA}/fluxo/{fonte['id']}/eventos"
    cabecalhos = {"Authorization": f"Bearer {token['token']}", "Content-Type": "application/json"}
    with _conexao() as inicial:
        tenant_a = ids_por_slug(inicial)["demo"]
    inicial.close()
    antes = _carga_da_maquina()

    # o processo recarrega o registro a cada 5 s; espera a fonte aparecer nele antes de medir
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        r = httpx.post(url, content=b"[]", headers=cabecalhos, timeout=10)
        if r.status_code in (200, 202):
            break
        time.sleep(1)
    assert r.status_code in (200, 202), f"a fonte não entrou no registro do processo: {r.text}"

    enviados = aceitos = 0
    atrasos_pedido_ms = []
    pedidos_por_segundo = ALVO_EVENTOS_S // LOTE
    with httpx.Client(timeout=30) as cliente:
        inicio = time.monotonic()
        for segundo in range(SEGUNDOS):
            alvo_do_segundo = inicio + segundo + 1
            for _ in range(pedidos_por_segundo):
                agora = datetime.datetime.now(UTC).isoformat()
                lote = [{"ts": agora, "placa": f"V{i % 1000:04d}", "lon": -46.6, "lat": -23.5,
                         "velocidade": 50 + (i % 30)} for i in range(LOTE)]
                t0 = time.monotonic()
                resposta = cliente.post(url, content=json.dumps(lote).encode(), headers=cabecalhos)
                atrasos_pedido_ms.append((time.monotonic() - t0) * 1000)
                assert resposta.status_code in (200, 202), resposta.text
                corpo = resposta.json()
                enviados += corpo["recebidos"]
                aceitos += corpo["aceitos"]
            sobra = alvo_do_segundo - time.monotonic()
            if sobra > 0:
                time.sleep(sobra)
        duracao_envio = time.monotonic() - inicio
    fim_do_envio = time.monotonic()

    # drenagem: a escrita é um lote por segundo; espera as linhas aparecerem (teto generoso, e o tempo
    # gasto é ele próprio uma medida)
    conferencia = _conexao()

    def _linhas():
        cur = conferencia.cursor()
        contexto(conferencia, tenant_a, 0, "plat-fluxo")
        cur.execute("SELECT count(*) AS n FROM plat.fluxo_evento WHERE fonte_id = %s::uuid", (fonte["id"],))
        n = cur.fetchone()["n"]
        conferencia.rollback()
        return n

    limite = time.monotonic() + 120
    linhas = 0
    while time.monotonic() < limite:
        linhas = _linhas()
        if linhas >= aceitos:
            break
        time.sleep(0.5)
    drenagem_s = round(time.monotonic() - fim_do_envio, 1)

    saude = httpx.get(f"http://127.0.0.1:{PORTA}/saude", headers=cabecalhos, timeout=10).json()
    rss = _rss_mb(processo_fluxo.pid)

    with conferencia as con:
        cur = con.cursor()
        contexto(con, tenant_a, 0, "plat-fluxo")
        cur.execute(
            "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM recebido_em - tempo_evento)) "
            "AS p50, percentile_disc(0.95) WITHIN GROUP "
            "(ORDER BY extract(epoch FROM recebido_em - tempo_evento)) AS p95 "
            "FROM plat.fluxo_evento WHERE fonte_id = %s::uuid", (fonte["id"],))
        percentis = cur.fetchone()
        con.rollback()
    atraso_p50_ms = round(float(percentis["p50"]) * 1000, 1)
    atraso_p95_ms = round(float(percentis["p95"]) * 1000, 1)
    depois = _carga_da_maquina()

    gravar = medida(ITEM)
    comando = "roda_teste.sh tests/api/test_fluxo_vazao.py -q -m lento"
    vazao = round(enviados / duracao_envio)
    for nome, valor, unidade in (
        ("vazao_receptor_http", vazao, "eventos/s"),
        ("eventos_enviados", enviados, "eventos"),
        ("eventos_aceitos", aceitos, "eventos"),
        ("linhas_gravadas", linhas, "linhas"),
        ("perda", aceitos - linhas, "eventos"),
        ("atraso_mediano", atraso_p50_ms, "ms"),
        ("atraso_p95", atraso_p95_ms, "ms"),
        ("drenagem_apos_ultimo_envio", drenagem_s, "s"),
        ("rss_plat_fluxo", rss, "MB"),
        ("duracao_do_envio", round(duracao_envio, 1), "s"),
        ("carga_1min_antes", antes["carga_1min"], "carga"),
        ("carga_1min_depois", depois["carga_1min"], "carga"),
        ("ram_livre_gb", depois["ram_livre_gb"], "GB"),
        ("nucleos", depois["nucleos"], "núcleos"),
        ("medido_em", depois["medido_em"], "instante"),
        ("erros_de_escrita", saude["erros_de_escrita"], "lotes"),
    ):
        gravar(nome, valor, unidade, comando)

    try:
        assert enviados == SEGUNDOS * ALVO_EVENTOS_S, f"o remetente não conseguiu enviar 10 mil/s: {enviados}"
        assert aceitos == enviados, f"o receptor descartou {enviados - aceitos} eventos"
        assert linhas == aceitos, f"perda entre o receptor e a tabela: {aceitos - linhas} eventos"
        assert saude["erros_de_escrita"] == 0
        assert atraso_p50_ms <= ATRASO_MEDIANO_MAX_MS, (
            f"atraso mediano {atraso_p50_ms} ms acima de {ATRASO_MEDIANO_MAX_MS} ms "
            f"(carga da máquina {depois['carga_1min']} em {depois['nucleos']} núcleos)")
    finally:
        with _conexao() as limpeza:
            cur = limpeza.cursor()
            contexto(limpeza, tenant_a, 0, "plat-fluxo")
            cur.execute("DELETE FROM plat.fluxo_evento WHERE fonte_id = %s::uuid", (fonte["id"],))
            limpeza.commit()
        limpeza.close()
        conferencia.close()
        sessao_a.delete(f"/api/tokens/{token['id']}")
        sessao_a.delete(f"/api/fluxos/{fonte['id']}")
