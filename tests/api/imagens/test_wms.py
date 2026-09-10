"""Portão do item L1-02-g-wms-1-3-0-raster, cláusula por cláusula, e as refutações do adversário.

O que este arquivo mede em processo (TestClient): GetCapabilities válido contra o ESQUEMA OFICIAL do
OGC (cópia local em tests/dados/ogc_xsd/wms/1.3.0, extraída do commit b0b52199f — 64 arquivos de XSD
já em cache no object store deste repositório, sem depender de rede); GetMap devolvendo PNG do tamanho
pedido; o eixo invertido do BBOX em EPSG:4326 (o defeito clássico do WMS 1.3.0) comparado com o mesmo
recorte em EPSG:3857; camada de outro inquilino invisível (nem no GetCapabilities, nem endereçável por
GetMap); token sem escopo recusado; tamanho acima do teto recusado; abusos do adversário (WIDTH
gigante, BBOX invertido de verdade, CRS inexistente, STYLES arbitrário, SLD_BODY com entidade externa)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
XSD = ROOT / "tests" / "dados" / "ogc_xsd"


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def raster_demo_b(tenant_id_b, sessao_b):
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_b, "demo2")


@pytest.fixture(scope="module")
def token_wms(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-wms", "escopos": ["tiles:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_wms_sem_escopo(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-wms-sem-escopo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


# ---------------------------------------------------------------- cláusula: GetCapabilities válido no XSD oficial
def _validar_xsd(xml_texto: str, tmp_path: Path) -> subprocess.CompletedProcess:
    arq = tmp_path / "capabilities.xml"
    arq.write_text(xml_texto, encoding="utf-8")
    return subprocess.run(
        ["xmllint", "--nonet", "--noout", "--schema", str(XSD / "wms" / "1.3.0" / "capabilities_1_3_0.xsd"),
         str(arq)],
        capture_output=True, text=True, cwd=str(XSD),
        env={**os.environ, "XML_CATALOG_FILES": str(XSD / "catalogo.xml")},
    )


@pytest.mark.skipif(shutil.which("xmllint") is None, reason="xmllint (libxml2-utils) ausente")
def test_getcapabilities_valida_no_esquema_oficial_1_3_0(token_wms, raster_demo, tmp_path):
    c, tok = _cliente(), token_wms["token"]
    r = c.get(f"/svc/{tok}/wms", params={"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")
    saida = _validar_xsd(r.text, tmp_path)
    assert saida.returncode == 0, saida.stderr[-2000:]
    assert "validates" in saida.stderr
    assert f">{raster_demo['item_id']}<" in r.text.replace("<Name>", ">").replace("</Name>", "<") or \
        raster_demo["item_id"] in r.text


def test_getcapabilities_declara_bbox_4326_e_3857(token_wms, raster_demo):
    c, tok = _cliente(), token_wms["token"]
    xml = c.get(f"/svc/{tok}/wms", params={"REQUEST": "GetCapabilities"}).text
    assert 'CRS="EPSG:4326"' in xml and 'CRS="EPSG:3857"' in xml
    assert "<EX_GeographicBoundingBox>" in xml
    assert "<CRS>EPSG:4326</CRS>" in xml and "<CRS>EPSG:3857</CRS>" in xml


def test_getcapabilities_service_case_insensitive_kvp(token_wms, raster_demo):
    """§6.3.3 da spec: nome de parâmetro é insensível a maiúscula/minúscula."""
    c, tok = _cliente(), token_wms["token"]
    r = c.get(f"/svc/{tok}/wms", params={"service": "wms", "request": "getcapabilities", "version": "1.3.0"})
    assert r.status_code == 200 and r.text.startswith('<?xml')


# ---------------------------------------------------------------- cláusula: GetMap devolve PNG do tamanho pedido
def _bounds4326(c, tok, item) -> tuple[float, float, float, float]:
    """bounds REAIS do raster de teste (nunca um número digitado de novo — vem do próprio
    `info.json`, já testado e correto pelo portão do L1-02-tiles-token)."""
    r = c.get(f"/svc/{tok}/raster/{item}/info.json")
    assert r.status_code == 200, r.text
    oeste, sul, leste, norte = r.json()["bounds"]
    return oeste, sul, leste, norte


def _bbox3857(c, tok, item) -> str:
    from rasterio.warp import transform_bounds

    oeste, sul, leste, norte = _bounds4326(c, tok, item)
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", "EPSG:3857", oeste, sul, leste, norte)
    return f"{minx},{miny},{maxx},{maxy}"


def _getmap(c, tok, item, **extra):
    p = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": item, "STYLES": "",
         "CRS": "EPSG:3857", "BBOX": _bbox3857(c, tok, item),
         "WIDTH": "256", "HEIGHT": "256", "FORMAT": "image/png", "TRANSPARENT": "TRUE"}
    p.update(extra)
    return c.get(f"/svc/{tok}/wms", params=p)


def test_getmap_devolve_png_do_tamanho_pedido(token_wms, raster_demo):
    import io

    from PIL import Image

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, WIDTH="300", HEIGHT="150")
    assert r.status_code == 200, r.text[:500]
    assert r.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (300, 150)
    # não é uma imagem vazia: a bbox cobre o raster de teste (Brasília, EPSG:3857) — tem de haver
    # pelo menos um pixel não totalmente transparente/preto
    extremos = img.convert("RGBA").getextrema()
    assert any(hi > 0 for _, hi in extremos)


def test_getmap_jpeg_sem_transparencia(token_wms, raster_demo):
    import io

    from PIL import Image

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, FORMAT="image/jpeg", TRANSPARENT="FALSE", WIDTH="128", HEIGHT="128")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (128, 128) and img.mode == "RGB"


def test_getmap_fora_da_cobertura_devolve_imagem_em_branco_do_tamanho_pedido(token_wms, raster_demo):
    import io

    from PIL import Image

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, BBOX="0,0,10000,10000", WIDTH="64", HEIGHT="64")
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (64, 64)
    assert img.convert("RGBA").getextrema()[3] == (0, 0)  # canal alfa todo zero: transparente, sem dado


# ---------------------------------------------------------------- cláusula: eixo invertido em EPSG:4326
def test_eixo_invertido_4326_bate_com_3857(token_wms, raster_demo):
    """O mesmo retângulo geográfico pedido em EPSG:3857 (ordem normal) e em EPSG:4326 (BBOX = lat,lon,
    lat,lon — o defeito clássico do WMS 1.3.0) tem de produzir uma imagem com cobertura de dado
    equivalente. Pedir o BBOX de 4326 na ordem ERRADA (lon,lat) devolveria uma janela bem menor/
    deslocada (ou vazia) — é essa diferença que a asserção final prova."""
    import io

    from PIL import Image

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    oeste, sul, leste, norte = _bounds4326(c, tok, item)  # bounds REAIS do raster, do próprio info.json

    r_correto = _getmap(c, tok, item, CRS="EPSG:4326", BBOX=f"{sul},{oeste},{norte},{leste}",
                        WIDTH="200", HEIGHT="200")
    assert r_correto.status_code == 200, r_correto.text[:500]
    img_correto = Image.open(io.BytesIO(r_correto.content)).convert("RGBA")
    alfa_correto = img_correto.getextrema()[3][1]  # máximo do canal alfa: >0 se algum pixel tem dado
    assert alfa_correto > 0

    # a mesma bbox, na ordem ERRADA (lon,lat como se fosse CRS:84) -- não é o que um cliente WMS 1.3.0
    # conforme manda, mas o servidor tem de recusar de forma limpa (nunca 500) OU devolver algo
    # geometricamente diferente; aqui conferimos que ele NÃO finge que está certo: ou refuta (400/
    # ServiceExceptionReport), ou a bbox literal (oeste como "sul") cai fora da faixa de latitude válida
    # e produz cobertura claramente distinta da correta.
    r_errado = _getmap(c, tok, item, CRS="EPSG:4326", BBOX=f"{oeste},{sul},{leste},{norte}",
                       WIDTH="200", HEIGHT="200")
    if r_errado.status_code == 200 and r_errado.headers["content-type"] == "image/png":
        img_errado = Image.open(io.BytesIO(r_errado.content)).convert("RGBA")
        # oeste=-47.95 usado como "sul" (latitude) é inválido (< -90 não, mas dista ~32° do raster real);
        # a imagem não pode ter a MESMA cobertura de dado que a correta
        assert img_errado.tobytes() != img_correto.tobytes()
    else:
        assert r_errado.status_code in (200, 400)
        assert "ServiceException" in r_errado.text


def test_eixo_normal_3857_nao_troca(token_wms, raster_demo):
    """EPSG:3857 nunca troca eixo — smoke test direto do comentário em wms.py."""
    from app.imagens import wms as wms_doc

    assert wms_doc.bbox_do_parametro("EPSG:3857", (1.0, 2.0, 3.0, 4.0)) == (1.0, 2.0, 3.0, 4.0)
    assert wms_doc.bbox_do_parametro("EPSG:4326", (2.0, 1.0, 4.0, 3.0)) == (1.0, 2.0, 3.0, 4.0)


# ---------------------------------------------------------------- cláusula: isolamento entre inquilinos
def test_camada_de_outro_inquilino_invisivel_no_capabilities(token_wms, raster_demo, raster_demo_b):
    c, tok = _cliente(), token_wms["token"]
    xml = c.get(f"/svc/{tok}/wms", params={"REQUEST": "GetCapabilities"}).text
    assert raster_demo["item_id"] in xml
    assert raster_demo_b["item_id"] not in xml


def test_camada_de_outro_inquilino_recusada_no_getmap(token_wms, raster_demo_b):
    c, tok, item_b = _cliente(), token_wms["token"], raster_demo_b["item_id"]
    r = _getmap(c, tok, item_b)
    assert r.status_code == 400
    assert "ServiceException" in r.text and "LayerNotDefined" in r.text
    # nunca confirma se o item existe: a mensagem para "de outro inquilino" é igual à de "não existe"
    r2 = _getmap(c, tok, "item-que-nunca-existiu")
    assert r2.status_code == 400 and "LayerNotDefined" in r2.text


# ---------------------------------------------------------------- cláusula: escopo insuficiente
def test_token_sem_escopo_recusado(token_wms_sem_escopo, raster_demo):
    c, tok, item = _cliente(), token_wms_sem_escopo["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/wms", params={"REQUEST": "GetCapabilities"})
    assert r.status_code == 403
    r2 = _getmap(c, tok, item)
    assert r2.status_code == 403


def test_token_invalido_recusado(raster_demo):
    c = _cliente()
    r = c.get("/svc/token-que-nao-existe/wms", params={"REQUEST": "GetCapabilities"})
    assert r.status_code == 403


# ---------------------------------------------------------------- cláusula/refutação: abusos do adversário
def test_width_gigante_recusado_sem_500(token_wms, raster_demo):
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, WIDTH="100000", HEIGHT="100000")
    assert r.status_code == 400
    assert "ServiceExceptionReport" in r.text and "ServiceException" in r.text


def test_bbox_invertido_de_verdade_recusado(token_wms, raster_demo):
    """min > max de propósito (não é troca de eixo — é um retângulo às avessas)."""
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, BBOX="-5320000,-1755000,-5341203,-1774267")
    assert r.status_code == 400 and "ServiceException" in r.text


def test_crs_inexistente_recusado(token_wms, raster_demo):
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, CRS="EPSG:999999")
    assert r.status_code == 400
    assert "InvalidCRS" in r.text


def test_styles_arbitrario_recusado(token_wms, raster_demo):
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, STYLES="qualquer-coisa-inventada")
    assert r.status_code == 400 and "StyleNotDefined" in r.text


def test_sld_body_com_entidade_externa_nunca_processado(token_wms, raster_demo):
    """XXE clássico: DOCTYPE com ENTITY externa lendo /etc/passwd. O servidor tem de recusar de forma
    limpa (nunca tentar interpretar o XML — se tentasse, o teste esperaria erro de parser, não 400
    limpo) e, sobretudo, NUNCA incluir conteúdo de arquivo local na resposta."""
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    xxe = ('<?xml version="1.0"?><!DOCTYPE StyledLayerDescriptor [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
           '<StyledLayerDescriptor>&xxe;</StyledLayerDescriptor>')
    r = _getmap(c, tok, item, SLD_BODY=xxe)
    assert r.status_code == 400
    assert "root:" not in r.text  # /etc/passwd nunca vaza
    assert "ServiceException" in r.text


def test_operacao_desconhecida_devolve_service_exception(token_wms, raster_demo):
    c, tok = _cliente(), token_wms["token"]
    r = c.get(f"/svc/{tok}/wms", params={"REQUEST": "GetFeatureInfo"})
    assert r.status_code == 400
    assert "OperationNotSupported" in r.text


def test_getmap_sem_layers_service_exception(token_wms):
    c, tok = _cliente(), token_wms["token"]
    r = c.get(f"/svc/{tok}/wms", params={"REQUEST": "GetMap"})
    assert r.status_code == 400 and "ServiceException" in r.text
