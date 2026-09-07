"""Unidade do compilador CQL2-JSON (item L2-01-h-selecao-filtros). Cada teste é uma cláusula do
portão ou uma linha da refutação, isolada do banco (compara o SQL/params textualmente ou executa
contra sqlite... na verdade contra nada: aqui só validamos estrutura e SQL gerado; a prova "mesma
contagem do SQL escrito à mão" mora em tests/api/test_selecao_filtro.py, contra o Postgres real)."""

import pytest

from app.consulta.cql2 import compilar_cql2, contar_clausulas
from app.consulta.where_ast import ErroWhere

COLUNAS = {
    "nome": {"sql": "t.nome", "tipo": "text"},
    "area_m2": {"sql": "t.area_m2", "tipo": "double precision"},
    "situacao": {"sql": "t.situacao", "tipo": "text"},
    "criado_em": {"sql": "t.criado_em", "tipo": "timestamp with time zone"},
    "ativo": {"sql": "t.ativo", "tipo": "boolean"},
    "geom": {"sql": "t.geom", "tipo": "geometry", "srid": 31982},
}


def test_comparacao_simples():
    r = compilar_cql2({"op": "=", "args": [{"property": "nome"}, "Lote 1"]}, COLUNAS)
    assert r.sql == "t.nome = %s"
    assert r.params == ["Lote 1"]


def test_and_or_aninhado_2_niveis():
    cql = {
        "op": "and",
        "args": [
            {"op": "=", "args": [{"property": "situacao"}, "disponível"]},
            {
                "op": "or",
                "args": [
                    {"op": ">", "args": [{"property": "area_m2"}, 200]},
                    {"op": "=", "args": [{"property": "ativo"}, True]},
                ],
            },
        ],
    }
    r = compilar_cql2(cql, COLUNAS)
    assert "AND" in r.sql and "OR" in r.sql
    assert r.params == ["disponível", 200, True]


def test_aninhamento_acima_de_2_niveis_recusado():
    cql = {"op": "and", "args": [
        {"op": "or", "args": [
            {"op": "and", "args": [
                {"op": "=", "args": [{"property": "nome"}, "x"]},
                {"op": "=", "args": [{"property": "nome"}, "y"]},
            ]},
            {"op": "=", "args": [{"property": "nome"}, "z"]},
        ]},
        {"op": "=", "args": [{"property": "nome"}, "w"]},
    ]}
    with pytest.raises(ErroWhere) as e:
        compilar_cql2(cql, COLUNAS)
    assert e.value.codigo == "expressao_complexa"


def test_campo_inexistente_recusado():
    with pytest.raises(ErroWhere) as e:
        compilar_cql2({"op": "=", "args": [{"property": "nao_existe"}, 1]}, COLUNAS)
    assert e.value.codigo == "campo_nao_permitido"


def test_operador_invalido_recusado():
    with pytest.raises(ErroWhere) as e:
        compilar_cql2({"op": "bogus", "args": [{"property": "nome"}, 1]}, COLUNAS)
    assert e.value.codigo == "operador_nao_permitido"


def test_funcao_nao_permitida_recusada():
    cql = {"op": ">=", "args": [{"property": "criado_em"}, {"function": {"name": "pg_sleep", "args": [5]}}]}
    with pytest.raises(ErroWhere) as e:
        compilar_cql2(cql, COLUNAS)
    assert e.value.codigo == "operador_nao_permitido"


def test_funcao_now_menos_dias_ok():
    cql = {"op": ">=", "args": [{"property": "criado_em"}, {"function": {"name": "now_menos_dias", "args": [30]}}]}
    r = compilar_cql2(cql, COLUNAS)
    assert "make_interval" in r.sql
    assert r.params == [30]


def test_valor_tipo_errado_recusado():
    with pytest.raises(ErroWhere) as e:
        compilar_cql2({"op": ">", "args": [{"property": "area_m2"}, "não é número"]}, COLUNAS)
    assert e.value.codigo == "tipo_invalido"


def test_data_invalida_recusada():
    with pytest.raises(ErroWhere) as e:
        compilar_cql2({"op": ">=", "args": [{"property": "criado_em"}, "não é data"]}, COLUNAS)
    assert e.value.codigo == "tipo_invalido"


def test_mais_de_100_clausulas_recusado():
    cql = {"op": "and", "args": [{"op": "=", "args": [{"property": "nome"}, str(i)]} for i in range(200)]}
    with pytest.raises(ErroWhere) as e:
        compilar_cql2(cql, COLUNAS)
    assert e.value.codigo == "expressao_complexa"


def test_in_lista_vazia_recusada():
    with pytest.raises(ErroWhere):
        compilar_cql2({"op": "in", "args": [{"property": "nome"}, []]}, COLUNAS)


def test_isnull():
    r = compilar_cql2({"op": "isNull", "args": [{"property": "nome"}]}, COLUNAS)
    assert r.sql == "t.nome IS NULL"
    assert r.params == []


def test_s_intersects_gera_st_intersects_com_transform():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    r = compilar_cql2({"op": "s_intersects", "args": [{"property": "geom"}, geom]}, COLUNAS)
    assert "ST_Intersects" in r.sql and "ST_Transform" in r.sql and "31982" in r.sql


def test_s_dwithin_gera_geography_e_distancia():
    geom = {"type": "Point", "coordinates": [0, 0]}
    r = compilar_cql2({"op": "s_dwithin", "args": [{"property": "geom"}, geom, 500]}, COLUNAS)
    assert "ST_DWithin" in r.sql and "::geography" in r.sql
    assert r.params[-1] == 500.0


def test_geometria_invalida_recusada():
    with pytest.raises(ErroWhere) as e:
        compilar_cql2({"op": "s_intersects", "args": [{"property": "geom"}, {"type": "Nada"}]}, COLUNAS)
    assert e.value.codigo == "tipo_invalido"


def test_contar_clausulas():
    cql = {"op": "and", "args": [
        {"op": "=", "args": [{"property": "nome"}, "x"]},
        {"op": "=", "args": [{"property": "situacao"}, "y"]},
    ]}
    assert contar_clausulas(cql) == 2


def test_injecao_sql_no_valor_vira_parametro_nunca_texto():
    r = compilar_cql2({"op": "=", "args": [{"property": "nome"}, "'; DROP TABLE t; --"]}, COLUNAS)
    assert "DROP TABLE" not in r.sql
    assert r.params == ["'; DROP TABLE t; --"]
