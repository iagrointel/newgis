"""Fixtures da exportação COMPLETA do inquilino (item L0-06-d-exportar-inquilino). Reaproveita o
`WorkerDeTeste` já escrito para o irmão L0-04-h (mesma disciplina: worker próprio em subprocesso, contra o
schema da TRILHA, nunca a unidade `plat-worker` de produção)."""

from __future__ import annotations

import os

import pytest

from tests.api.exportacao.conftest import InquilinoDeExportacao, WorkerDeTeste, semear_camada


@pytest.fixture(scope="session")
def worker_exportacao_inquilino(env):
    w = WorkerDeTeste(env, f"teste-exportacao-inquilino-{os.getpid()}")
    yield w
    w.parar()


@pytest.fixture(scope="session")
def inquilino_a(sessao_plat):
    """Inquilino temporário próprio deste item (slug sem hífen, como o L0-04-h exige para poder semear
    camada hospedada pela mesma `plat.camada_preparar` da ingestão)."""
    inq = InquilinoDeExportacao(sessao_plat)
    yield inq
    inq.apagar()


@pytest.fixture(scope="session")
def camada_a(env, inquilino_a):
    """Uma camada hospedada pequena no inquilino de teste — o suficiente para o GeoPackage do pacote sair
    com N=1 camada e provar a cláusula "N camadas do catálogo", sem o custo de 100 mil feições do L0-04-h."""
    return semear_camada(env, inquilino_a, 500, "zt camada do inquilino (exportacao completa)")
