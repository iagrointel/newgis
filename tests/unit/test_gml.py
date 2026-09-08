"""Portão do item L2-04-h, parte de GML 3.2: o XSD que o `DescribeFeatureType` publica e o
documento que o `GetFeature` devolve são a mesma decisão, e o teste prova isso do jeito duro —
compila o XSD gerado contra o GML 3.2.1 OFICIAL em cache (docs/xsd/cache, baixado por
`docs/xsd/baixar_iso19139.py --perfil wfs20`, nunca da rede) e valida o documento contra ele."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from lxml import etree

from app.consulta import gml

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "docs" / "xsd" / "cache" / "schemas.opengis.net"
GML_LOCAL = CACHE / "gml" / "3.2.1" / "gml.xsd"
WFS_LOCAL = CACHE / "wfs" / "2.0" / "wfs.xsd"

META = [
    {"nome": "fid", "tipo_pg": "integer", "tipo_esri": "esriFieldTypeOID", "papel": "oid",
     "nullable": False, "comprimento": None},
    {"nome": "nome", "tipo_pg": "text", "tipo_esri": "esriFieldTypeString", "papel": "atributo",
     "nullable": True, "comprimento": 255},
    {"nome": "area", "tipo_pg": "double precision", "tipo_esri": "esriFieldTypeDouble",
     "papel": "atributo", "nullable": True, "comprimento": None},
]
ITEM = str(uuid.UUID("11111111-2222-3333-4444-555555555555"))


def _esquema_local(xsd_texto: str) -> etree.XMLSchema:
    """O XSD publicado aponta para o gml.xsd oficial (é o que GeoServer e ArcGIS fazem); para
    validar sem rede, o teste troca a URL pelo caminho do cache."""
    local = xsd_texto.replace("http://schemas.opengis.net/gml/3.2.1/gml.xsd", GML_LOCAL.as_uri())
    return etree.XMLSchema(etree.fromstring(local.encode("utf-8")))


@pytest.fixture(scope="module")
def cache_presente():
    if not GML_LOCAL.exists() or not WFS_LOCAL.exists():
        pytest.fail("cache de XSD ausente: rode docs/xsd/baixar_iso19139.py --perfil wfs20")
    return True


def _geojson(geometria: dict) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 1, "geometry": geometria,
         "properties": {"fid": 1, "nome": "um", "area": 10.5}}]}


def test_xsd_gerado_compila_contra_o_gml_oficial(cache_presente):
    for geometria in ("Point", "MultiPolygon", "MultiLineString", None):
        esquema = _esquema_local(gml.descrever_tipo(ITEM, META, geometria))
        assert esquema is not None


@pytest.mark.parametrize(
    ("tipo_camada", "geometria", "elemento"),
    [
        ("Point", {"type": "Point", "coordinates": [-49.1, -27.1]}, "Point"),
        ("MultiPoint", {"type": "MultiPoint", "coordinates": [[-49.1, -27.1], [-49.2, -27.2]]},
         "MultiPoint"),
        ("LineString", {"type": "LineString", "coordinates": [[-49.1, -27.1], [-49.2, -27.2]]},
         "LineString"),
        ("MultiLineString", {"type": "MultiLineString",
                              "coordinates": [[[-49.1, -27.1], [-49.2, -27.2]]]}, "MultiCurve"),
        ("Polygon", {"type": "Polygon", "coordinates": [
            [[-49.1, -27.1], [-49.0, -27.1], [-49.0, -27.0], [-49.1, -27.1]]]}, "Polygon"),
        ("MultiPolygon", {"type": "MultiPolygon", "coordinates": [
            [[[-49.1, -27.1], [-49.0, -27.1], [-49.0, -27.0], [-49.1, -27.1]]]]}, "MultiSurface"),
    ],
)
def test_documento_valida_contra_o_xsd_publicado(cache_presente, tipo_camada, geometria, elemento):
    """Toda geometria da casa sai em GML 3.2 válido — inclusive as Multi*, que a passagem anterior
    achatava no primeiro membro."""
    esquema = _esquema_local(gml.descrever_tipo(ITEM, META, tipo_camada))
    doc = gml.colecao_feicoes(ITEM, _geojson(geometria), META, gml.CRS_PADRAO, True, "fid", 1,
                              "http://exemplo/schema")
    arvore = etree.fromstring(doc.encode("utf-8"))
    feicao = arvore.find(f"{{{gml.NS_WFS}}}member/*")
    assert feicao is not None
    esquema.assertValid(feicao)
    assert f"gml:{elemento}" in doc or f"<gml:{elemento}" in doc


def test_toda_geometria_tem_gml_id(cache_presente):
    doc = gml.colecao_feicoes(
        ITEM, _geojson({"type": "MultiPolygon", "coordinates": [
            [[[-49.1, -27.1], [-49.0, -27.1], [-49.0, -27.0], [-49.1, -27.1]]]]}),
        META, gml.CRS_PADRAO, True, "fid", 1, "http://exemplo/schema")
    for trecho in re.findall(r"<gml:(?:Point|LineString|Polygon|MultiSurface|MultiCurve|MultiPoint)[^>]*>",
                              doc):
        assert "gml:id=" in trecho, trecho


def test_ordem_dos_eixos_na_saida():
    """`urn:ogc:def:crs:EPSG::4326` sai latitude longitude; CRS84 sai longitude latitude."""
    ponto = {"type": "Point", "coordinates": [-49.1, -27.1]}
    lat_lon = gml.geometria_gml(ponto, gml.CRS_PADRAO, "g1", True)
    lon_lat = gml.geometria_gml(ponto, "http://www.opengis.net/def/crs/OGC/1.3/CRS84", "g1", False)
    assert "<gml:pos>-27.1 -49.1</gml:pos>" in lat_lon
    assert "<gml:pos>-49.1 -27.1</gml:pos>" in lon_lat


def test_hits_e_valores_sao_xml_bem_formado():
    etree.fromstring(gml.colecao_hits(42).encode("utf-8"))
    doc = gml.colecao_valores(ITEM, _geojson({"type": "Point", "coordinates": [-49.1, -27.1]}),
                              META, gml.CRS_PADRAO, True, "fid", "nome", 1)
    arvore = etree.fromstring(doc.encode("utf-8"))
    assert arvore.get("numberMatched") == "1"
    etree.fromstring(gml.excecao("InvalidParameterValue", "texto de erro", "COUNT").encode("utf-8"))


def test_nome_de_tipo_e_ncname():
    """Nome de tipo de feição precisa ser NCName: o UUID do item começa com dígito e tem hífen."""
    nome = gml.nome_tipo(ITEM)
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", nome)
    assert "-" not in nome
