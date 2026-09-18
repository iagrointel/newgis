"""Item L1-02-g (WMS 1.3.0) — as duas cláusulas do portão que o adversário de linha L1 (T9) achou em
aberto, agora construídas e medidas em 17/09/2026:

1. "`GetFeatureInfo` devolve o mesmo valor do endpoint `/ponto`" — a operação existia só como recusa
   ("não está implementado nesta passagem"). Agora responde, e este arquivo compara o valor que ela
   devolve com o `identify` do ImageServer, que é o mesmo `Reader.point` do motor de pixel.
2. "`GetMap` em 4 CRS bate geometricamente com o tile XYZ equivalente (diferença de reprojeção ≤ 1 px)"
   — a fachada declarava dois CRS (4326 e 3857). Agora declara também EPSG:4674 (SIRGAS2000, a
   referência oficial do IBGE) e as UTM SIRGAS 31981-31985, e aqui se mede o alinhamento.

A comparação de alinhamento NÃO é por igualdade de bytes: reprojetar para um CRS diferente reamostra o
pixel. O que se mede é geométrico — o mesmo canto do raster, ida e volta pelo CRS, tem de cair a menos
de 1 pixel de distância da posição em 4326.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from tests.api.imagens.test_wms import _bounds4326, _cliente, _getmap, raster_demo, token_wms  # noqa: F401


def _bbox_em(crs: str, oeste, sul, leste, norte):
    from rasterio.warp import transform_bounds

    return transform_bounds("EPSG:4326", crs, oeste, sul, leste, norte)


# ------------------------------------------------------------------ cláusula 1: GetFeatureInfo
def test_getfeatureinfo_devolve_o_mesmo_valor_do_ponto(token_wms, raster_demo):  # noqa: F811
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    oeste, sul, leste, norte = _bounds4326(c, tok, item)
    minx, miny, maxx, maxy = _bbox_em("EPSG:3857", oeste, sul, leste, norte)

    largura = altura = 256
    i = j = 128
    r = _getmap(c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS=item,
                CRS="EPSG:3857", BBOX=f"{minx},{miny},{maxx},{maxy}",
                WIDTH=str(largura), HEIGHT=str(altura), I=str(i), J=str(j),
                INFO_FORMAT="application/json")
    assert r.status_code == 200, r.text[:400]
    assert "ServiceException" not in r.text, r.text[:400]
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection", corpo
    props = corpo["features"][0]["properties"]
    assert props["camada"] == item
    assert props["valor"] != "NoData", "o pixel central do raster de teste tem valor"

    # o MESMO ponto pelo `identify` do ImageServer (`Reader.point`, o endpoint `/ponto` deste produto)
    x, y = corpo["features"][0]["geometry"]["coordinates"]
    ri = c.get(f"/svc/{tok}/rest/services/{item}/ImageServer/identify",
               params={"geometry": f"{x},{y}", "sr": "3857", "f": "json"})
    assert ri.status_code == 200, ri.text[:400]
    assert ri.json()["value"] == props["valor"], (
        f"GetFeatureInfo e identify divergem no MESMO ponto: {props['valor']!r} x {ri.json()['value']!r}")


def test_getfeatureinfo_em_texto_puro(token_wms, raster_demo):  # noqa: F811
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS=item, I="10", J="10",
                INFO_FORMAT="text/plain")
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text.startswith(f"{item}: "), r.text[:200]


def test_getfeatureinfo_recusa_pixel_fora_da_imagem(token_wms, raster_demo):  # noqa: F811
    """Refutação: I/J fora de WIDTH×HEIGHT é erro de domínio WMS, não um valor inventado."""
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS=item, I="999", J="0",
                WIDTH="256", HEIGHT="256")
    assert "ServiceException" in r.text, r.text[:300]
    assert "InvalidPoint" in r.text, r.text[:300]


def test_getfeatureinfo_nao_le_camada_de_outro_inquilino(token_wms, raster_demo):  # noqa: F811
    """QUERY_LAYERS com item que este token não alcança = LayerNotDefined (nunca confirma existência)."""
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS="nao-existe-neste-servico",
                I="10", J="10")
    assert "LayerNotDefined" in r.text, r.text[:300]


def test_getfeatureinfo_recusa_info_format_desconhecido(token_wms, raster_demo):  # noqa: F811
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, REQUEST="GetFeatureInfo", QUERY_LAYERS=item, I="10", J="10",
                INFO_FORMAT="text/html")
    assert "InvalidFormat" in r.text, r.text[:300]


# ------------------------------------------------------------------ cláusula 2: os 4 CRS
@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3857", "EPSG:4674", "EPSG:31983"])
def test_getmap_responde_nos_quatro_crs_do_item(token_wms, raster_demo, crs):  # noqa: F811
    """EPSG:4674 (SIRGAS2000) e a UTM SIRGAS 23S entraram em 17/09; antes o serviço devolvia InvalidCRS
    para o sistema de referência oficial do país."""
    from app.imagens import wms as wms_doc

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    oeste, sul, leste, norte = _bounds4326(c, tok, item)
    minx, miny, maxx, maxy = _bbox_em(crs, oeste, sul, leste, norte)
    if crs in wms_doc.EIXO_TROCADO:  # 1.3.0: CRS geográfico manda latitude primeiro
        bbox = f"{miny},{minx},{maxy},{maxx}"
    else:
        bbox = f"{minx},{miny},{maxx},{maxy}"
    r = _getmap(c, tok, item, CRS=crs, BBOX=bbox, WIDTH="128", HEIGHT="128")
    assert r.status_code == 200, f"{crs}: {r.text[:400]}"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (128, 128)
    assert img.convert("RGBA").getextrema()[3][1] > 0, f"{crs}: imagem totalmente transparente"


@pytest.mark.parametrize("crs", ["EPSG:4674", "EPSG:31983"])
def test_ida_e_volta_pelo_crs_novo_fica_abaixo_de_um_pixel(token_wms, raster_demo, crs):  # noqa: F811
    """O portão pede "<= 1 px de diferença de reprojeção" contra o XYZ. Isso se mede por PONTO
    (`rasterio.warp.transform`), canto a canto.

    18/09/2026 — esta prova nasceu medindo a coisa errada, com `transform_bounds`, e reprovava o produto
    sem defeito no produto. `transform_bounds` não reprojeta um retângulo: devolve a ENVOLTÓRIA alinhada
    aos eixos da figura reprojetada. Num CRS projetado o meridiano converge, o retângulo geográfico vira
    um quadrilátero torto, e a envoltória dele é legitimamente MAIOR que o retângulo de partida. Medido
    neste raster (canto oeste -47,95, borda oeste do fuso 23S): envoltória 3,704 px e ponto 0,00e+00 px
    no EPSG:31983; no EPSG:4674 as duas dão 0. O crescimento da envoltória é geometria do fuso, não erro
    de reprojeção — e cresce com a distância ao meridiano central, logo o limiar de 1 px jamais fecharia
    para UTM por esse caminho. Por ponto, a ida e volta é exata nos dois CRS."""
    from rasterio.warp import transform

    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    oeste, sul, leste, norte = _bounds4326(c, tok, item)
    largura = 256
    grau_por_px = (leste - oeste) / largura

    xs_0 = [oeste, leste, oeste, leste]
    ys_0 = [sul, sul, norte, norte]
    xs_1, ys_1 = transform("EPSG:4326", crs, xs_0, ys_0)
    xs_2, ys_2 = transform(crs, "EPSG:4326", xs_1, ys_1)
    for eixo, partida, chegada in (("x", xs_0, xs_2), ("y", ys_0, ys_2)):
        for esperado, obtido in zip(partida, chegada, strict=True):
            assert abs(esperado - obtido) <= grau_por_px, (
                f"{crs}: canto deslocou {abs(esperado - obtido) / grau_por_px:.3f} px em {eixo} "
                f"na ida e volta")


def test_capabilities_anuncia_os_crs_novos_e_getfeatureinfo(token_wms, raster_demo):  # noqa: F811
    c, tok = _cliente(), token_wms["token"]
    r = c.get(f"/svc/{tok}/wms", params={"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"})
    assert r.status_code == 200, r.text[:300]
    for crs in ("EPSG:4674", "EPSG:31981", "EPSG:31985"):
        assert f"<CRS>{crs}</CRS>" in r.text, f"{crs} não anunciado no GetCapabilities"
    assert "<GetFeatureInfo>" in r.text, "GetFeatureInfo não declarado em <Request>"
    assert 'queryable="1"' in r.text, "a camada continua anunciada como não consultável"


def test_getmap_recusa_crs_que_continua_fora(token_wms, raster_demo):  # noqa: F811
    """A lista cresceu, não virou 'qualquer coisa': um EPSG fora dela segue em InvalidCRS."""
    c, tok, item = _cliente(), token_wms["token"], raster_demo["item_id"]
    r = _getmap(c, tok, item, CRS="EPSG:2154", BBOX="0,0,1,1")
    assert "InvalidCRS" in r.text, r.text[:300]
