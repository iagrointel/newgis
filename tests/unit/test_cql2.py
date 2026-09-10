"""Testes do tradutor CQL2 (item L2-04-g). Cobre a cláusula do portão "10 expressões CQL2-text e
as equivalentes CQL2-JSON dão a mesma contagem e batem com SQL escrito à mão" na parte de
compilação (sem banco — a contagem contra o banco de verdade está em tests/api/); aqui confere-se
que texto e JSON compilam para SQL equivalente e que a bateria de ataque (função desconhecida,
1.000 cláusulas, bbox invertido, datetime aberto) nunca vira exceção não tratada."""

import datetime

import pytest

from app.consulta import cql2

COLUNAS = {"nome": '"nome"', "area": '"area"', "quando": '"quando"', "categoria": '"categoria"'}


def _sql_texto(texto):
    return cql2.compilar_cql2(texto, "cql2-text", COLUNAS, 4674)


def _sql_json(doc):
    return cql2.compilar_cql2(doc, "cql2-json", COLUNAS, 4674)


# ---------------------------------------------------------------- 10 pares text/json equivalentes
CASOS = [
    ("nome = 'Brusque'", {"op": "=", "args": [{"property": "nome"}, "Brusque"]}),
    ("area > 100", {"op": ">", "args": [{"property": "area"}, 100]}),
    ("area >= 100 AND area <= 200", {"op": "and", "args": [
        {"op": ">=", "args": [{"property": "area"}, 100]}, {"op": "<=", "args": [{"property": "area"}, 200]}]}),
    ("nome LIKE 'B%'", {"op": "like", "args": [{"property": "nome"}, "B%"]}),
    ("categoria IN ('a', 'b', 'c')", {"op": "in", "args": [{"property": "categoria"}, ["a", "b", "c"]]}),
    ("area BETWEEN 10 AND 20", {"op": "between", "args": [{"property": "area"}, 10, 20]}),
    ("nome IS NULL", {"op": "isNull", "args": [{"property": "nome"}]}),
    ("NOT (area > 100)", {"op": "not", "args": [{"op": ">", "args": [{"property": "area"}, 100]}]}),
    ("area > 10 OR categoria = 'x'", {"op": "or", "args": [
        {"op": ">", "args": [{"property": "area"}, 10]}, {"op": "=", "args": [{"property": "categoria"}, "x"]}]}),
    ("T_AFTER(quando, TIMESTAMP('2026-01-01T00:00:00Z'))",
     {"op": "t_after", "args": [{"property": "quando"}, {"timestamp": "2026-01-01T00:00:00Z"}]}),
]


@pytest.mark.parametrize("texto,doc", CASOS)
def test_texto_e_json_compilam_para_o_mesmo_sql(texto, doc):
    sql_t, params_t = _sql_texto(texto)
    sql_j, params_j = _sql_json(doc)
    assert sql_t == sql_j, f"{texto!r} -> {sql_t!r} != {sql_j!r}"
    assert params_t == params_j


def test_comparacao_bate_com_sql_escrito_a_mao():
    sql, params = _sql_texto("area > 100")
    assert sql == '"area" > %s'
    assert params == [100]


def test_and_or_not_precedencia():
    sql, params = _sql_texto("area > 10 AND categoria = 'x' OR nome = 'y'")
    # AND liga mais forte que OR: (area>10 AND categoria='x') OR nome='y'
    assert sql == '(("area" > %s) AND ("categoria" = %s)) OR ("nome" = %s)'
    assert params == [10, "x", "y"]


def test_in_lista():
    sql, params = _sql_texto("categoria IN ('a', 'b')")
    assert sql == '"categoria" = ANY(%s)'
    assert params == [["a", "b"]]


def test_between():
    sql, params = _sql_texto("area BETWEEN 10 AND 20")
    assert sql == '"area" BETWEEN %s AND %s'
    assert params == [10, 20]


def test_is_null_e_is_not_null():
    sql, _ = _sql_texto("nome IS NULL")
    assert sql == '"nome" IS NULL'
    sql, _ = _sql_texto("nome IS NOT NULL")
    assert sql == '"nome" IS NOT NULL'


def test_like():
    sql, params = _sql_texto("nome LIKE 'B%'")
    assert sql == '"nome"::text LIKE %s'
    assert params == ["B%"]


def test_not():
    sql, params = _sql_texto("NOT (area > 100)")
    assert sql == 'NOT ("area" > %s)'
    assert params == [100]


def test_espacial_s_intersects():
    geom = '\'{"type":"Point","coordinates":[-49.1,-27.1]}\''
    sql, params = _sql_texto(f"S_INTERSECTS(geometria, {geom})")
    assert sql.startswith("ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 4674))")
    assert params[0].startswith("{")


def test_espacial_s_dwithin():
    geom = '\'{"type":"Point","coordinates":[-49.1,-27.1]}\''
    sql, params = _sql_texto(f"S_DWITHIN(geometria, {geom}, 1000)")
    assert "ST_DWithin(ST_Transform(geom, 4326)::geography" in sql
    assert params[-1] == 1000.0


def test_temporal_t_after():
    sql, params = _sql_texto("T_AFTER(quando, TIMESTAMP('2026-01-01T00:00:00Z'))")
    assert sql == '"quando" > %s'
    assert params == [datetime.datetime(2026, 1, 1, 0, 0)]


def test_temporal_t_before_intervalo_aberto():
    # ../2026-01-01 : instante indeterminado do lado esquerdo — o portão exige que funcione
    sql, params = _sql_texto("T_BEFORE(quando, TIMESTAMP('../2026-01-01'))")
    assert sql == '"quando" < %s'
    assert params == [datetime.date(2026, 1, 1)]


def test_temporal_t_during_intervalo_aberto_dos_dois_lados():
    sql, params = _sql_texto("T_DURING(quando, TIMESTAMP('2026-01-01/..'))")
    assert sql == '"quando" >= %s'
    assert params == [datetime.date(2026, 1, 1)]


def test_temporal_t_during_json_intervalo_fechado():
    doc = {"op": "t_during", "args": [{"property": "quando"},
                                       {"interval": [{"date": "2026-01-01"}, {"date": "2026-02-01"}]}]}
    sql, params = _sql_json(doc)
    assert sql == '"quando" >= %s AND "quando" <= %s'
    assert params == [datetime.date(2026, 1, 1), datetime.date(2026, 2, 1)]


# ---------------------------------------------------------------- bateria de ataque
def test_funcao_desconhecida_e_erro_tratado_nunca_500():
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_texto("FUNCAO_QUE_NAO_EXISTE(nome, 'x')")
    assert e.value.codigo in ("filtro_sintaxe",)


def test_operador_json_desconhecido():
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_json({"op": "s_desconhecido", "args": [{"property": "nome"}, {"type": "Point", "coordinates": [0, 0]}]})
    assert e.value.codigo == "filtro_operador_desconhecido"


def test_mil_clausulas_and_e_recusado_por_teto_de_token_nao_trava():
    texto = " AND ".join("area > 1" for _ in range(1000))
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_texto(texto)
    assert e.value.codigo == "filtro_grande_demais"


def test_mil_clausulas_and_json_e_recusado_por_profundidade():
    doc = {"op": ">", "args": [{"property": "area"}, 1]}
    grande = {"op": "and", "args": [doc] * 1000}
    # 1000 termos no MESMO nó and não é profundidade — mas cada um deve compilar sem estourar pilha;
    # o teto real do JSON é por aninhamento (profundidade), então isto tem de compilar sem erro:
    sql, params = _sql_json(grande)
    assert sql.count(" AND ") == 999
    assert len(params) == 1000


def test_json_aninhado_alem_do_teto_de_profundidade():
    no = {"op": ">", "args": [{"property": "area"}, 1]}
    for _ in range(30):
        no = {"op": "not", "args": [no]}
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_json(no)
    assert e.value.codigo == "filtro_profundo_demais"


def test_campo_desconhecido_nunca_vaza_para_sql():
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_texto("campo_que_nao_existe = 1")
    assert e.value.codigo == "filtro_campo_desconhecido"


def test_geometria_invalida_em_funcao_espacial():
    with pytest.raises(cql2.ErroCql2) as e:
        _sql_texto("S_INTERSECTS(geometria, 'isto nao e geojson')")
    assert e.value.codigo == "filtro_geometria_invalida"


def test_sintaxe_quebrada_nunca_lanca_excecao_nao_tratada():
    for ruim in ["nome = ", "(((nome = 'a'", "nome IN (", "AND OR", ""]:
        with pytest.raises(cql2.ErroCql2):
            _sql_texto(ruim)


def test_bbox_invertido_nao_e_responsabilidade_do_cql2_mas_nao_quebra_geometria_valida():
    # bbox invertido é validado na camada de rota (Part 1/2, xmin>xmax); aqui só se confere que uma
    # geometria válida com envelope "invertido" ainda compila (quem decide 400 é a rota).
    geom = '\'{"type":"Polygon","coordinates":[[[10,10],[0,10],[0,0],[10,0],[10,10]]]}\''
    sql, params = _sql_texto(f"S_WITHIN(geometria, {geom})")
    assert sql.startswith("ST_Within(geom,")
