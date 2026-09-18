"""Item L1-25 (ImageServer compatível Esri) — as duas cláusulas do portão que o adversário de linha L1
(T9) achou em aberto, construídas e medidas em 17/09/2026:

1. "`exportImage` ... devolve PNG/JPEG/TIFF alinhado ao XYZ (≤ 1 px)". O serviço só aceitava png/jpg; o
   próprio teste de fechamento do item usava `format=tiff` como exemplo de formato RECUSADO.
2. "`mosaicRule` limitada às [regras] do L1-08". O serviço recusava QUALQUER mosaicRule não-vazia.

O TIFF sai no dtype nativo do recorte (é isso que distingue TIFF de PNG aqui: o valor, não a figura), e
o alinhamento é medido contra o PNG do MESMO bbox — mesma origem, mesmo tamanho de pixel.
"""

from __future__ import annotations

import io
import json

from tests.api.imagens.test_imageserver_token import _base, raster_demo, token_img  # noqa: F401

BBOX = "-47.95,-15.94,-47.76,-15.75"


def _cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, base_url="http://testserver")


def _export(c, tok, item, **extra):
    p = {"bbox": BBOX, "bboxSR": "4326", "size": "256,256", "format": "png", "f": "image"}
    p.update(extra)
    return c.get(f"{_base(tok, item)}/exportImage", params=p)


# ------------------------------------------------------------------ cláusula 1: TIFF
def test_export_image_devolve_tiff_georreferenciado(token_img, raster_demo):  # noqa: F811
    import rasterio

    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = _export(c, tok, item, format="tiff")
    assert r.status_code == 200, r.text[:400]
    assert r.headers["content-type"].startswith("image/tif"), r.headers.get("content-type")
    with rasterio.open(io.BytesIO(r.content)) as src:
        assert (src.width, src.height) == (256, 256)
        assert src.crs is not None, "o TIFF exportado tem de sair georreferenciado"
        assert src.count >= 1


def test_tiff_preserva_o_dtype_nativo_enquanto_o_png_vira_8_bits(token_img, raster_demo):  # noqa: F811
    """A razão de existir o formato: o COG de teste é uint16; o PNG precisa esticar para 8 bits para
    virar figura, o TIFF não pode."""
    import rasterio
    from PIL import Image

    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    rt = _export(c, tok, item, format="tiff")
    assert rt.status_code == 200, rt.text[:300]
    with rasterio.open(io.BytesIO(rt.content)) as src:
        dtype_tiff = src.dtypes[0]
        maximo = int(src.read(1).max())
    assert dtype_tiff == "uint16", f"o recorte devia sair no dtype nativo do COG; saiu {dtype_tiff}"
    assert maximo > 255, f"valor máximo {maximo} — o TIFF foi esticado para 8 bits, não devia"

    rp = _export(c, tok, item, format="png")
    assert rp.status_code == 200
    assert Image.open(io.BytesIO(rp.content)).mode in ("RGB", "RGBA", "L", "LA")


def test_tiff_e_png_cobrem_o_mesmo_retangulo(token_img, raster_demo):  # noqa: F811
    """Alinhamento (portão: ≤ 1 px): o TIFF do mesmo bbox tem de ter a MESMA extensão do pedido, com
    erro abaixo de um pixel do recorte."""
    import rasterio

    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    r = _export(c, tok, item, format="tiff")
    assert r.status_code == 200, r.text[:300]
    xmin, ymin, xmax, ymax = (float(v) for v in BBOX.split(","))
    with rasterio.open(io.BytesIO(r.content)) as src:
        b = src.bounds
        px_x = (xmax - xmin) / 256
        px_y = (ymax - ymin) / 256
    assert abs(b.left - xmin) <= px_x and abs(b.right - xmax) <= px_x, (b, xmin, xmax)
    assert abs(b.bottom - ymin) <= px_y and abs(b.top - ymax) <= px_y, (b, ymin, ymax)


# ------------------------------------------------------------------ cláusula 2: mosaicRule
def test_mosaic_rule_lock_do_proprio_item_e_aceito(token_img, raster_demo):  # noqa: F811
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    regra = json.dumps({"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [item]})
    r = _export(c, tok, item, mosaicRule=regra)
    assert r.status_code == 200, r.text[:400]
    assert r.headers["content-type"] == "image/png"
    assert "X-Plat-Mosaic-Rule" in r.headers, "a regra foi aceita sem dizer o que fez com ela"


def test_mosaic_rule_none_e_operacao_do_l1_08_sao_aceitas(token_img, raster_demo):  # noqa: F811
    from app.imagens import mosaico as mos

    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    for regra in (
        {"mosaicMethod": "esriMosaicNone"},
        {"mosaicMethod": "esriMosaicNone", "mosaicOperation": "MT_MEDIAN"},
        {"mosaicMethod": "esriMosaicAttribute", "sortField": "datetime"},
    ):
        r = _export(c, tok, item, mosaicRule=json.dumps(regra))
        assert r.status_code == 200, f"{regra}: {r.text[:300]}"
    # e a tradução é a do L1-08, não uma segunda tabela
    assert mos.traduzir_regra_esri({"mosaicMethod": "esriMosaicNone", "mosaicOperation": "MT_MEDIAN"},
                                   [item])["pixel_selection"] == "median"
    assert set(mos.OPERACOES_ESRI.values()) <= set(mos.SELECOES_PIXEL)


def test_mosaic_rule_com_lock_de_outro_raster_e_recusada(token_img, raster_demo):  # noqa: F811
    """Refutação literal do item: `lockRasterIds` de outro inquilino. O serviço só conhece a própria
    cena, então qualquer id que não seja o dele é recusado — nunca 200."""
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    regra = json.dumps({"mosaicMethod": "esriMosaicLockRaster",
                        "lockRasterIds": ["cena-de-outro-inquilino"]})
    r = _export(c, tok, item, mosaicRule=regra)
    assert r.status_code == 400, r.text[:300]
    assert r.json()["error"]["code"] == 400
    assert "lockRasterIds" in r.json()["error"]["message"], r.text[:300]


def test_mosaic_rule_malformada_nunca_da_500(token_img, raster_demo):  # noqa: F811
    c, tok, item = _cliente(), token_img["token"], raster_demo["item_id"]
    for bruto in ("{", "[]", '{"mosaicMethod":"esriMosaicLockRaster"}',
                  '{"mosaicMethod":"esriMosaicLockRaster","lockRasterIds":[]}',
                  '{"mosaicMethod":"esriMosaicAttribute"}',
                  '{"mosaicMethod":"esriMosaicNone","mosaicOperation":"MT_BLEND"}'):
        r = _export(c, tok, item, mosaicRule=bruto)
        assert r.status_code == 400, f"{bruto!r} -> {r.status_code}"
        assert "error" in r.json(), r.text[:200]


def test_paridade_declara_os_sete_metodos_esri():
    """O portão do L1-08 pede os 7 métodos do Esri declarados individualmente; a tabela que o código usa
    é a mesma que a documentação publica."""
    from app.imagens import mosaico as mos

    sete = {"esriMosaicNone", "esriMosaicCenter", "esriMosaicAttribute", "esriMosaicLockRaster",
            "esriMosaicNorthwest", "esriMosaicSeamline", "esriMosaicViewpoint"}
    assert sete <= (set(mos.METODOS_ESRI) | set(mos.METODOS_ESRI_FORA)), sete - (
        set(mos.METODOS_ESRI) | set(mos.METODOS_ESRI_FORA))
    for nome, motivo in mos.METODOS_ESRI_FORA.items():
        assert motivo.strip(), f"{nome} declarado FORA sem motivo escrito"
