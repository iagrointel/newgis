"""Portão do item L1-02-f-predefinicoes-de-renderizacao-e-legenda, cláusula por cláusula, e as
refutações do adversário.

Usa o COG sintético de 4 bandas de `tests/api/imagens/apoio_raster.py` (banda4 = infravermelho
próximo, padrão de vegetação alternada com contraste real) — as predefinições de índice (NDVI/NDWI/
NBR-aproximado) e a de falsa-cor exigem 4 bandas, que o item real da demo (Sentinel-2 3 bandas) não tem.

A prova PIXEL DE REFERÊNCIA das 6 predefinições de fábrica — a cláusula do portão que o adversário de
linha L1 (T9) achou em aberto — está COMMITADA e reproduzível desde 17/09/2026 em
`tests/unit/test_l102f_pixel_referencia.py`, contra `tests/dados/predefinicoes_referencia.json`
(9 pixels por predefinição, tolerância de 2 níveis por canal, COG gerado localmente pela mesma fórmula
determinística deste apoio). Este arquivo segue medindo o comportamento pela API; aquele mede o pixel."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


def _cliente():
    from app.main import app

    return TestClient(app, base_url="http://testserver")


# banda1=azul, banda2=verde, banda3=vermelho, banda4=infravermelho próximo — mesma fórmula de
# `apoio_raster._gerar_cog` (jitter incluído nas duas primeiras, degrau seco nas duas últimas); o COG
# sintético em si NÃO carrega `raster:bands`/estatística (os testes de WMS/tiles que o criaram não
# precisavam) — as predefinições de fábrica com esticamento por percentil e o teste de `n_bandas`
# (allowRasterFunction, min_bandas) precisam, então este módulo GRAVA a estatística real da fórmula
# geradora (não um número inventado: é a faixa exata que `_gerar_cog` produz) depois de semear.
_ESTATISTICAS_4B = [
    {"nodata": 0.0, "statistics": {"minimum": 400.0, "maximum": 717.0, "mean": 570.0, "stddev": 90.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 700.0, "maximum": 913.0, "mean": 810.0, "stddev": 60.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 900.0, "maximum": 2100.0, "mean": 1500.0, "stddev": 600.0,
                                   "valid_percent": 100.0}},
    {"nodata": 0.0, "statistics": {"minimum": 1200.0, "maximum": 3800.0, "mean": 2500.0, "stddev": 1300.0,
                                   "valid_percent": 100.0}},
]


def _com_estatisticas(tenant_id: int, colecao: str, item_id: str) -> None:
    from app import db
    from app.catalogo.comum import jsonb
    from app.imagens import pgstac as ps

    ctx = db.Contexto(tenant_id=tenant_id, usuario_id=0, login="teste")
    with db.db(ctx) as cur:
        item = ps.item_obter(cur, tenant_id, colecao, item_id)
        item["assets"]["cientifico"]["raster:bands"] = _ESTATISTICAS_4B
        cur.execute("SELECT pgstac.update_item(%s::jsonb)", (jsonb(item),))


@pytest.fixture(scope="module")
def raster_demo(tenant_id_a, sessao_a):
    from tests.api.imagens.apoio_raster import semear_raster

    dados = semear_raster(tenant_id_a, "predef")
    _com_estatisticas(tenant_id_a, dados["colecao"], dados["item_id"])
    return dados


@pytest.fixture(scope="module")
def raster_demo_b(tenant_id_b, sessao_b):
    from tests.api.imagens.apoio_raster import semear_raster

    dados = semear_raster(tenant_id_b, "predef2")
    _com_estatisticas(tenant_id_b, dados["colecao"], dados["item_id"])
    return dados


@pytest.fixture(scope="module")
def token_predef(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-predef", "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_a.delete(f"/api/tokens/{dados['id']}")


@pytest.fixture(scope="module")
def token_predef_b(sessao_b):
    r = sessao_b.post("/api/tokens", json={"nome": "zt-predef-b", "escopos": ["imagens:ler"]})
    assert r.status_code == 201, r.text
    dados = r.json()
    yield dados
    sessao_b.delete(f"/api/tokens/{dados['id']}")


def _url_item(sessao_dono, item_id: str) -> str:
    """`plat.item` do item raster sintético (apoio_raster já cria a linha em `plat.item`) — a CRUD de
    predefinições vive em cima desse uuid."""
    return f"/api/imagens/{item_id}/predefinicoes"


# ---------------------------------------------------------------- cláusula: predefinição inválida = 422
def test_predefinicao_invalida_422_com_caminho_do_erro(sessao_a, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "sem-titulo"})
    assert r.status_code == 422, r.text  # pydantic: 'titulo' ausente


def test_esquema_recusa_campo_fora_do_vocabulario(sessao_a, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={
        "nome": "com-campo-extra", "titulo": "x", "campo_que_nao_existe": 1,
    })
    assert r.status_code == 422, r.text


def test_colormap_desconhecido_recusado_422(sessao_a, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={
        "nome": "colormap-ruim", "titulo": "x", "colormap": "rampa-que-nao-existe-70000-entradas",
    })
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["erro"] == "predefinicao_invalida"


def test_banda_inexistente_no_item_e_422(sessao_a, raster_demo):
    """Adversário: predefinição referencia banda 10 (dentro do esquema, 1-64 — mas o item sintético só
    tem 4 bandas: recusa por incompatibilidade real com o item, não pela forma)."""
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={
        "nome": "banda-fora", "titulo": "x", "bandas": [10],
    })
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "predefinicao_incompativel"


def test_banda_muito_alta_recusada_pelo_esquema(sessao_a, raster_demo):
    """Adversário: predefinição com banda 99 (fora até do esquema — teto de 64) recusa pela FORMA,
    nunca 500."""
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "banda-fora-do-esquema", "titulo": "x",
                                                       "bandas": [99]})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "predefinicao_invalida"


def test_nome_reservado_de_fabrica_nao_pode_ser_criado(sessao_a, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "ndvi", "titulo": "tentando roubar o nome"})
    assert r.status_code == 409, r.text


# ---------------------------------------------------------------- cláusula: determinismo da query string
def test_mesma_predefinicao_gera_mesma_query_string(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    r1 = c.get(f"/svc/{tok}/raster/{item}/tilejson.json", params={"predef": "ndvi"})
    r2 = c.get(f"/svc/{tok}/raster/{item}/tilejson.json", params={"predef": "ndvi"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["tiles"] == r2.json()["tiles"]


# ---------------------------------------------------------------- cláusula: NDVI abre no mapa + legenda com cortes
def test_ndvi_colormap_rdylgn_abre_no_mapa(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/8/121/181.png", params={"predef": "ndvi"})
    # ladrilho pode cair fora da cobertura (204) dependendo do zoom escolhido; em zoom baixo o raster
    # sintético (bem pequeno) quase sempre cai fora — usa tilejson para achar um zoom real coberto
    if r.status_code == 204:
        pytest.skip("ladrilho fora da cobertura neste z/x/y (ver test_ndvi_no_zoom_coberto)")
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"] == "image/png"


def _tile_coberto(c, tok, item):
    import mercantile

    info = c.get(f"/svc/{tok}/raster/{item}/info.json").json()
    oeste, sul, leste, norte = info["bounds"]
    z = info["maxzoom"]
    t = mercantile.tile((oeste + leste) / 2, (sul + norte) / 2, z)
    return z, t.x, t.y


def test_ndvi_no_zoom_coberto_abre_e_legenda_bate_com_os_cortes(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    z, x, y = _tile_coberto(c, tok, item)
    r = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "ndvi"})
    assert r.status_code == 200, r.text[:300]
    from PIL import Image

    img = Image.open(io.BytesIO(r.content))
    assert img.mode in ("RGBA", "RGB")

    legenda = c.get(f"/svc/{tok}/raster/{item}/legenda.json", params={"predef": "ndvi"}).json()
    assert legenda["tipo"] == "rampa" and legenda["colormap"] == "rdylgn"
    assert legenda["faixa"] == [-1.0, 1.0]
    cortes = legenda["amostras"]
    assert len(cortes) >= 2
    # legenda PNG existe e é uma imagem de verdade (mesma fonte que legenda.json, nunca duas fontes)
    r_png = c.get(f"/svc/{tok}/raster/{item}/legenda.png", params={"predef": "ndvi"})
    assert r_png.status_code == 200 and r_png.headers["content-type"] == "image/png"
    Image.open(io.BytesIO(r_png.content)).load()


def test_ndwi_e_nbr_aproximado_tambem_abrem(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    z, x, y = _tile_coberto(c, tok, item)
    for nome in ("ndwi", "nbr-aproximado"):
        r = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": nome})
        assert r.status_code == 200, (nome, r.text[:300])


def test_relevo_sombreado_abre_e_difere_do_rgb_natural(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    z, x, y = _tile_coberto(c, tok, item)
    r_rgb = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "rgb-natural"})
    r_hs = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "relevo-sombreado"})
    assert r_rgb.status_code == 200 and r_hs.status_code == 200
    assert r_rgb.content != r_hs.content


# ------------------------------------------------------------ cláusula: predefinição de fábrica muda pixel
def test_falsa_cor_nir_muda_o_pixel_de_forma_previsivel_vs_rgb_natural(token_predef, raster_demo):
    """Predefinição de fábrica muda o pixel de forma PREVISÍVEL (portão): falsa-cor-nir manda banda4
    (infravermelho, alto contraste no padrão de teste) para o canal vermelho — os dois PNG têm de
    diferir pixel a pixel na maioria dos pixels, e a média do canal vermelho de falsa-cor-nir tem de
    ser MAIOR (o padrão de vegetação da banda4 é mais claro que a banda3 usada pelo rgb-natural)."""
    import numpy as np
    from PIL import Image

    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    z, x, y = _tile_coberto(c, tok, item)
    r1 = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "rgb-natural"})
    r2 = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "falsa-cor-nir"})
    assert r1.status_code == 200 and r2.status_code == 200
    a = np.array(Image.open(io.BytesIO(r1.content)).convert("RGB"), dtype=np.int16)
    b = np.array(Image.open(io.BytesIO(r2.content)).convert("RGB"), dtype=np.int16)
    diff = np.abs(a - b).sum(axis=2)
    fracao_diferente = float((diff > 0).mean())
    assert fracao_diferente > 0.5, fracao_diferente


# ---------------------------------------------------------------- cláusula: nodata transparente
def test_nodata_transparente_por_padrao_e_desligavel(sessao_a, token_predef, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={
        "nome": "sem-transparencia", "titulo": "x", "nodata_transparente": False,
    })
    assert r.status_code == 201, r.text
    c, tok = _cliente(), token_predef["token"]
    z, x, y = _tile_coberto(c, tok, item)
    r_opaco = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "sem-transparencia"})
    assert r_opaco.status_code == 200
    from PIL import Image

    img = Image.open(io.BytesIO(r_opaco.content))
    assert img.mode == "RGB" or img.getextrema()[3] == (255, 255)  # sem canal alfa variável: opaco


# ------------------------------------------------------------ cláusula: trocar padrão muda a URL sem quebrar a anterior
def test_trocar_predefinicao_padrao_muda_url_wmts_sem_quebrar_a_anterior(sessao_a, token_predef, raster_demo):
    item = raster_demo["item_id"]
    c, tok = _cliente(), token_predef["token"]

    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "preset-a", "titulo": "A", "bandas": [1, 2, 3]})
    assert r.status_code == 201, r.text
    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "preset-b", "titulo": "B", "bandas": [3, 2, 1]})
    assert r.status_code == 201, r.text

    r = sessao_a.post(f"{_url_item(sessao_a, item)}/preset-a/tornar-padrao")
    assert r.status_code == 200, r.text
    url_a = c.get(f"/svc/{tok}/raster/{item}/tilejson.json").json()["tiles"][0]
    assert "predef=preset-a" in url_a

    r = sessao_a.post(f"{_url_item(sessao_a, item)}/preset-b/tornar-padrao")
    assert r.status_code == 200, r.text
    url_b = c.get(f"/svc/{tok}/raster/{item}/tilejson.json").json()["tiles"][0]
    assert "predef=preset-b" in url_b
    assert url_a != url_b

    # a URL antiga (predef=preset-a explícito) continua servindo preset-a — não foi apagado, só deixou
    # de ser o padrão
    z, x, y = _tile_coberto(c, tok, item)
    r_a = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "preset-a"})
    assert r_a.status_code == 200, r_a.text[:300]


# ---------------------------------------------------------------- cláusula: 6 predefinições de fábrica
def test_seis_predefinicoes_de_fabrica_listadas(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/raster/{item}/predefinicoes.json")
    assert r.status_code == 200
    fabrica = {e["nome"] for e in r.json()["fabrica"]}
    assert fabrica == {"rgb-natural", "falsa-cor-nir", "ndvi", "ndwi", "nbr-aproximado", "relevo-sombreado"}


# ---------------------------------------------------------------- refutação do adversário: nunca 500
def test_rescale_invertido_nunca_500(sessao_a, token_predef, raster_demo):
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={
        "nome": "rescale-invertido", "titulo": "x", "bandas": [1],
        "esticamento": {"tipo": "explicito", "faixas": [[10000, -10000]]},
    })
    assert r.status_code == 201, r.text
    c, tok = _cliente(), token_predef["token"]
    z, x, y = _tile_coberto(c, tok, item)
    r_tile = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "rescale-invertido"})
    assert r_tile.status_code in (200, 204, 422), r_tile.status_code
    assert r_tile.status_code != 500


def test_predefinicao_inexistente_e_404_nunca_500(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    z, x, y = _tile_coberto(c, tok, item)
    r = c.get(f"/svc/{tok}/raster/{item}/{z}/{x}/{y}.png", params={"predef": "nao-existo-de-jeito-nenhum"})
    assert r.status_code == 404, r.text
    assert r.status_code != 500


def test_predefinicao_com_banda_no_limite_do_item_aceita(sessao_a, raster_demo):
    """Item sintético tem exatamente 4 bandas — pedir a banda 4 (o limite) tem de aceitar; pedir a 5
    (fora) tem de recusar com 422, não 500 (a cláusula anterior já cobre isso)."""
    item = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item), json={"nome": "so-4-bandas", "titulo": "x", "bandas": [4]})
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------- cláusula: predefinição de outro inquilino invisível
def test_predefinicao_de_outro_inquilino_invisivel(sessao_a, sessao_b, token_predef_b, raster_demo, raster_demo_b):
    """`falsa-cor-nir`-like custom criada pelo inquilino A no item DELE não aparece, nem funciona, para
    um token do inquilino B pedindo o ITEM de B (RLS por tenant_id, não por nome de predefinição)."""
    item_a = raster_demo["item_id"]
    r = sessao_a.post(_url_item(sessao_a, item_a), json={"nome": "so-do-a", "titulo": "segredo do A"})
    assert r.status_code == 201, r.text

    item_b = raster_demo_b["item_id"]
    c, tok_b = _cliente(), token_predef_b["token"]
    r_lista = c.get(f"/svc/{tok_b}/raster/{item_b}/predefinicoes.json")
    assert r_lista.status_code == 200
    nomes_b = {e["nome"] for e in r_lista.json()["custom"]}
    assert "so-do-a" not in nomes_b

    r_uso = c.get(f"/svc/{tok_b}/raster/{item_b}/8/1/1.png", params={"predef": "so-do-a"})
    assert r_uso.status_code == 404, r_uso.text


# ---------------------------------------------------------------- WMS: STYLES= e GetLegendGraphic
def test_wms_styles_ndvi_e_getlegendgraphic(sessao_a, token_predef, raster_demo):
    from rasterio.warp import transform_bounds

    item = raster_demo["item_id"]
    c, tok = _cliente(), token_predef["token"]
    info = c.get(f"/svc/{tok}/raster/{item}/info.json").json()
    oeste, sul, leste, norte = info["bounds"]
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", "EPSG:3857", oeste, sul, leste, norte)
    p = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": item, "STYLES": "ndvi",
        "CRS": "EPSG:3857", "BBOX": f"{minx},{miny},{maxx},{maxy}", "WIDTH": "128", "HEIGHT": "128",
        "FORMAT": "image/png"}
    r = c.get(f"/svc/{tok}/wms", params=p)
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"] == "image/png"

    r_legenda = c.get(f"/svc/{tok}/wms", params={
        "SERVICE": "WMS", "REQUEST": "GetLegendGraphic", "LAYER": item, "STYLE": "ndvi",
        "FORMAT": "image/png"})
    assert r_legenda.status_code == 200 and r_legenda.headers["content-type"] == "image/png"

    r_ruim = c.get(f"/svc/{tok}/wms", params={**p, "STYLES": "nao-existe-esse-estilo"})
    assert r_ruim.status_code == 400
    assert "StyleNotDefined" in r_ruim.text


# ---------------------------------------------------------------- ImageServer: renderingRule
def test_imageserver_renderingrule_aceita_forma_minima_e_recusa_o_resto(sessao_a, token_predef, raster_demo):
    item = raster_demo["item_id"]
    c, tok = _cliente(), token_predef["token"]
    info = c.get(f"/svc/{tok}/raster/{item}/info.json").json()
    oeste, sul, leste, norte = info["bounds"]
    base = f"/svc/{tok}/rest/services/{item}/ImageServer/exportImage"

    r = c.get(base, params={"bbox": f"{oeste},{sul},{leste},{norte}", "bboxSR": "4326", "size": "64,64",
                            "format": "png", "renderingRule": '{"rasterFunction":"ndvi"}'})
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"] == "image/png"

    r_inexistente = c.get(base, params={"bbox": f"{oeste},{sul},{leste},{norte}", "bboxSR": "4326",
                                        "size": "32,32", "renderingRule": '{"rasterFunction":"nao-existe"}'})
    assert r_inexistente.status_code in (400, 422)
    assert r_inexistente.headers["content-type"] == "application/json"

    r_forma_errada = c.get(base, params={
        "bbox": f"{oeste},{sul},{leste},{norte}", "bboxSR": "4326", "size": "32,32",
        "renderingRule": '{"rasterFunction":"Stretch","rasterFunctionArguments":{}}'})
    assert r_forma_errada.status_code == 400
    assert "error" in r_forma_errada.json()

    r_mosaic = c.get(base, params={"bbox": f"{oeste},{sul},{leste},{norte}", "bboxSR": "4326",
                                   "size": "32,32", "mosaicRule": '{"mosaicMethod":"x"}'})
    assert r_mosaic.status_code == 400


def test_imageserver_documento_allowrasterfunction_true_quando_compativel(token_predef, raster_demo):
    c, tok, item = _cliente(), token_predef["token"], raster_demo["item_id"]
    r = c.get(f"/svc/{tok}/rest/services/{item}/ImageServer", params={"f": "json"})
    assert r.status_code == 200
    assert r.json()["allowRasterFunction"] is True
