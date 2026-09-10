"""API de seleção e filtro do mapa (item L2-01-h-selecao-filtros): cada teste aqui é uma cláusula
do portão de pronto ou uma linha da refutação, contra Postgres real (nunca mock).

Depende da bancada `scripts/selecao_demo_camadas.py criar` (camadas `selecao-pontos` e `selecao-alvo`
no inquilino demo). Sem ela os testes SALTAM com o motivo dito — nunca passam por omissão."""

import json

import pytest

MARCA_PONTOS = "selecao-pontos (L2-01-h"
MARCA_ALVO = "selecao-alvo (L2-01-h"
QUADRADO_ALVO = {
    "type": "Polygon",
    "coordinates": [[[-50.05, -15.05], [-49.95, -15.05], [-49.95, -14.95],
                      [-50.05, -14.95], [-50.05, -15.05]]],
}


def _camadas(sessao):
    r = sessao.get("/api/mapa/camadas")
    assert r.status_code == 200, r.text
    return r.json()["camadas"]


@pytest.fixture(scope="module")
def camada_pontos(sessao_a):
    achadas = [c for c in _camadas(sessao_a) if MARCA_PONTOS in c["titulo"]]
    if not achadas:
        pytest.skip("bancada do item ausente: rode scripts/selecao_demo_camadas.py criar")
    return achadas[0]


@pytest.fixture(scope="module")
def camada_alvo(sessao_a):
    achadas = [c for c in _camadas(sessao_a) if MARCA_ALVO in c["titulo"]]
    if not achadas:
        pytest.skip("bancada do item ausente: rode scripts/selecao_demo_camadas.py criar")
    return achadas[0]


# =================================================================== conexão direta ao Postgres p/ o SQL à mão
def _conexao_direta():
    import os

    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(os.environ["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        # RLS de plat.item exige o mesmo contexto que a API monta por sessão (ADR 0002); a suíte usa
        # sempre o admin de `demo`, o mesmo dono da bancada.
        cur.execute("SELECT usuario_id, tenant_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        r = cur.fetchone()
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(r["tenant_id"]),))
        cur.execute("SELECT set_config('plat.usuario_id', %s, false)", (str(r["usuario_id"]),))
        cur.execute("SELECT set_config('plat.login', 'admin', false)")
    return con


def _schema_tabela(camada_id):
    con = _conexao_direta()
    with con.cursor() as cur:
        cur.execute("SELECT dados->>'schema' AS esquema, dados->>'tabela' AS tabela "
                    "FROM plat.item WHERE id = %s::uuid", (camada_id,))
        r = cur.fetchone()
    con.close()
    return r["esquema"], r["tabela"]


# =================================================================== cláusula: polígono de 20 feições == ST_Intersects
def test_selecao_por_poligono_bate_com_st_intersects_direto(sessao_a, camada_pontos):
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/selecionar",
                       json={"geometria": QUADRADO_ALVO, "relacao": "intersects"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["n"] == 20, corpo

    esquema, tabela = _schema_tabela(camada_pontos["id"])
    con = _conexao_direta()
    with con.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{tabela}" '
                    f"WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                    (json.dumps(QUADRADO_ALVO),))
        n_direto = cur.fetchone()["n"]
    con.close()
    assert corpo["n"] == n_direto == 20


# ============================================================== cláusula: CQL2 3 cláusulas + OR aninhado == SQL à mão
def test_filtro_cql2_tres_clausulas_or_aninhado_bate_com_sql_a_mao(sessao_a, camada_pontos):
    filtro = {
        "op": "and",
        "args": [
            {"op": "like", "args": [{"property": "nome"}, "dentro%"]},
            {"op": "in", "args": [{"property": "situacao"}, ["disponível", "ocupado"]]},
            {"op": "or", "args": [
                {"op": ">", "args": [{"property": "area_m2"}, 300]},
                {"op": "=", "args": [{"property": "ativo"}, True]},
            ]},
        ],
    }
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 200, r.text
    n_api = r.json()["n"]

    esquema, tabela = _schema_tabela(camada_pontos["id"])
    con = _conexao_direta()
    with con.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{tabela}" '
                    f"WHERE nome LIKE 'dentro%%' AND situacao IN ('disponível', 'ocupado') "
                    f"AND (area_m2 > 300 OR ativo = true)")
        n_mao = cur.fetchone()["n"]
    con.close()
    assert n_api == n_mao


# =================================================================== cláusula: filtro em data com fuso
def test_filtro_data_com_fuso_bate_com_sql_a_mao(sessao_a, camada_pontos):
    filtro = {"op": ">=", "args": [{"property": "criado_em"}, "2026-08-01T00:00:00-03:00"]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 200, r.text
    n_api = r.json()["n"]

    esquema, tabela = _schema_tabela(camada_pontos["id"])
    con = _conexao_direta()
    with con.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{tabela}" '
                    f"WHERE criado_em >= '2026-08-01T00:00:00-03:00'::timestamptz")
        n_mao = cur.fetchone()["n"]
    con.close()
    assert n_api == n_mao


# =================================================================== cláusula: seleção espacial por distância 500 m
def test_selecao_espacial_por_distancia_500m_bate_com_st_dwithin_geografico(sessao_a, camada_pontos, camada_alvo):
    r = sessao_a.post("/api/mapa/selecao-espacial",
                       json={"camada_a": camada_pontos["id"], "camada_b": camada_alvo["id"],
                             "relacao": "dwithin", "distancia_m": 500})
    assert r.status_code == 200, r.text
    n_api = r.json()["n"]

    ea, ta = _schema_tabela(camada_pontos["id"])
    eb, tb = _schema_tabela(camada_alvo["id"])
    con = _conexao_direta()
    with con.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{ea}"."{ta}" a WHERE EXISTS ('
                    f'  SELECT 1 FROM "{eb}"."{tb}" b '
                    f"  WHERE ST_DWithin(a.geom::geography, b.geom::geography, 500))")
        n_mao = cur.fetchone()["n"]
    con.close()
    assert n_api == n_mao


def test_selecao_espacial_por_distancia_100m_nao_pega_o_alvo_a_300m(sessao_a, camada_pontos, camada_alvo):
    # o alvo está a ~300 m do CENTRO do quadrado, mas nenhum dos 20 pontos "dentro" fica garantido a
    # <= 100 m dele (a bancada sorteia posição dentro do quadrado inteiro) — a prova aqui é que o
    # número muda com a distância, e nunca sobe quando a distância cai.
    r500 = sessao_a.post("/api/mapa/selecao-espacial",
                          json={"camada_a": camada_pontos["id"], "camada_b": camada_alvo["id"],
                                "relacao": "dwithin", "distancia_m": 500})
    r100 = sessao_a.post("/api/mapa/selecao-espacial",
                          json={"camada_a": camada_pontos["id"], "camada_b": camada_alvo["id"],
                                "relacao": "dwithin", "distancia_m": 100})
    assert r500.status_code == r100.status_code == 200
    assert r100.json()["n"] <= r500.json()["n"]


# ============================================================== cláusula: construtor recusa campo/operador inválido
def test_construtor_recusa_campo_inexistente(sessao_a, camada_pontos):
    filtro = {"op": "=", "args": [{"property": "campo_que_nao_existe"}, "x"]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "campo_nao_permitido", r.text


def test_construtor_recusa_operador_invalido(sessao_a, camada_pontos):
    filtro = {"op": "funcao_inexistente", "args": [{"property": "nome"}, "x"]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 422, r.text


# =================================================================== valores únicos (base do construtor)
def test_valores_unicos_do_campo_situacao(sessao_a, camada_pontos):
    r = sessao_a.get(f"/api/mapa/camadas/{camada_pontos['id']}/valores", params={"campo": "situacao"})
    assert r.status_code == 200, r.text
    assert set(r.json()["valores"]) <= {"disponível", "ocupado"}


def test_valores_unicos_recusa_campo_geometria(sessao_a, camada_pontos):
    r = sessao_a.get(f"/api/mapa/camadas/{camada_pontos['id']}/valores", params={"campo": "geom"})
    assert r.status_code == 422, r.text


# =================================================================== refutação: injeção CQL2
def test_adversario_funcao_nao_permitida_da_422_nunca_500(sessao_a, camada_pontos):
    filtro = {"op": "pg_sleep", "args": [{"property": "nome"}, 5]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 422, r.text


def test_adversario_200_clausulas_da_422_nunca_500(sessao_a, camada_pontos):
    filtro = {"op": "and", "args": [
        {"op": "=", "args": [{"property": "nome"}, f"x{i}"]} for i in range(200)
    ]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 422, r.text


def test_adversario_valor_de_tipo_errado_da_422_nunca_500(sessao_a, camada_pontos):
    filtro = {"op": ">", "args": [{"property": "area_m2"}, "nao-e-numero"]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code in (422,), r.text


def test_adversario_sql_bruto_no_nome_do_campo_da_422_nunca_500(sessao_a, camada_pontos):
    filtro = {"op": "=", "args": [{"property": "nome; DROP TABLE plat.item; --"}, "x"]}
    r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/filtrar", json={"filtro": filtro})
    assert r.status_code == 422, r.text


def test_adversario_dez_selecoes_aleatorias_batem_com_postgis(sessao_a, camada_pontos):
    """10 quadrados aleatórios (posição e lado sorteados) sobre a nuvem de 200 pontos: a contagem que a
    API devolve por /selecionar (ST_Intersects) tem de bater, sempre, com ST_Intersects direto no mesmo
    Postgres — é a comparação com PostGIS que o adversário do item exige."""
    import random

    random.seed(20260907)
    esquema, tabela = _schema_tabela(camada_pontos["id"])
    con = _conexao_direta()
    try:
        for _ in range(10):
            cx = random.uniform(-65.0, -35.0)
            cy = random.uniform(-30.0, -12.0)
            lado = random.uniform(0.5, 5.0)
            poligono = {
                "type": "Polygon",
                "coordinates": [[[cx - lado, cy - lado], [cx + lado, cy - lado],
                                  [cx + lado, cy + lado], [cx - lado, cy + lado],
                                  [cx - lado, cy - lado]]],
            }
            r = sessao_a.post(f"/api/mapa/camadas/{camada_pontos['id']}/selecionar",
                               json={"geometria": poligono, "relacao": "intersects"})
            assert r.status_code == 200, r.text
            with con.cursor() as cur:
                cur.execute(f'SELECT count(*) AS n FROM "{esquema}"."{tabela}" '
                            f"WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                            (json.dumps(poligono),))
                n_direto = cur.fetchone()["n"]
            assert r.json()["n"] == n_direto, (poligono, r.json()["n"], n_direto)
    finally:
        con.close()
