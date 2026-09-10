import re
import statistics
import time
from pathlib import Path

from app.db import migracoes_em_disco

ROOT = Path(__file__).resolve().parents[2]
CAMPOS = {"versao", "git_sha", "ambiente", "banco", "migracoes_aplicadas", "migracoes_pendentes",
          "ultima_migracao", "servicos", "fila", "tempo_ms", "em"}


def test_saude_200_com_json_do_contrato(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) == CAMPOS
    assert j["banco"] == "ok"
    assert j["migracoes_pendentes"] == 0
    # Duas famílias de nome convivem (ADR 0014): o legado `NNN_slug`, fechado em 047, e o carimbo de
    # tempo `YYYYMMDDTHHMM_slug` de toda migração nova. `migracoes_em_disco` já devolve as duas na
    # ordem de aplicação (legado primeiro, depois carimbo).
    migracoes = migracoes_em_disco()
    assert j["migracoes_aplicadas"] == len(migracoes)
    # "última" aqui quer dizer A DE AUTORIA MAIS RECENTE (o maior carimbo de tempo; na falta de
    # carimbo, o maior número do legado), não a maior string nem a última que foi aplicada no banco.
    assert j["ultima_migracao"] == migracoes[-1]
    assert re.fullmatch(r"\d+\.\d+\.\d+", j["versao"])
    assert re.fullmatch(r"[0-9a-f]{7,12}", j["git_sha"])
    assert j["ambiente"] in ("producao", "dev")
    assert set(j["servicos"]) == {"martin", "titiler", "garage", "worker"}
    assert all(v in ("ausente", "ok", "erro") for v in j["servicos"].values())
    # fila (ADR 0003 seção 4.6): a unidade plat-worker tem de estar viva e alcançável em PLAT_WORKER_URL
    assert set(j["fila"]) == {"pendentes", "rodando", "workers_vivos", "ultimo_heartbeat"}, j["fila"]
    assert j["fila"]["workers_vivos"] >= 1, j["fila"]
    assert j["servicos"]["worker"] == "ok", j["servicos"]
    assert isinstance(j["tempo_ms"], int | float) and j["tempo_ms"] >= 0
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", j["em"])
    assert r.headers["Cache-Control"] == "no-store"
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["X-Req-Id"])


def test_api_versao_200_sem_banco(cliente):
    r = cliente.get("/api/versao")
    assert r.status_code == 200
    assert set(r.json()) == {"versao", "git_sha", "ambiente", "em"}


def test_versao_e_saude_sao_a_mesma_implantacao(cliente):
    assert cliente.get("/api/versao").json()["git_sha"] == cliente.get("/saude").json()["git_sha"]


def test_raiz_devolve_pagina_com_noindex(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert '<meta name="robots" content="noindex, nofollow">' in r.text
    assert "/static/app.js" in r.text


def test_latencia_saude_e_versao(cliente, medida):
    gravar = medida("L0-01-repo")
    for rota, nome in (("/saude", "latencia_saude_ms"), ("/api/versao", "latencia_versao_ms")):
        tempos = []
        for _ in range(20):
            t0 = time.perf_counter()
            assert cliente.get(rota).status_code == 200
            tempos.append((time.perf_counter() - t0) * 1000)
        gravar(nome, round(statistics.median(tempos), 2), "ms",
               f"mediana de 20 GET {rota} pelo TestClient (tests/api/test_saude.py)")
