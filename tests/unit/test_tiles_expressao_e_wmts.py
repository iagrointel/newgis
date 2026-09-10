"""Unidade do motor de ladrilho (item L1-02): gramática de expressão e forma do WMTS. Sem banco, sem
rede, sem armazenamento — o que aqui reprovar, reprova em qualquer máquina."""

import re

import pytest

from app.imagens import tiles, wmts


@pytest.mark.parametrize("expressao", [
    "(b4-b3)/(b4+b3)", "b1", "b10*2", "(b8a-b4)" .replace("b8a", "b8"), "where(b1>1000,1,0)",
    "sqrt(b1)", "(b4 - b3) / (b4 + b3 + 0.0001)", "minimum(b1,b2)", "log10(b1+1)",
])
def test_expressao_da_gramatica_passa(expressao):
    ok, motivo = tiles.expressao_valida(expressao)
    assert ok, (expressao, motivo)


@pytest.mark.parametrize("expressao", [
    "", "1+1", "os.system('id')", "__import__('os')", "eval(b1)", "exec(b1)", "b1.__class__",
    "open('/etc/passwd')", "getattr(b1,'a')", "b1 and b2", "lambda: b1", "b1#comentário",
    "b1 ; b2", "b1[0]", "{'a':b1}", "b" + "9" * 250,
])
def test_expressao_fora_da_gramatica_reprova(expressao):
    ok, motivo = tiles.expressao_valida(expressao)
    assert not ok and motivo


def test_bandas_da_expressao():
    assert tiles.bandas_da_expressao("(b8-b4)/(b8+b4)") == [4, 8]
    assert tiles.bandas_da_expressao("b1") == [1]


def test_env_gdal_nao_carrega_credencial():
    """A credencial do balde vai na SESSÃO (rasterio recusa AWS_* dentro de Env); se algum dia alguém
    puser chave aqui, ela vazaria para todo `rasterio.Env` do processo."""
    env = tiles.env_gdal()
    assert not [k for k in env if k.startswith("AWS_")]
    assert env["GDAL_DISABLE_READDIR_ON_OPEN"] == "EMPTY_DIR"


def test_capabilities_tem_a_estrutura_que_o_cliente_le():
    xml = wmts.capabilities(
        base="https://exemplo.gov.br/svc/plat_abc/raster/i1", identificador="i1", titulo="Imagem",
        bounds=[-48.0, -16.0, -47.5, -15.5], zoom_min=0, zoom_max=14,
        formatos=["image/png", "image/jpeg"], consulta="expressao=b1", resumo="teste")
    assert xml.startswith("<?xml version=")
    assert 'version="1.0.0"' in xml and "<ows:ServiceType>OGC WMTS</ows:ServiceType>" in xml
    assert xml.count("<TileMatrix>") == 15  # 0..14
    assert "urn:ogc:def:crs:EPSG::3857" in xml
    assert 'template="https://exemplo.gov.br/svc/plat_abc/raster/i1/{TileMatrix}/{TileCol}/{TileRow}.png?expressao=b1"' in xml  # noqa: E501
    # o nível 0 do WebMercatorQuad tem 1x1 ladrilhos e a origem no canto superior esquerdo do mundo
    assert "<MatrixWidth>1</MatrixWidth>" in xml
    assert re.search(r"<TopLeftCorner>-20037508\.34\d* 20037508\.34\d*</TopLeftCorner>", xml)


def test_formatos_e_grade_sao_fechados():
    assert set(tiles.FORMATOS) == {"png", "jpg", "jpeg", "webp"}
    assert wmts.TMS_ID == "WebMercatorQuad"
    assert tiles.TAMANHO == 256
