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


@pytest.fixture(scope="session")
def arquivo_a(inquilino_a):
    """Um arquivo de verdade no bucket do inquilino, pelo fluxo do produto (`POST /api/uploads` ->
    `PUT .../partes/1` -> `POST .../concluir`, o mesmo `Uploader` do item L0-04-a). Sem ele o pacote sairia com
    `arquivos.zip` vazio e a cláusula "os arquivos do bucket em zip por item" ficaria sem prova."""
    from tests.api.uploads.test_uploads import Uploader

    up = Uploader(inquilino_a.admin)
    conteudo = ("id,nome\n" + "\n".join(f"{i},zt {i}" for i in range(200))).encode("utf-8")
    r = up.iniciar("zt-arquivo-do-inquilino.csv", conteudo, "csv")
    upload_id = r.json()["id"]
    for resposta in up.enviar_partes(upload_id, conteudo, r.json()["parte_bytes"]):
        assert resposta.status_code == 200, resposta.text
    arquivo_id = up.concluir(upload_id).json()["arquivo_id"]
    yield {"item_id": arquivo_id, "bytes": len(conteudo)}
    up.liberar_token()
