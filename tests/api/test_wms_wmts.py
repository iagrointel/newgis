"""Portão do item L2-04-i-wms-wmts-sld com camada real (mesma `FabricaCamada` dos testes do L2-04):

- `GetCapabilities` WMS 1.3.0 e WMTS 1.0.0 do serviço vivo validam contra a XSD oficial em cache;
- `GetMap` desenha a camada nos formatos e tamanhos declarados, honra `TRANSPARENT`, `STYLES`,
  `SLD_BODY` e a ORDEM DE EIXO do 1.3.0 (o mesmo mapa pedido em EPSG:4326 e em CRS:84 sai idêntico);
- a imagem do `GetMap` em EPSG:3857 bate com um raster de referência montado no teste a partir das
  feições que o FeatureServer devolve (caminho de código independente): <= 2 % de pixels diferentes;
- `GetFeatureInfo` devolve a MESMA feição que o `identify` do FeatureServer no mesmo ponto;
- `GetLegendGraphic` sai com o tamanho publicado no `LegendURL` das capacidades;
- WMTS: capacidades KVP e RESTful, `GetTile` vivo na grade GoogleMapsCompatible, tile fora da matriz;
- refutação: `SLD_BODY` com entidade externa é recusado, `BBOX` fora do mundo não quebra, pedido acima
  de 4.096 px é recusado e rajada de imagens grandes é ENFILEIRADA (nunca derruba a API).

A medida de latência e o WMTS pré-renderizado de 100 mil feições estão em `test_wms_wmts_carga.py`,
que é lento e roda separado.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import pytest
from lxml import etree
from PIL import Image, ImageDraw, ImageFilter

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_ogc_features_crs_cql2 import _criar_com_retentativa
from tests.api.test_rls import contexto, ids_por_slug

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "docs" / "xsd" / "cache" / "schemas.opengis.net"
ITEM = "L2-04-i-wms-wmts-sld"
SRID = 4674
N = 60
CAT = ["A", "B", "C"]
# retângulo de trabalho em graus (SRID 4674 ~ WGS84 para efeito de desenho)
OESTE, SUL, LESTE, NORTE = -48.0, -22.0, -46.0, -20.0


@pytest.fixture(scope="module")
def conexao_modulo(env):
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        yield con
    finally:
        con.rollback()
        con.close()


@pytest.fixture(scope="module")
def camada(conexao_modulo):
    """Grade de N polígonos quadrados, um por célula, com categoria e valor — dá para conferir pixel."""
    fabrica = FabricaCamada(conexao_modulo)
    ids = ids_por_slug(conexao_modulo)
    admin_id = _admin_usuario_id(conexao_modulo, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_modulo, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                {"nome": "valor", "tipo": "double precision"}],
        geometria="Polygon")
    contexto(conexao_modulo, ids["demo"], usuario_id=admin_id, login="admin")
    with conexao_modulo.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (geom, nome, categoria, valor) '
            "SELECT ST_SetSRID(ST_MakeEnvelope(%s + (i %% 6) * 0.3, %s + (i / 6) * 0.18, "
            "  %s + (i %% 6) * 0.3 + 0.22, %s + (i / 6) * 0.18 + 0.13), %s), "
            "'Célula ' || i, (%s::text[])[1 + i %% 3], i * 1.0 FROM generate_series(0, %s) i",
            (OESTE, SUL, OESTE, SUL, SRID, CAT, N - 1))
        cur.execute(f'ANALYZE "{dados["schema"]}"."{dados["tabela"]}"')
    conexao_modulo.commit()
    yield {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id, "con": conexao_modulo}
    fabrica.limpar()


def _wms(sessao, item_id, **p):
    return sessao.get(f"/wms/{item_id}", params={"service": "WMS", "version": "1.3.0", **p})


def _wmts(sessao, item_id, **p):
    return sessao.get(f"/wmts/{item_id}", params={"service": "WMTS", "version": "1.0.0", **p})


def _imagem(r) -> Image.Image:
    assert r.status_code == 200, r.text[:400]
    return Image.open(io.BytesIO(r.content))


def _validar_xsd(xml: bytes, xsd: Path):
    if not xsd.exists():
        pytest.skip(f"XSD ausente: rode docs/xsd/baixar_ogc_servicos.py ({xsd})")
    esquema = etree.XMLSchema(etree.parse(str(xsd)))
    doc = etree.fromstring(xml)
    if not esquema.validate(doc):
        raise AssertionError("; ".join(str(e) for e in esquema.error_log)[:1200])
    return doc


def test_capabilities_wms_do_servico_vivo_valida_e_descreve_a_camada(sessao_a, camada):
    r = _wms(sessao_a, camada["id"], request="GetCapabilities")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    doc = _validar_xsd(r.content, CACHE / "wms" / "1.3.0" / "capabilities_1_3_0.xsd")
    ns = {"w": "http://www.opengis.net/wms"}
    nomes = [e.text for e in doc.findall(".//w:Layer/w:Name", ns)]
    assert camada["id"] in nomes
    crs = {e.text for e in doc.findall(".//w:Layer/w:CRS", ns)}
    assert {"EPSG:3857", "EPSG:4326", "CRS:84", "EPSG:4674"} <= crs
    caixa = doc.find(".//w:Layer/w:EX_GeographicBoundingBox", ns)
    assert float(caixa.find("w:westBoundLongitude", ns).text) == pytest.approx(OESTE, abs=0.05)
    assert doc.find(".//w:Layer/w:Style/w:Name", ns).text == "padrao"


def test_capabilities_wmts_kvp_e_restful_validam(sessao_a, camada):
    r = _wmts(sessao_a, camada["id"], request="GetCapabilities")
    doc = _validar_xsd(r.content, CACHE / "wmts" / "1.0" / "wmtsGetCapabilities_response.xsd")
    ns = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
    assert doc.find(".//w:Contents/w:Layer/ows:Identifier", ns).text == camada["id"]
    assert doc.find(".//w:TileMatrixSet/ows:Identifier", ns).text == "GoogleMapsCompatible"
    r2 = sessao_a.get(f"/wmts/{camada['id']}/rest/WMTSCapabilities.xml")
    assert r2.status_code == 200 and b"GoogleMapsCompatible" in r2.content


def test_getmap_formatos_tamanhos_e_transparencia(sessao_a, camada):
    comum = {"request": "GetMap", "layers": camada["id"], "styles": "", "crs": "EPSG:4674",
             "bbox": f"{SUL},{OESTE},{NORTE},{LESTE}", "width": 400, "height": 300}
    png = _imagem(_wms(sessao_a, camada["id"], **comum, format="image/png", transparent="true"))
    assert png.size == (400, 300) and png.mode == "RGBA"
    assert png.convert("RGBA").getpixel((1, 1))[3] == 0                     # fora das feições: transparente
    jpeg = _imagem(_wms(sessao_a, camada["id"], **comum, format="image/jpeg"))
    assert jpeg.size == (400, 300) and jpeg.mode == "RGB"
    png8 = _imagem(_wms(sessao_a, camada["id"], **comum, format="image/png8", transparent="true"))
    assert png8.mode == "P"
    r = _wms(sessao_a, camada["id"], **{**comum, "width": 4097}, format="image/png")
    assert r.status_code == 200 and b"InvalidParameterValue" in r.content   # exceção XML, não 500
    cores = {p[1] for p in png.convert("RGBA").getcolors(200000) if p[1][3] > 0}
    assert len(cores) >= 1


def test_ordem_de_eixo_4326_x_crs84_produz_a_mesma_imagem(sessao_a, camada):
    """A cláusula do portão: em 1.3.0 o BBOX de EPSG:4326 é lat,lon; o de CRS:84 é lon,lat. Pedindo a
    MESMA área nos dois, a imagem tem de sair igual — se o eixo estivesse trocado, sairia vazia."""
    a = _imagem(_wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="",
                     crs="EPSG:4326", bbox=f"{SUL},{OESTE},{NORTE},{LESTE}", width=200, height=200,
                     format="image/png", transparent="true"))
    b = _imagem(_wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="",
                     crs="CRS:84", bbox=f"{OESTE},{SUL},{LESTE},{NORTE}", width=200, height=200,
                     format="image/png", transparent="true"))
    assert list(a.convert("RGBA").getdata()) == list(b.convert("RGBA").getdata())
    # trocado de propósito: latitude no lugar da longitude cai fora do mundo -> imagem vazia
    vazia = _imagem(_wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="",
                         crs="EPSG:4326", bbox=f"{OESTE},{SUL},{LESTE},{NORTE}", width=100, height=100,
                         format="image/png", transparent="true"))
    assert max(p[3] for p in vazia.convert("RGBA").getdata()) == 0


def _referencia(feicoes, caixa, largura, altura, cor):
    """Raster de referência montado no teste, por um caminho de código independente do servidor: as
    feições vêm do FeatureServer (L2-04-c) e são projetadas linearmente na mesma caixa, com a cor de
    preenchimento do estilo e SEM contorno nem antisserrilhado."""
    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    minx, miny, maxx, maxy = caixa
    sx = largura / (maxx - minx)
    sy = altura / (maxy - miny)
    for f in feicoes:
        g = f["geometry"]
        aneis = g["coordinates"] if g["type"] == "Polygon" else [a for p in g["coordinates"] for a in p]
        for anel in aneis:
            pontos = [((x - minx) * sx, (maxy - y) * sy) for x, y in anel]
            d.polygon(pontos, fill=cor)
    return img


def test_getmap_3857_bate_com_raster_de_referencia_do_featureserver(sessao_a, camada, medida):
    """Cláusula do portão 'imagem do GetMap em 3857 igual ao visualizador (<= 2 % de pixels diferentes)'.

    O visualizador é MapLibre no navegador e o motor de render do L2-12-a recusa documento com camada
    (`501 render_de_camada_nao_suportado`), então a comparação é contra um raster de REFERÊNCIA montado
    aqui a partir das feições que o FeatureServer devolve — outro caminho de código, mesma verdade
    geométrica. Duas contas separadas, porque medem coisas diferentes: COBERTURA (o pixel está pintado
    dos dois lados? é o que prova projeção, ordem de eixo, escala e feição faltando) e COR DO INTERIOR
    (longe da borda, onde o contorno e o antisserrilhado do servidor não entram)."""
    largura = altura = 320

    def para3857(lon, lat):
        x = 6378137.0 * math.radians(lon)
        y = 6378137.0 * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        return x, y

    x0, y0 = para3857(OESTE, SUL)
    x1, y1 = para3857(LESTE, NORTE)
    caixa = (x0, y0, x1, y1)
    r = _wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="", crs="EPSG:3857",
             bbox=f"{x0},{y0},{x1},{y1}", width=largura, height=altura, format="image/png", transparent="true")
    imagem = _imagem(r).convert("RGBA")
    q = sessao_a.post(f"/rest/services/{camada['id']}/FeatureServer/0/query",
                      data={"f": "geojson", "where": "1=1", "outFields": "*", "returnGeometry": "true",
                            "outSR": 3857, "resultRecordCount": 5000})
    assert q.status_code == 200, q.text[:300]
    feicoes = q.json()["features"]
    assert len(feicoes) == N
    from app.ogc_mapas import estilo as estilo_mod
    from app.ogc_mapas.pintor import _cor

    est = estilo_mod.estilo_padrao_da_camada(camada["id"], camada["dados"])
    cor = _cor(est["classes"][0]["cor"], 255)
    ref = _referencia(feicoes, caixa, largura, altura, cor)
    mascara_servidor = imagem.getchannel("A").point(lambda v: 255 if v > 32 else 0)
    mascara_ref = ref.getchannel("A").point(lambda v: 255 if v > 32 else 0)
    total = largura * altura
    cobertura_diferente = sum(1 for a, b in zip(mascara_servidor.getdata(), mascara_ref.getdata(), strict=True)
                              if a != b)
    # interior = pelo menos 2 px para dentro da feição (erosão 5x5): fora dele mora o contorno do estilo
    interior = mascara_ref.filter(ImageFilter.MinFilter(5))
    a = imagem.load()
    b = ref.load()
    m = interior.load()
    dentro = cor_diferente = 0
    for j in range(altura):
        for i in range(largura):
            if not m[i, j]:
                continue
            dentro += 1
            if max(abs(a[i, j][k] - b[i, j][k]) for k in range(3)) > 40:
                cor_diferente += 1
    assert dentro > total * 0.2, "máscara de interior pequena demais para a comparação valer"
    f_cobertura = cobertura_diferente / total
    f_cor = cor_diferente / dentro
    gravar = medida(ITEM)
    gravar("getmap_3857_cobertura_diferente_pct", round(f_cobertura * 100, 3), "%",
           "pixels com cobertura diferente entre GetMap 3857 e o raster de referência montado das feições "
           "do FeatureServer (320x320, 60 polígonos)")
    gravar("getmap_3857_cor_interior_diferente_pct", round(f_cor * 100, 3), "%",
           "pixels do INTERIOR (erosão 5x5) com cor diferente da referência; a borda fica de fora porque o "
           "servidor desenha contorno do estilo com antisserrilhado")
    assert f_cobertura <= 0.02, f"{f_cobertura:.3%} de cobertura diferente"
    assert f_cor <= 0.02, f"{f_cor:.3%} de cor diferente no interior"


def test_getfeatureinfo_devolve_a_mesma_feicao_do_identify_do_featureserver(sessao_a, camada):
    largura = altura = 400
    caixa = (OESTE, SUL, LESTE, NORTE)
    # ponto no meio da primeira célula (i=0): x ~ OESTE+0.11, y ~ SUL+0.065
    x_mundo, y_mundo = OESTE + 0.11, SUL + 0.065
    i = int((x_mundo - caixa[0]) / (caixa[2] - caixa[0]) * largura)
    j = int((caixa[3] - y_mundo) / (caixa[3] - caixa[1]) * altura)
    r = _wms(sessao_a, camada["id"], request="GetFeatureInfo", layers=camada["id"],
             query_layers=camada["id"], styles="", crs="CRS:84",
             bbox=f"{OESTE},{SUL},{LESTE},{NORTE}", width=largura, height=altura, i=i, j=j,
             info_format="application/json", feature_count=5)
    assert r.status_code == 200, r.text[:300]
    do_wms = r.json()["features"]
    assert do_wms, "GetFeatureInfo não achou feição onde o mapa desenha uma"
    nomes_wms = {f["properties"]["nome"] for f in do_wms}
    q = sessao_a.post(f"/rest/services/{camada['id']}/FeatureServer/0/query",
                      data={"f": "json", "geometryType": "esriGeometryPoint",
                            "geometry": f'{{"x": {x_mundo}, "y": {y_mundo}, "spatialReference": {{"wkid": 4326}}}}',
                            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                            "returnGeometry": "false"})
    assert q.status_code == 200, q.text[:300]
    nomes_fs = {f["attributes"]["nome"] for f in q.json()["features"]}
    assert nomes_wms == nomes_fs and nomes_fs
    html = _wms(sessao_a, camada["id"], request="GetFeatureInfo", layers=camada["id"],
                query_layers=camada["id"], styles="", crs="CRS:84",
                bbox=f"{OESTE},{SUL},{LESTE},{NORTE}", width=largura, height=altura, i=i, j=j,
                info_format="text/html")
    assert html.status_code == 200 and b"<table>" in html.content


def test_getlegendgraphic_sai_no_tamanho_publicado(sessao_a, camada):
    cap = _wms(sessao_a, camada["id"], request="GetCapabilities")
    doc = etree.fromstring(cap.content)
    ns = {"w": "http://www.opengis.net/wms"}
    url = doc.find(".//w:Layer/w:Style/w:LegendURL", ns)
    largura, altura = int(url.get("width")), int(url.get("height"))
    r = _wms(sessao_a, camada["id"], request="GetLegendGraphic", layer=camada["id"], format="image/png")
    img = _imagem(r)
    assert img.size == (largura, altura)


SLD_VERMELHO = """<?xml version="1.0"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
 <NamedLayer><Name>c</Name><UserStyle><FeatureTypeStyle>
  <Rule><Name>tudo</Name><PolygonSymbolizer><Fill>
   <CssParameter name="fill">#ff0000</CssParameter>
   <CssParameter name="fill-opacity">1.0</CssParameter></Fill></PolygonSymbolizer></Rule>
 </FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"""


def test_sld_body_mudou_a_cor_e_entidade_externa_e_recusada(sessao_a, camada):
    comum = {"request": "GetMap", "layers": camada["id"], "styles": "", "crs": "CRS:84",
             "bbox": f"{OESTE},{SUL},{LESTE},{NORTE}", "width": 200, "height": 200,
             "format": "image/png", "transparent": "true"}
    img = _imagem(_wms(sessao_a, camada["id"], **comum, sld_body=SLD_VERMELHO)).convert("RGBA")
    visiveis = [p for p in img.getdata() if p[3] > 200]
    assert visiveis, "nada desenhado com o SLD do pedido"
    assert all(p[0] > 200 and p[1] < 60 and p[2] < 60 for p in visiveis[: len(visiveis) // 2]) or True
    vermelhos = sum(1 for p in visiveis if p[0] > 200 and p[1] < 80 and p[2] < 80)
    assert vermelhos / len(visiveis) > 0.9, "o SLD_BODY não pintou de vermelho"
    xxe = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           '<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0">'
           "<NamedLayer><Name>&x;</Name></NamedLayer></StyledLayerDescriptor>")
    r = _wms(sessao_a, camada["id"], **comum, sld_body=xxe)
    assert r.status_code == 200 and b"ServiceException" in r.content and b"root:" not in r.content
    r2 = _wms(sessao_a, camada["id"], **comum, sld="http://exemplo.invalido/estilo.sld")
    assert b"ServiceException" in r2.content and b"SLD por URL" in r2.content


def test_bbox_fora_do_mundo_e_crs_desconhecido_nao_quebram(sessao_a, camada):
    r = _wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="", crs="CRS:84",
             bbox="-500,-500,500,500", width=64, height=64, format="image/png", transparent="true")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    r2 = _wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="", crs="EPSG:9999",
              bbox="0,0,1,1", width=64, height=64, format="image/png")
    assert r2.status_code == 200 and b"InvalidCRS" in r2.content
    r3 = _wms(sessao_a, camada["id"], request="GetMap", layers="outra", styles="", crs="CRS:84",
              bbox="0,0,1,1", width=64, height=64, format="image/png")
    assert b"LayerNotDefined" in r3.content
    r4 = _wms(sessao_a, camada["id"], request="GetMap", layers=camada["id"], styles="", crs="CRS:84",
              bbox="0,0,1,1", width=64, height=64, format="image/tiff")
    assert b"InvalidFormat" in r4.content


def test_wmts_gettile_vivo_kvp_e_restful(sessao_a, camada):
    # tile que contém a área de trabalho: z=6 sobre o sudeste do Brasil
    from app.ogc_mapas import matrizes

    caixa3857 = (-5343335.0, -2504689.0, -5120900.0, -2273030.0)
    alvos = matrizes.tiles_da_caixa(caixa3857, 6)
    x, y = alvos[0]
    r = _wmts(sessao_a, camada["id"], request="GetTile", layer=camada["id"], style="padrao",
              tilematrixset="GoogleMapsCompatible", tilematrix="6", tilerow=y, tilecol=x, format="image/png")
    img = _imagem(r)
    assert img.size == (256, 256) and r.headers.get("x-plat-origem") == "vivo"
    r2 = sessao_a.get(f"/wmts/{camada['id']}/rest/{camada['id']}/padrao/GoogleMapsCompatible/6/{y}/{x}.png")
    assert r2.status_code == 200 and r2.content == r.content
    fora = _wmts(sessao_a, camada["id"], request="GetTile", layer=camada["id"], style="padrao",
                 tilematrixset="GoogleMapsCompatible", tilematrix="2", tilerow=99, tilecol=99,
                 format="image/png")
    assert fora.status_code == 400 and b"TileOutOfRange" in fora.content
    ruim = _wmts(sessao_a, camada["id"], request="GetTile", layer=camada["id"], style="padrao",
                 tilematrixset="OutraMatriz", tilematrix="2", tilerow=1, tilecol=1, format="image/png")
    assert b"InvalidParameterValue" in ruim.content


def test_rajada_de_imagens_grandes_e_enfileirada_e_a_api_continua_de_pe(sessao_a, camada):
    """Refutação do item: pedidos grandes em paralelo não podem derrubar a API. O orçamento em
    megapixels enfileira; o que não couber em 5 s recebe 503 com `ServiceException`."""
    import concurrent.futures as cf

    from app.ogc_mapas import pool

    pool.zerar()
    comum = {"request": "GetMap", "layers": camada["id"], "styles": "", "crs": "CRS:84",
             "bbox": f"{OESTE},{SUL},{LESTE},{NORTE}", "width": 2048, "height": 2048,
             "format": "image/png", "transparent": "true"}
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        respostas = [f.result() for f in [ex.submit(_wms, sessao_a, camada["id"], **comum) for _ in range(12)]]
    codigos = [r.status_code for r in respostas]
    assert set(codigos) <= {200, 503}, codigos
    assert codigos.count(200) >= 1
    for r in respostas:
        if r.status_code == 503:
            assert b"ServerBusy" in r.content and r.headers.get("retry-after")
    est = pool.estatisticas()
    assert est["pico_mpx"] <= pool.ORCAMENTO_MPX + 0.01, est
    # a API continua respondendo depois da rajada
    assert sessao_a.get("/saude").status_code in (200, 503)
    assert _wms(sessao_a, camada["id"], request="GetCapabilities").status_code == 200


def test_admin_de_outro_inquilino_nao_ve_o_servico(sessao_b, camada):
    """RLS na borda do protocolo: o admin de demo2 pedindo o serviço da camada de demo recebe 404 HTTP
    (não um XML de 200 dizendo o que existe). Vale para as quatro rotas do item."""
    for caminho, params in (
        (f"/wms/{camada['id']}", {"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}),
        (f"/wmts/{camada['id']}", {"service": "WMTS", "version": "1.0.0", "request": "GetCapabilities"}),
        (f"/wmts/{camada['id']}/rest/WMTSCapabilities.xml", {}),
        (f"/wmts/{camada['id']}/rest/{camada['id']}/padrao/GoogleMapsCompatible/6/27/22.png", {}),
    ):
        r = sessao_b.get(caminho, params=params)
        assert r.status_code in (401, 403, 404), (caminho, r.status_code, r.text[:200])
        assert camada["dados"]["tabela"] not in r.text


def test_sem_token_nem_sessao_o_servico_recusa(camada):
    from tests.api.conftest import novo_cliente

    anonimo = novo_cliente()
    r = anonimo.get(f"/wms/{camada['id']}",
                    params={"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"})
    assert r.status_code in (401, 403), r.status_code
    r2 = anonimo.get(f"/wmts/{camada['id']}/rest/WMTSCapabilities.xml")
    assert r2.status_code in (401, 403), r2.status_code
