"""Item L2-04-i-wms-wmts-sld, sem banco: as regras do protocolo que não dependem de dado.

- `GetCapabilities` WMS 1.3.0 e WMTS 1.0.0 gerados aqui validam contra a XSD OFICIAL do OGC em cache
  (`docs/xsd/cache`, baixada por `docs/xsd/baixar_ogc_servicos.py`), sem rede;
- ordem de eixo do WMS 1.3.0: em EPSG:4326/4674 o BBOX chega latitude primeiro, em EPSG:3857 e CRS:84
  não — é a diferença que mais quebra cliente entre 1.1.1 e 1.3.0;
- aritmética do TileMatrixSet GoogleMapsCompatible contra os números da especificação;
- leitor de SLD: subconjunto lido, semântica de feição sem regra e recusa de entidade externa (XXE);
- PMTiles: escreve, lê por FAIXA de bytes e devolve o mesmo tile (é assim que o WMTS pré-renderizado
  serve sem tocar no banco).
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import pytest
from lxml import etree

from app.ogc_mapas import capacidades, matrizes, sld_leitura
from app.ogc_mapas.pintor import classe_da_feicao, pintar
from app.ogc_mapas.rotas_wms import ErroWms, caixa_do_pedido, srid_do_crs

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "docs" / "xsd" / "cache" / "schemas.opengis.net"
XSD_WMS = CACHE / "wms" / "1.3.0" / "capabilities_1_3_0.xsd"
XSD_WMTS = CACHE / "wmts" / "1.0" / "wmtsGetCapabilities_response.xsd"

CAMADA = {
    "nome": "c1", "titulo": "Municípios de teste", "resumo": "camada de prova",
    "crs_nativo": "EPSG:4674", "extensao4326": (-53.1, -24.0, -44.2, -19.8),
    "extensao_nativa": (-53.1, -24.0, -44.2, -19.8),
    "estilos": [{"nome": "padrao", "titulo": "padrão", "padrao": True,
                 "legenda_url": "http://127.0.0.1/wms/x?request=GetLegendGraphic",
                 "legenda_largura": 120, "legenda_altura": 40}],
    "escala_min": None, "escala_max": None, "consultavel": True,
}


def _validar(xml: str, xsd: Path) -> None:
    if not xsd.exists():
        pytest.skip(f"XSD ausente: rode venv/bin/python docs/xsd/baixar_ogc_servicos.py ({xsd})")
    esquema = etree.XMLSchema(etree.parse(str(xsd)))
    doc = etree.fromstring(xml.encode("utf-8"))
    if not esquema.validate(doc):
        raise AssertionError("; ".join(str(e) for e in esquema.error_log)[:1500])


def test_capabilities_wms_valida_contra_xsd_oficial():
    xml = capacidades.wms_capabilities(base="http://127.0.0.1:8567/wms/abc", titulo_servico="plat",
                                       camadas=[CAMADA], inquilino="demo")
    _validar(xml, XSD_WMS)
    assert '<Name>c1</Name>' in xml and "<MaxWidth>4096</MaxWidth>" in xml
    # EX_GeographicBoundingBox é sempre lon/lat; o BoundingBox de EPSG:4326 é lat/lon (1.3.0)
    assert "<westBoundLongitude>-53.100000</westBoundLongitude>" in xml
    assert '<BoundingBox CRS="EPSG:4326" minx="-24.000000" miny="-53.100000"' in xml
    assert '<BoundingBox CRS="CRS:84" minx="-53.100000" miny="-24.000000"' in xml


def test_capabilities_wmts_valida_contra_xsd_oficial():
    xml = capacidades.wmts_capabilities(base="http://127.0.0.1:8567/wmts/abc",
                                        base_rest="http://127.0.0.1:8567/wmts/abc/rest",
                                        titulo_servico="plat", camadas=[CAMADA], z_max=14)
    _validar(xml, XSD_WMTS)
    assert "<ows:Identifier>GoogleMapsCompatible</ows:Identifier>" in xml
    assert "urn:ogc:def:crs:EPSG::3857" in xml and xml.count("<TileMatrix>") == 15


def test_excecoes_validam_contra_a_xsd_do_protocolo():
    xsd = CACHE / "wms" / "1.3.0" / "exceptions_1_3_0.xsd"
    _validar(capacidades.excecao_wms("InvalidCRS", "CRS não suportado: EPSG:9999"), xsd)
    xsd_ows = CACHE / "ows" / "1.1.0" / "owsExceptionReport.xsd"
    if xsd_ows.exists():
        _validar(capacidades.excecao_ows("TileOutOfRange", "tile fora da matriz"), xsd_ows)


def test_ordem_de_eixo_do_wms_130():
    # EPSG:4326: BBOX chega miny,minx,maxy,maxx (latitude primeiro)
    assert caixa_do_pedido("-24,-53.1,-19.8,-44.2", "EPSG:4326") == (-53.1, -24.0, -44.2, -19.8)
    assert caixa_do_pedido("-24,-53.1,-19.8,-44.2", "EPSG:4674") == (-53.1, -24.0, -44.2, -19.8)
    # CRS:84 e projetados mantêm x,y
    assert caixa_do_pedido("-53.1,-24,-44.2,-19.8", "CRS:84") == (-53.1, -24.0, -44.2, -19.8)
    assert caixa_do_pedido("-5000000,-3000000,-4000000,-2000000", "EPSG:3857") == (-5e6, -3e6, -4e6, -2e6)
    assert srid_do_crs("CRS:84") == 4326 and srid_do_crs("EPSG:31983") == 31983
    with pytest.raises(ErroWms):
        caixa_do_pedido("1,2,3", "EPSG:3857")
    with pytest.raises(ErroWms):
        caixa_do_pedido("10,10,0,0", "EPSG:3857")          # invertido


def test_matriz_google_bate_com_a_especificacao():
    # OGC 07-057r7 anexo E.4: z0 = 559082264.0287178, e cada nível divide por 2
    assert round(matrizes.denominador_escala(0), 4) == 559082264.0287
    assert round(matrizes.denominador_escala(1), 4) == round(559082264.0287178 / 2, 4)
    assert matrizes.caixa_do_tile(0, 0, 0) == (-matrizes.LIMITE, -matrizes.LIMITE, matrizes.LIMITE, matrizes.LIMITE)
    # y cresce para o SUL: o tile 1/0/0 é o quadrante NOROESTE
    minx, miny, maxx, maxy = matrizes.caixa_do_tile(1, 0, 0)
    assert (round(minx), round(miny), round(maxx), round(maxy)) == (-20037508, 0, 0, 20037508)
    assert len(matrizes.matrizes(0, 14)) == 15
    assert not matrizes.valido(2, 4, 0) and matrizes.valido(2, 3, 3)
    # a caixa de um tile, dividida em 256, dá exatamente o pixel_span do nível
    assert math.isclose((maxx - minx) / 256, matrizes.pixel_span(1), rel_tol=1e-12)


SLD_CATEGORIA = """<?xml version="1.0"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" version="1.0.0">
 <NamedLayer><Name>c</Name><UserStyle><FeatureTypeStyle>
  <Rule><Name>alto</Name>
   <ogc:Filter><ogc:PropertyIsGreaterThanOrEqualTo><ogc:PropertyName>v</ogc:PropertyName>
    <ogc:Literal>10</ogc:Literal></ogc:PropertyIsGreaterThanOrEqualTo></ogc:Filter>
   <PolygonSymbolizer><Fill><CssParameter name="fill">#ff0000</CssParameter></Fill></PolygonSymbolizer></Rule>
  <Rule><Name>resto</Name>
   <PolygonSymbolizer><Fill><CssParameter name="fill">#0000ff</CssParameter></Fill></PolygonSymbolizer></Rule>
 </FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"""


def test_sld_lido_no_subconjunto_e_regra_padrao_por_ultimo():
    d = sld_leitura.ler(SLD_CATEGORIA)
    assert d["geometria"] == "poligono" and d["padrao"] is True
    assert [c["rotulo"] for c in d["classes"]] == ["alto", "resto"]
    assert d["classes"][0]["teste"] == [">=", ["to-number", ["get", "v"]], 10.0]
    assert classe_da_feicao(d["classes"], {"v": 12})["cor"] == "#ff0000"
    assert classe_da_feicao(d["classes"], {"v": 1})["cor"] == "#0000ff"


def test_sld_sem_regra_padrao_nao_desenha_feicao_fora_das_regras():
    sem_padrao = SLD_CATEGORIA.replace(
        '<Rule><Name>resto</Name>\n   <PolygonSymbolizer><Fill><CssParameter name="fill">#0000ff</CssParameter>'
        "</Fill></PolygonSymbolizer></Rule>", "")
    d = sld_leitura.ler(sem_padrao)
    assert d["padrao"] is False
    assert classe_da_feicao(d["classes"], {"v": 1}, d["padrao"]) is None
    quadrado = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    _png, n = pintar([{"propriedades": {"v": 1}, "geometria": quadrado}], d, (-1, -1, 2, 2), 32, 32)
    assert n == 0


def test_sld_com_entidade_externa_e_recusado():
    xxe = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           '<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0">'
           "<NamedLayer><Name>&x;</Name></NamedLayer></StyledLayerDescriptor>")
    with pytest.raises(sld_leitura.SldInvalido):
        sld_leitura.ler(xxe)
    with pytest.raises(sld_leitura.SldInvalido):
        sld_leitura.ler("<html>não é sld</html>")
    with pytest.raises(sld_leitura.SldInvalido):
        sld_leitura.ler("x" * (sld_leitura.MAX_BYTES + 1))


def test_pmtiles_escreve_e_le_por_faixa_de_bytes():
    """O WMTS pré-renderizado depende disto: achar o tile lendo só o cabeçalho + o diretório + a faixa."""
    from pmtiles.tile import Compression, TileType, deserialize_directory, deserialize_header, find_tile, zxy_to_tileid
    from pmtiles.writer import Writer

    buf = io.BytesIO()
    w = Writer(buf)
    tiles = {(3, 2, 3): b"a" * 300, (3, 2, 4): b"b" * 300, (4, 5, 6): b"c" * 300}
    for (z, x, y), dados in sorted(tiles.items(), key=lambda kv: zxy_to_tileid(*kv[0])):
        w.write_tile(zxy_to_tileid(z, x, y), dados)
    w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 3, "max_zoom": 4,
                "min_lon_e7": -500000000, "min_lat_e7": -300000000, "max_lon_e7": -400000000,
                "max_lat_e7": -200000000, "center_zoom": 3, "center_lon_e7": -450000000,
                "center_lat_e7": -250000000}, {"nome": "x"})
    bruto = buf.getvalue()
    lidos = []

    def faixa(inicio, fim):
        lidos.append(fim - inicio + 1)
        return bruto[inicio:fim + 1]

    cab = deserialize_header(faixa(0, 126))
    raiz = deserialize_directory(faixa(cab["root_offset"], cab["root_offset"] + cab["root_length"] - 1))
    for (z, x, y), esperado in tiles.items():
        e = find_tile(raiz, zxy_to_tileid(z, x, y))
        t0 = cab["tile_data_offset"] + e.offset
        assert faixa(t0, t0 + e.length - 1) == esperado
    assert find_tile(raiz, zxy_to_tileid(3, 0, 0)) is None       # tile ausente = área sem feição
    assert max(lidos) < len(bruto)                               # nunca baixou o arquivo inteiro
