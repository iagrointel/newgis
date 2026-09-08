"""Portão do item L2-04-h, parte de filtro: o FES 2.0 do WFS produz o MESMO SQL parametrizado que o
CQL2 equivalente do OGC API Features (item L2-04-g). Se um dia os dois divergirem, é aqui que
aparece — o teste compara texto do SQL e lista de parâmetros, não só a contagem de linhas.

Cobre também o que o adversário deste item vai tentar: XXE (entidade externa e DTD), bomba de
entidade, filtro fundo demais, filtro grande demais e a ordem dos eixos do EPSG:4326."""

from __future__ import annotations

import datetime

import pytest

from app.consulta import cql2, fes

COLUNAS = {"nome": '"nome"', "area": '"area"', "quando": '"quando"', "geometria": "geom"}
SRID = 4674


def _fes(xml: str):
    return fes.compilar_fes(xml, COLUNAS, SRID)


def _cql2(texto: str):
    return cql2.compilar_cql2(texto, "cql2-text", COLUNAS, SRID)


def _envelope(x0, y0, x1, y1, srs="http://www.opengis.net/def/crs/OGC/1.3/CRS84") -> str:
    return (f'<gml:Envelope srsName="{srs}" xmlns:gml="http://www.opengis.net/gml/3.2">'
            f"<gml:lowerCorner>{x0} {y0}</gml:lowerCorner>"
            f"<gml:upperCorner>{x1} {y1}</gml:upperCorner></gml:Envelope>")


def _filtro(miolo: str) -> str:
    return ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2">' + miolo + "</fes:Filter>")


# --------------------------------------------------------------------------- comparação e lógica
@pytest.mark.parametrize(
    ("elemento", "equivalente"),
    [
        ("PropertyIsEqualTo", "nome = 'x'"),
        ("PropertyIsNotEqualTo", "nome <> 'x'"),
        ("PropertyIsLessThan", "nome < 'x'"),
        ("PropertyIsGreaterThan", "nome > 'x'"),
        ("PropertyIsLessThanOrEqualTo", "nome <= 'x'"),
        ("PropertyIsGreaterThanOrEqualTo", "nome >= 'x'"),
    ],
)
def test_comparacao_da_o_mesmo_sql_do_cql2(elemento, equivalente):
    sql, params, _ids = _fes(_filtro(
        f"<fes:{elemento}><fes:ValueReference>nome</fes:ValueReference>"
        f"<fes:Literal>x</fes:Literal></fes:{elemento}>"))
    assert (sql, params) == _cql2(equivalente)


def test_e_ou_nao_dao_o_mesmo_sql_do_cql2():
    sql, params, _ = _fes(_filtro(
        "<fes:And>"
        "<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
        "<fes:Literal>a</fes:Literal></fes:PropertyIsEqualTo>"
        "<fes:Not><fes:PropertyIsGreaterThan><fes:ValueReference>area</fes:ValueReference>"
        "<fes:Literal>10</fes:Literal></fes:PropertyIsGreaterThan></fes:Not>"
        "</fes:And>"))
    assert (sql, params) == _cql2("nome = 'a' AND NOT area > 10")


def test_like_between_e_null():
    sql, params, _ = _fes(_filtro(
        '<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="\\">'
        "<fes:ValueReference>nome</fes:ValueReference><fes:Literal>ab*</fes:Literal></fes:PropertyIsLike>"))
    assert (sql, params) == _cql2("nome LIKE 'ab%'")

    sql, params, _ = _fes(_filtro(
        "<fes:PropertyIsBetween><fes:ValueReference>area</fes:ValueReference>"
        "<fes:LowerBoundary><fes:Literal>1</fes:Literal></fes:LowerBoundary>"
        "<fes:UpperBoundary><fes:Literal>9</fes:Literal></fes:UpperBoundary></fes:PropertyIsBetween>"))
    assert (sql, params) == _cql2("area BETWEEN 1 AND 9")

    sql, params, _ = _fes(_filtro(
        "<fes:PropertyIsNull><fes:ValueReference>nome</fes:ValueReference></fes:PropertyIsNull>"))
    assert (sql, params) == _cql2("nome IS NULL")


def test_like_escapa_coringa_de_sql_que_nao_e_coringa_em_fes():
    """`%` e `_` são literais em FES; se passassem crus viravam coringa no LIKE do Postgres."""
    sql, params, _ = _fes(_filtro(
        '<fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">'
        "<fes:ValueReference>nome</fes:ValueReference><fes:Literal>10%_a*</fes:Literal>"
        "</fes:PropertyIsLike>"))
    assert params == ["10\\%\\_a%"]
    assert "LIKE" in sql


# --------------------------------------------------------------------------- espacial e temporal
def test_intersects_e_within_dao_o_mesmo_sql_do_cql2():
    for elemento, funcao in (("Intersects", "S_INTERSECTS"), ("Within", "S_WITHIN")):
        sql, params, _ = _fes(_filtro(
            f"<fes:{elemento}><fes:ValueReference>geometria</fes:ValueReference>"
            + _envelope(-49.5, -27.5, -49.0, -27.0) + f"</fes:{elemento}>"))
        esperado = _cql2(
            f"{funcao}(geometria, POLYGON((-49.5 -27.5, -49.0 -27.5, -49.0 -27.0, -49.5 -27.0, -49.5 -27.5)))")
        assert sql == esperado[0]
        assert params == esperado[1]


def test_dwithin_exige_metros_e_da_o_mesmo_sql_do_cql2():
    sql, params, _ = _fes(_filtro(
        '<fes:DWithin><fes:ValueReference>geometria</fes:ValueReference>'
        '<gml:Point srsName="http://www.opengis.net/def/crs/OGC/1.3/CRS84"><gml:pos>-49.1 -27.1</gml:pos>'
        '</gml:Point><fes:Distance uom="m">500</fes:Distance></fes:DWithin>'))
    esperado = _cql2("S_DWITHIN(geometria, POINT(-49.1 -27.1), 500)")
    assert sql == esperado[0]
    assert params == esperado[1]
    with pytest.raises(fes.ErroFes) as e:
        _fes(_filtro(
            '<fes:DWithin><fes:ValueReference>geometria</fes:ValueReference>'
            '<gml:Point srsName="CRS84"><gml:pos>-49.1 -27.1</gml:pos></gml:Point>'
            '<fes:Distance uom="mi">1</fes:Distance></fes:DWithin>'))
    assert e.value.codigo == "filtro_uom_nao_suportado"


def test_bbox_sem_valuereference_usa_a_geometria_padrao():
    sql, _params, _ = _fes(_filtro("<fes:BBOX>" + _envelope(-50, -28, -49, -27) + "</fes:BBOX>"))
    assert sql.startswith("ST_Intersects(geom")


def test_temporal_after_before_during():
    sql, params, _ = _fes(_filtro(
        "<fes:After><fes:ValueReference>quando</fes:ValueReference>"
        '<gml:TimeInstant gml:id="t1"><gml:timePosition>2026-01-01T00:00:00Z</gml:timePosition>'
        "</gml:TimeInstant></fes:After>"))
    assert sql == '"quando" > %s'
    assert params[0] == datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    sql, params, _ = _fes(_filtro(
        "<fes:During><fes:ValueReference>quando</fes:ValueReference>"
        '<gml:TimePeriod gml:id="p1"><gml:beginPosition>2026-01-01</gml:beginPosition>'
        "<gml:endPosition>2026-02-01</gml:endPosition></gml:TimePeriod></fes:During>"))
    esperado = _cql2("T_DURING(quando, 2026-01-01/2026-02-01)")
    assert sql == esperado[0]
    assert params == esperado[1]


# --------------------------------------------------------------------------- ordem dos eixos
def test_ordem_dos_eixos_urn_4326_e_latitude_longitude():
    """A pegadinha do WFS 2.0: em `urn:ogc:def:crs:EPSG::4326` vale a ordem da autoridade EPSG
    (latitude, longitude); na forma curta `EPSG:4326`, longitude, latitude."""
    urn = _fes(_filtro("<fes:BBOX>" + _envelope(-27.5, -49.5, -27.0, -49.0,
                                                 "urn:ogc:def:crs:EPSG::4326") + "</fes:BBOX>"))
    curto = _fes(_filtro("<fes:BBOX>" + _envelope(-49.5, -27.5, -49.0, -27.0,
                                                  "EPSG:4326") + "</fes:BBOX>"))
    assert urn[1] == curto[1], "o mesmo retângulo escrito nas duas convenções tem de compilar igual"
    assert fes._ordem_lat_lon("urn:ogc:def:crs:EPSG::4326") is True  # noqa: SLF001
    assert fes._ordem_lat_lon("http://www.opengis.net/def/crs/EPSG/0/4326") is True  # noqa: SLF001
    assert fes._ordem_lat_lon("EPSG:4326") is False  # noqa: SLF001
    assert fes._ordem_lat_lon("http://www.opengis.net/def/crs/OGC/1.3/CRS84") is False  # noqa: SLF001


def test_crs_de_filtro_fora_de_wgs84_e_recusado_em_vez_de_mentir():
    with pytest.raises(fes.ErroFes) as e:
        _fes(_filtro("<fes:BBOX>" + _envelope(300000, 7000000, 310000, 7010000,
                                               "urn:ogc:def:crs:EPSG::31982") + "</fes:BBOX>"))
    assert e.value.codigo == "srsname_nao_suportado"


# --------------------------------------------------------------------------- ataques
def test_xxe_com_entidade_externa_e_recusado():
    ataque = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE fes:Filter [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>'
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
        "<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
        "<fes:Literal>&xxe;</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>"
    )
    with pytest.raises(fes.ErroFes) as e:
        _fes(ataque)
    assert e.value.codigo in ("xml_dtd_proibida", "xml_entidade_proibida")


def test_bomba_de_entidade_e_recusada():
    bomba = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
        "<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
        "<fes:Literal>&lol2;</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>"
    )
    with pytest.raises(fes.ErroFes):
        _fes(bomba)


def test_filtro_fundo_demais_e_grande_demais_sao_recusados():
    fundo = "".join("<fes:Not>" for _ in range(fes.MAX_PROFUNDIDADE + 3))
    fundo += ("<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
              "<fes:Literal>a</fes:Literal></fes:PropertyIsEqualTo>")
    fundo += "".join("</fes:Not>" for _ in range(fes.MAX_PROFUNDIDADE + 3))
    with pytest.raises(fes.ErroFes) as e:
        _fes(_filtro(fundo))
    assert e.value.codigo in ("filtro_profundo_demais", "filtro_grande_demais")

    with pytest.raises(fes.ErroFes) as e:
        _fes("<x>" + "a" * (fes.MAX_BYTES + 10) + "</x>")
    assert e.value.codigo == "filtro_grande_demais"


def test_campo_fora_da_lista_branca_nao_vira_sql():
    with pytest.raises(fes.ErroFes) as e:
        _fes(_filtro(
            "<fes:PropertyIsEqualTo><fes:ValueReference>tenant_id</fes:ValueReference>"
            "<fes:Literal>1</fes:Literal></fes:PropertyIsEqualTo>"))
    assert e.value.codigo == "filtro_campo_desconhecido"


def test_literal_com_aspas_vira_parametro_nunca_texto_no_sql():
    sql, params, _ = _fes(_filtro(
        "<fes:PropertyIsEqualTo><fes:ValueReference>nome</fes:ValueReference>"
        "<fes:Literal>x'; DROP TABLE plat.item; --</fes:Literal></fes:PropertyIsEqualTo>"))
    assert "DROP" not in sql
    assert params == ["x'; DROP TABLE plat.item; --"]


def test_resourceid_sai_como_identidade_sem_predicado():
    sql, params, ids = _fes(
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
        '<fes:ResourceId rid="c_abc.7"/></fes:Filter>')
    assert (sql, params) == (None, [])
    assert ids == ["c_abc.7"]
