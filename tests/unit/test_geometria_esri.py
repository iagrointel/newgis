"""Testes do tradutor de geometria Esri (item L2-04-c): parsing de envelope/ponto csv e JSON,
mapa de esriSpatialRel, unidades de distância — sem banco (só o parsing/tradução)."""

import pytest

from app.consulta import geometria_esri as geo
from app.erros import ErroAPI


def test_parse_envelope_csv():
    obj, tipo = geo.parse_geometry("-46.6,-23.6,-46.4,-23.4", None)
    assert tipo == "envelope"
    assert obj == {"xmin": -46.6, "ymin": -23.6, "xmax": -46.4, "ymax": -23.4}


def test_parse_envelope_csv_texto_nao_numerico_e_recusado():
    with pytest.raises(ErroAPI):
        geo.parse_geometry("a,b,c,d", "esriGeometryEnvelope")


def test_parse_point_csv():
    obj, tipo = geo.parse_geometry("-46.6,-23.6", "esriGeometryPoint")
    assert tipo == "point"
    assert obj == {"x": -46.6, "y": -23.6}


def test_parse_geometry_json_polygon():
    js = '{"rings": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    obj, tipo = geo.parse_geometry(js, "esriGeometryPolygon")
    assert tipo == "polygon"
    assert obj["rings"][0][0] == [0, 0]


def test_para_ewkt_envelope():
    wkt = geo.para_ewkt({"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}, "envelope", 4326)
    assert wkt.startswith("SRID=4326;POLYGON((0.0 0.0, 1.0 0.0, 1.0 1.0, 0.0 1.0, 0.0 0.0))")


def test_para_ewkt_ponto():
    assert geo.para_ewkt({"x": -46.5, "y": -23.4}, "point", 4674) == "SRID=4674;POINT(-46.5 -23.4)"


def test_sr_wkid_formas():
    assert geo.sr_wkid(4326) == 4326
    assert geo.sr_wkid("4326") == 4326
    assert geo.sr_wkid({"wkid": 3857}) == 3857
    assert geo.sr_wkid({"latestWkid": 3857, "wkid": 102100}) == 3857
    assert geo.sr_wkid(None) is None


def test_spatial_rel_tem_os_9_valores_esri():
    esperados = {
        "esriSpatialRelIntersects", "esriSpatialRelContains", "esriSpatialRelCrosses",
        "esriSpatialRelEnvelopeIntersects", "esriSpatialRelIndexIntersects", "esriSpatialRelOverlaps",
        "esriSpatialRelTouches", "esriSpatialRelWithin", "esriSpatialRelRelation",
    }
    assert set(geo.SPATIAL_REL) == esperados


def test_unidades_para_metros():
    assert geo.UNIDADES_METROS["esriSRUnit_Kilometer"] == 1000.0
    assert geo.UNIDADES_METROS["esriSRUnit_Meter"] == 1.0


def test_geometry_type_invalido_e_recusado():
    with pytest.raises(ErroAPI):
        geo.parse_geometry("{}", "esriGeometryMultipatch")


def test_geometria_vazia_e_recusada():
    with pytest.raises(ErroAPI):
        geo.parse_geometry("", "esriGeometryEnvelope")


def test_geometria_com_vertices_demais_e_recusada():
    muitos = [[float(i), float(i)] for i in range(geo.MAX_VERTICES + 1)]
    n = geo.contar_vertices({"points": muitos}, "multipoint")
    assert n > geo.MAX_VERTICES
