"""Portão do item L1-25-servico-de-imagem-esri-compativel, cláusula por cláusula, e as refutações do
adversário (mesmo padrão de tests/api/imagens/test_tiles_token.py, item irmão L1-02).

O que este arquivo mede em processo (TestClient): o documento do serviço `ImageServer?f=json` contra os
campos que o portão exige, `exportImage` com bbox em EPSG:3857 e EPSG:4326 (e o alias Esri 102100),
alinhamento de pixel ≤ 1 px contra o ladrilho XYZ do L1-02 para o MESMO recorte, `identify` num ponto de
dentro e de fora da cobertura, `tile/<z>/<y>/<x>` byte-a-byte igual ao XYZ, e as recusas: `renderingRule`/
`mosaicRule` (fora do contrato mínimo), `size` acima do teto, `format` não suportado, item de outro
inquilino (403, nunca 404) e token sem escopo."""

from __future__ import annotations

import pytest


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    """Mesmo COG sintético do L1-02 (4 bandas, 16 bits, EPSG:3857) — sem `proj:transform` nem
    `raster:bands.statistics` no STAC: exatamente o caso que prova que o documento do serviço OMITE
    pixelSizeX/Y e minValues/maxValues/meanValues em vez de inventar."""
    from tests.api.imagens.apoio_raster import semear_raster

    return semear_raster(tenant_id_a, "demo")


@pytest.fixture(scope="module")
def token_img(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-imgserver", "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_img_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": "zt-imgserver-b", "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_sem_escopo(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-imgserver-semescopo", "escopos": ["catalogo:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


def _base(tok: str, item: str) -> str:
    return f"/svc/{tok}/rest/services/{item}/ImageServer"


# ---------------------------------------------------------------- cláusula: documento do serviço
def test_documento_do_servico_tem_os_campos_obrigatorios(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}?f=json")
    assert r.status_code == 200, r.text
    doc = r.json()
    for campo in ("currentVersion", "name", "bandCount", "pixelType", "hasHistograms",
                  "capabilities", "extent", "initialExtent", "spatialReference"):
        assert campo in doc, (campo, doc)
    assert doc["bandCount"] == 4
    assert doc["pixelType"] == "U16"  # o COG sintético é uint16
    assert doc["extent"]["spatialReference"]["wkid"] == 3857
    assert doc["initialExtent"] == doc["extent"]
    assert doc["capabilities"] == "Image"
    # honestidade do portão: sem L1-02-h não há histograma, sem RAT não há tabela de atributo, e este
    # COG não tem raster:bands/statistics no STAC (apoio_raster.py não grava) -> nunca inventar valor
    assert doc["hasHistograms"] is False
    assert doc["hasRasterAttributeTable"] is False
    assert "minValues" not in doc and "maxValues" not in doc and "meanValues" not in doc


def test_documento_aceita_pjson_html_e_callback(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    pj = c.get(f"{_base(tok, item)}", params={"f": "pjson"})
    assert pj.status_code == 200 and "\n" in pj.text
    html = c.get(f"{_base(tok, item)}", params={"f": "html"})
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    cb = c.get(f"{_base(tok, item)}", params={"callback": "minhaFuncao"})
    assert cb.status_code == 200 and cb.text.startswith("minhaFuncao(") and cb.text.rstrip().endswith(");")


def test_estatistica_real_aparece_quando_o_item_stac_carrega(token_img, raster_demo):
    """O demo `apoio_raster` não tem `raster:bands`, mas o contrato existe: um item COM estatística
    devolve `minValues`/`maxValues`/`meanValues` medidos. Prova direto no `_documento_servico`, sem
    depender de outro item real no ambiente de teste."""
    from starlette.requests import Request as _StarletteRequest

    from app.auth.sessao import _auth_de_token
    from app.imagens import rotas_imageserver as ri

    escopo = {"type": "http", "headers": [], "client": ("testclient", 12345), "method": "GET",
             "path": "/", "query_string": b""}
    auth = _auth_de_token(_StarletteRequest(escopo), token_img["token"])
    doc = ri._documento_servico(auth, raster_demo["item_id"], "cientifico")
    assert "minValues" not in doc  # confirma a omissão para ESTE item, antes de testar o caminho positivo

    stac_com_stats = {"assets": {"cientifico": {"raster:bands": [
        {"statistics": {"minimum": 1.0, "maximum": 254.0, "mean": 80.5, "stddev": 12.3}},
        {"statistics": {"minimum": 2.0, "maximum": 250.0, "mean": 70.1, "stddev": 10.1}},
    ]}}}
    stats = ri._estatisticas(stac_com_stats, "cientifico")
    assert stats == {
        "minValues": [1.0, 2.0], "maxValues": [254.0, 250.0], "meanValues": [80.5, 70.1],
        "stdvValues": [12.3, 10.1],
    }


# ---------------------------------------------------------------- cláusula: exportImage
def test_export_image_devolve_png_e_jpeg_do_tamanho_pedido(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    bbox = "-47.95,-15.94,-47.76,-15.75"  # cobre o COG sintético (canto -47.95,-15.75, 0.19° de lado)
    png = c.get(f"{_base(tok, item)}/exportImage",
               params={"bbox": bbox, "bboxSR": "4326", "size": "300,200", "format": "png", "f": "image"})
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(png.content))
    assert im.size == (300, 200)

    jpg = c.get(f"{_base(tok, item)}/exportImage",
               params={"bbox": bbox, "bboxSR": "4326", "size": "128,128", "format": "jpg"})
    assert jpg.status_code == 200 and jpg.headers["content-type"] == "image/jpeg"
    assert jpg.content[:3] == b"\xff\xd8\xff"


def test_export_image_f_json_devolve_href_que_funciona(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    bbox = "-47.95,-15.94,-47.76,-15.75"
    r = c.get(f"{_base(tok, item)}/exportImage",
             params={"bbox": bbox, "bboxSR": "4326", "size": "64,64", "f": "json"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["width"] == 64 and corpo["height"] == 64
    assert corpo["extent"]["spatialReference"]["wkid"] == 4326
    assert "f=image" in corpo["href"]
    from urllib.parse import urlsplit
    partes = urlsplit(corpo["href"])
    caminho_e_consulta = partes.path + (f"?{partes.query}" if partes.query else "")
    segue = c.get(caminho_e_consulta)
    assert segue.status_code == 200 and segue.headers["content-type"] == "image/png"


def test_export_image_bbox_3857_e_4326_alinhado_ao_xyz_do_l1_02(token_img, raster_demo):
    """Cláusula literal do portão: bbox em 3857 E em 4326 alinhado ao XYZ, <= 1 px. Usa o mesmo
    ladrilho z/x/y do L1-02 como referência — mesma grade WebMercatorQuad, mesmo motor de leitura."""
    import io

    import numpy as np
    from morecantile import tms
    from morecantile.commons import Tile
    from PIL import Image

    grade = tms.get("WebMercatorQuad")
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    z, x, y = 12, 1503, 2230  # mesmo ladrilho de tests/api/imagens/test_tiles_token.py (cobre o COG sintético)
    xyz = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png")
    assert xyz.status_code == 200, xyz.text
    referencia = np.array(Image.open(io.BytesIO(xyz.content)).convert("RGB"))

    tile = Tile(x, y, z)
    b3857 = grade.xy_bounds(tile)
    r3857 = c.get(f"{_base(tok, item)}/exportImage", params={
        "bbox": f"{b3857.left},{b3857.bottom},{b3857.right},{b3857.top}", "bboxSR": "102100",
        "size": "256,256", "format": "png", "f": "image"})
    assert r3857.status_code == 200, r3857.text
    img3857 = np.array(Image.open(io.BytesIO(r3857.content)).convert("RGB"))
    diff = np.abs(img3857.astype(int) - referencia.astype(int))
    assert diff.max() <= 1, f"3857: diferença máxima de {diff.max()} entre exportImage e o XYZ"

    b4326 = grade.bounds(tile)
    r4326 = c.get(f"{_base(tok, item)}/exportImage", params={
        "bbox": f"{b4326.left},{b4326.bottom},{b4326.right},{b4326.top}", "bboxSR": "4326",
        "imageSR": "3857", "size": "256,256", "format": "png", "f": "image"})
    assert r4326.status_code == 200, r4326.text
    img4326 = np.array(Image.open(io.BytesIO(r4326.content)).convert("RGB"))
    diff2 = np.abs(img4326.astype(int) - referencia.astype(int))
    assert diff2.max() <= 1, f"4326->3857: diferença máxima de {diff2.max()} entre exportImage e o XYZ"


def test_export_image_size_acima_do_teto_e_recusado_em_json_esri(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/exportImage",
             params={"bbox": "-47.95,-15.94,-47.76,-15.75", "size": "20000,20000"})
    assert r.status_code == 400
    corpo = r.json()
    assert corpo["error"]["code"] == 400 and "message" in corpo["error"]


def test_export_image_format_nao_suportado_e_recusado_em_json_esri(token_img, raster_demo):
    """`tiff` PASSOU a ser suportado em 17/09 (conserto L1-25); o exemplo de formato recusado agora é
    um que de fato não existe no serviço."""
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/exportImage",
             params={"bbox": "-47.95,-15.94,-47.76,-15.75", "format": "bmp"})
    assert r.status_code == 400 and r.json()["error"]["code"] == 400


def test_export_image_mosaic_rule_fora_do_l1_08_e_recusado(token_img, raster_demo):
    """`mosaicRule` é LIMITADA (portão do item L1-25): um objeto que nem é mosaicRule, e os dois métodos
    Esri declarados FORA, continuam recusados com erro nomeado — nunca aceitos e ignorados."""
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/exportImage",
             params={"bbox": "-47.95,-15.94,-47.76,-15.75", "mosaicRule": '{"rasterFunction":"Grayscale"}'})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == 400
    for metodo in ("esriMosaicSeamline", "esriMosaicViewpoint"):
        rr = c.get(f"{_base(tok, item)}/exportImage",
                   params={"bbox": "-47.95,-15.94,-47.76,-15.75",
                           "mosaicRule": '{"mosaicMethod":"%s"}' % metodo})
        assert rr.status_code == 400, f"{metodo}: {rr.text}"
        assert metodo in rr.json()["error"]["message"], rr.text


def test_export_image_rendering_rule_nome_desconhecido_e_recusado_sem_500(token_img, raster_demo):
    """Item L1-02-f: `renderingRule` na forma mínima `{"rasterFunction":"<nome>"}` é ACEITO como forma —
    "Grayscale" não é uma predefinição desta plataforma (nem de fábrica, nem custom deste item), então
    recusa por predefinição inexistente (erro Esri, nunca 500, nunca aplicado às cegas)."""
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/exportImage",
             params={"bbox": "-47.95,-15.94,-47.76,-15.75", "renderingRule": '{"rasterFunction":"Grayscale"}'})
    assert r.status_code in (400, 422), r.text
    corpo = r.json()
    assert corpo["error"]["code"] in (400, 422)
    assert "Grayscale" in corpo["error"]["message"] or "renderingRule" in corpo["error"]["message"]


def test_export_image_rendering_rule_forma_encadeada_e_recusada_sem_500(token_img, raster_demo):
    """A forma completa do Pro (`rasterFunctionArguments`, encadeamento) nunca é interpretada — só a
    forma mínima `{"rasterFunction":"<nome>"}` (ver docstring de app/imagens/rotas_imageserver.py)."""
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/exportImage", params={
        "bbox": "-47.95,-15.94,-47.76,-15.75",
        "renderingRule": '{"rasterFunction":"Stretch","rasterFunctionArguments":{"Raster":{}}}'})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == 400


def test_export_image_bbox_malformado_nunca_500(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    for bbox in ("nao,e,numero,aqui", "1,2,3", "10,10,1,1"):  # xmax<xmin/ymax<ymin no último
        r = c.get(f"{_base(tok, item)}/exportImage", params={"bbox": bbox})
        assert r.status_code == 400, (bbox, r.status_code, r.text)
        assert r.json()["error"]["code"] == 400


# ---------------------------------------------------------------- cláusula: identify
def test_identify_devolve_valor_por_banda(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/identify", params={
        "geometry": "-47.85,-15.85", "geometryType": "esriGeometryPoint", "sr": "4326", "f": "json"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["value"] != "NoData"
    valores = corpo["value"].split(",")
    assert len(valores) == 4  # 4 bandas
    assert corpo["location"]["spatialReference"]["wkid"] == 4326


def test_identify_fora_da_cobertura_devolve_nodata(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/identify", params={"geometry": "0,0", "sr": "4326", "f": "json"})
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "NoData"


def test_identify_geometry_json_tambem_funciona(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    corpo_geom = '{"x": -47.85, "y": -15.85, "spatialReference": {"wkid": 4326}}'
    r = c.get(f"{_base(tok, item)}/identify", params={"geometry": corpo_geom, "f": "json"})
    assert r.status_code == 200 and r.json()["value"] != "NoData"


# ---------------------------------------------------------------- cláusula: tile/<z>/<y>/<x>
def test_tile_esri_e_byte_a_byte_igual_ao_xyz_do_l1_02(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    z, x, y = 12, 1503, 2230
    xyz = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png")
    esri = c.get(f"{_base(tok, item)}/tile/{z}/{y}/{x}")
    assert xyz.status_code == 200 and esri.status_code == 200
    assert esri.content == xyz.content
    assert esri.headers["content-type"] == "image/png"


def test_tile_esri_recusa_rendering_rule_e_band_ids(token_img, raster_demo):
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}/tile/12/2230/1503", params={"renderingRule": "{}"})
    assert r.status_code == 400 and r.json()["error"]["code"] == 400


# ---------------------------------------------------------------- refutação: inquilino, escopo, endereço
def test_token_de_outro_inquilino_nao_ve_o_item(token_img_b, raster_demo):
    c, tok_b, item = _cliente(), token_img_b["token"], raster_demo["item_id"]
    for url in (f"{_base(tok_b, item)}?f=json",
                f"{_base(tok_b, item)}/exportImage?bbox=-47.95,-15.94,-47.76,-15.75",
                f"{_base(tok_b, item)}/identify?geometry=-47.85,-15.85",
                f"{_base(tok_b, item)}/tile/12/2230/1503"):
        r = c.get(url)
        assert r.status_code == 403, (url, r.status_code, r.text)
        assert r.json()["erro"] == "item_indisponivel"


def test_token_sem_escopo_imagens_nem_tiles_e_recusado(token_sem_escopo, raster_demo):
    c, tok, item = _cliente(), token_sem_escopo["token"], raster_demo["item_id"]
    r = c.get(f"{_base(tok, item)}?f=json")
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"


def test_openapi_nao_declara_parametro_de_endereco_de_arquivo(token_img):
    """Mesma prova estrutural do L1-02: nenhuma rota do ImageServer aceita `url`/`src`/`caminho` — o
    caminho do COG nasce do catálogo do inquilino, nunca de entrada do cliente."""
    from app.main import app

    spec = app.openapi()
    achou_alguma = False
    for caminho, metodos in spec["paths"].items():
        if "/ImageServer" not in caminho:
            continue
        achou_alguma = True
        for op in metodos.values():
            nomes = {p["name"].lower() for p in op.get("parameters", [])}
            assert not (nomes & {"url", "src", "href", "arquivo", "caminho", "endereco"}), (caminho, nomes)
    assert achou_alguma, "nenhuma rota /ImageServer no OpenAPI — o router foi montado em app/main.py?"
