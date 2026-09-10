"""Porta HTTPS do item L1-02-e: bytes do COG e recusas da borda autenticada."""

import pytest


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


def _token(sessao, nome: str, escopos: list[str]):
    resposta = sessao.post("/api/tokens", json={"nome": nome, "escopos": escopos})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture(scope="module")
def token_imagens_a(sessao_a):
    dados = _token(sessao_a, "zt-cog-a", ["imagens:ler"])
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_imagens_b(sessao_b):
    dados = _token(sessao_b, "zt-cog-b", ["imagens:ler"])
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


def _url(token: dict, raster: dict, asset: str = "cientifico") -> str:
    return f"/svc/{token['token']}/cog/{raster['item_id']}/{asset}.tif"


def test_200_sem_range_entrega_cog_com_cabecalhos(token_imagens_a, raster_demo):
    from app import objetos

    resposta = _cliente().get(_url(token_imagens_a, raster_demo))
    assert resposta.status_code == 200
    assert resposta.content[:4] in (b"II*\x00", b"MM\x00*")
    assert len(resposta.content) == objetos.tamanho(raster_demo["chave"])
    assert resposta.headers["content-length"] == str(len(resposta.content))
    assert resposta.headers["accept-ranges"] == "bytes"
    assert resposta.headers["etag"].startswith('"')


def test_206_com_range_e_content_range_correto(token_imagens_a, raster_demo):
    resposta = _cliente().get(_url(token_imagens_a, raster_demo), headers={"Range": "bytes=8-31"})
    assert resposta.status_code == 206
    assert len(resposta.content) == 24
    assert resposta.headers["content-length"] == "24"
    assert resposta.headers["content-range"].startswith("bytes 8-31/")
    assert resposta.headers["accept-ranges"] == "bytes"


def test_faixa_invalida_da_416(token_imagens_a, raster_demo):
    resposta = _cliente().get(_url(token_imagens_a, raster_demo), headers={"Range": "bytes=999999999-"})
    assert resposta.status_code == 416
    assert resposta.json()["erro"] == "faixa_invalida"
    assert resposta.headers["content-range"].startswith("bytes */")


def test_asset_inexistente_da_404(token_imagens_a, raster_demo):
    resposta = _cliente().get(_url(token_imagens_a, raster_demo, "inexistente"))
    assert resposta.status_code == 404
    assert resposta.json()["erro"] == "asset_inexistente"


def test_item_de_outro_inquilino_fica_invisivel(token_imagens_b, raster_demo):
    resposta = _cliente().get(_url(token_imagens_b, raster_demo))
    assert resposta.status_code == 403
    assert resposta.json()["erro"] == "item_indisponivel"


def test_token_sem_escopo_da_403(sessao_a, raster_demo):
    dados = _token(sessao_a, "zt-cog-sem-escopo", ["catalogo:ler"])
    try:
        resposta = _cliente().get(_url(dados, raster_demo))
        assert resposta.status_code == 403
        assert resposta.json()["erro"] == "escopo_insuficiente"
    finally:
        sessao_a.delete(f"/api/tokens/{dados['id']}")
