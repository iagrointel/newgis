"""Fixtures do intercâmbio em lote (item L6-02-o). Reusa INTEIRO o harness de `tests/api/exportacao/conftest.py`
(item L0-04-h-exportar): dois inquilinos temporários, `semear_camada` (mesma `plat.camada_preparar` da
ingestão real), o worker de teste em subprocesso próprio e as funções de baixar/aguardar — nada disso é
reescrito aqui. O que este arquivo acrescenta é só o que L0-04-h não precisava: uma camada MENOR (a prova de
ida e volta não precisa de 100 mil feições para os formatos novos) e 20 camadas para a medida do escrow do
inquilino inteiro (cláusula 3 do portão)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.api.exportacao.conftest import (  # noqa: F401 — reexportado para os testes deste pacote
    InquilinoDeExportacao,
    WorkerDeTeste,
    conexao,
    semear_camada,
)

FEICOES_PEQUENA = 2_000


@pytest.fixture(scope="session")
def worker_intercambio(env):
    w = WorkerDeTeste(env, f"teste-intercambio-{__import__('os').getpid()}")
    yield w
    w.parar()


@pytest.fixture(scope="session")
def inquilino_ic(sessao_plat):
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="session")
def camada_ic(env, inquilino_ic):
    """Camada pequena (2 mil feições) para os formatos novos (filegdb.zip, mbtiles, pmtiles, geojsonseq):
    o portão pede ida e volta fiel, não volume — 100 mil pontos em MVT/PMTiles levaria minutos por rodada
    sem provar nada a mais sobre a quantização do tile."""
    return semear_camada(env, inquilino_ic, FEICOES_PEQUENA, "zt camada de intercambio (2 mil feicoes)")


@pytest.fixture(scope="session")
def camadas_20(env, inquilino_ic):
    """20 camadas pequenas (100 feições cada) no MESMO inquilino, para a cláusula 3 do portão ('export do
    inquilino com 20 camadas em tempo medido'). 100 feições por camada é o bastante para provar que o
    escrow trata N camadas de verdade (nomes de tabela distintos, contagem por camada no manifesto) sem
    gastar minutos de disco a 95%."""
    return [semear_camada(env, inquilino_ic, 100, f"zt camada {i:02d} do escrow", prefixo=f"escrow{i:02d}")
           for i in range(20)]


def esperar_intercambio(cliente, exportacao_id: str, timeout: float = 180) -> dict:
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = cliente.get(f"/api/intercambio/exportacoes/{exportacao_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("concluida", "falhou", "cancelada"):
            return ultimo
        time.sleep(0.25)
    pytest.fail(f"exportação {exportacao_id} não terminou em {timeout} s: {ultimo}")


def exportar_intercambio(cliente, corpo: dict, timeout: float = 180) -> dict:
    r = cliente.post("/api/intercambio/exportacoes", json=corpo)
    assert r.status_code == 202, r.text
    final = esperar_intercambio(cliente, r.json()["exportacao_id"], timeout)
    final["job_id"] = r.json()["job_id"]
    return final


def baixar_intercambio(cliente, exportacao_id: str, destino: Path) -> Path:
    r = cliente.get(f"/api/intercambio/exportacoes/{exportacao_id}/baixar")
    assert r.status_code == 200, r.text
    destino.write_bytes(r.content)
    return destino
