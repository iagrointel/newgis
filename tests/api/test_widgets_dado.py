"""Portão do item L5-01-c-widgets-dado, lado do servidor: a tabela do app pagina e ordena 100 mil feições pelo
FeatureServer com p95 < 300 ms por página (medido, gravado em tests/medidas); o gráfico agrega no servidor
(`outStatistics` + `groupByFieldsForStatistics`) e cada agregação bate com SQL direto na mesma tabela
(count/sum/avg/min/max por categoria — refutação: 5 agregações comparadas); valores únicos do filtro;
exportação por páginas de 5 mil respeitando o `where`. Reusa a `FabricaCamada` (tabela real via
`plat.camada_preparar`) e semeia 100 mil linhas por SQL na trilha — semeadura de MEDIDA, não caminho de produto."""

from __future__ import annotations

import json
import os
import random
import time

import psycopg2
import pytest

from tests.api.test_edicao_transacional import FabricaCamada, _admin_usuario_id
from tests.api.test_ogc_features_crs_cql2 import _criar_com_retentativa
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L5-01-c-widgets-dado"
N = 100_000
CATEGORIAS = ["A", "B", "C", "D", "E"]


@pytest.fixture(scope="module")
def conexao_modulo(env):
    """Mesma conexão de `conexao_plat_app` (tests/conftest.py), mas por MÓDULO: semear 100 mil linhas uma vez."""
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    try:
        yield con
    finally:
        con.rollback()
        con.close()


@pytest.fixture(scope="module")
def camada_100k(conexao_modulo):
    conexao_plat_app = conexao_modulo
    fabrica = FabricaCamada(conexao_plat_app)
    ids = ids_por_slug(conexao_plat_app)
    admin_id = _admin_usuario_id(conexao_plat_app, "demo")
    item_id, dados = _criar_com_retentativa(
        fabrica, conexao_plat_app, "demo", ids["demo"], admin_id,
        campos=[{"nome": "nome", "tipo": "text"}, {"nome": "categoria", "tipo": "text"},
                {"nome": "valor", "tipo": "double precision"}, {"nome": "n", "tipo": "integer"},
                {"nome": "quando", "tipo": "timestamp without time zone"}],
        geometria="Point",
    )
    contexto(conexao_plat_app, ids["demo"], usuario_id=admin_id, login="admin")
    t0 = time.perf_counter()
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{dados["schema"]}"."{dados["tabela"]}" (geom, nome, categoria, valor, n, quando) '
            "SELECT ST_SetSRID(ST_MakePoint(-50 + (i %% 1000) * 0.01, -25 + (i / 1000) * 0.05), 4674), "
            "'f' || i, (%s::text[])[1 + i %% 5], (i %% 997) * 1.5, i %% 100, "
            "timestamp '2026-01-01' + (i %% 365) * interval '1 day' FROM generate_series(1, %s) i",
            (CATEGORIAS, N),
        )
        cur.execute(f'ANALYZE "{dados["schema"]}"."{dados["tabela"]}"')
    conexao_plat_app.commit()
    yield {"id": item_id, "dados": dados, "tenant_id": ids["demo"], "admin_id": admin_id,
           "semeadura_s": round(time.perf_counter() - t0, 2), "con": conexao_plat_app}
    fabrica.limpar()


def _query(sessao, camada_id, **params):
    params.setdefault("f", "json")
    r = sessao.post(f"/rest/services/{camada_id}/FeatureServer/0/query", data=params)
    assert r.status_code == 200, r.text
    return r.json()


def _p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(len(xs) * 0.95) - 1))]


def test_tabela_100_mil_pagina_e_ordena_p95_menor_que_300_ms(sessao_a, camada_100k, medida):
    cid = camada_100k["id"]
    total = _query(sessao_a, cid, where="1=1", returnCountOnly="true")["count"]
    assert total == N
    rnd = random.Random(7)
    tempos = []
    wheres = ["1=1", "categoria = 'B'", "valor > 500 AND n < 50"]
    contagens = {w: _query(sessao_a, cid, where=w, returnCountOnly="true")["count"] for w in wheres}
    assert all(c > 1000 for c in contagens.values()), contagens
    for k in range(30):
        ordem = ["valor DESC", "categoria ASC, n DESC", "nome ASC", "fid ASC"][k % 4]
        where = wheres[k % 3]
        offset = rnd.randrange(0, contagens[where] - 60)
        t0 = time.perf_counter()
        r = _query(sessao_a, cid, where=where, orderByFields=ordem, resultOffset=offset, resultRecordCount=50,
                   returnGeometry="false", outFields="nome,categoria,valor,n")
        tempos.append((time.perf_counter() - t0) * 1000)
        assert 0 < len(r["features"]) <= 50
        if ordem == "valor DESC":
            valores = [f["attributes"]["valor"] for f in r["features"]]
            assert valores == sorted(valores, reverse=True)
    p95 = round(_p95(tempos), 1)
    gravar = medida(ITEM)
    gravar("tabela_pagina_100k_p95_ms", p95, "ms",
           "POST /rest/services/{camada}/FeatureServer/0/query resultRecordCount=50, resultOffset aleatorio, "
           "orderByFields e where variados, 30 paginas sobre 100 mil pontos (TestClient em processo)")
    gravar("tabela_pagina_100k_p50_ms", round(sorted(tempos)[len(tempos) // 2], 1), "ms", "mesma medida, mediana")
    gravar("semeadura_100k_s", camada_100k["semeadura_s"], "s",
        "INSERT ... generate_series(1, 100000) + ANALYZE na trilha")
    gravar("carga_1min", round(os.getloadavg()[0], 2), "load", "os.getloadavg()[0] no instante da medida")
    assert p95 < 300, (p95, tempos)


def test_grafico_agrega_no_servidor_e_bate_com_sql_direto(sessao_a, camada_100k):
    cid = camada_100k["id"]
    d = camada_100k["dados"]
    conexao_plat_app = camada_100k["con"]
    where = "n < 40"
    specs = [
        {"statisticType": "count", "onStatisticField": "*", "outStatisticFieldName": "n_"},
        {"statisticType": "sum", "onStatisticField": "valor", "outStatisticFieldName": "soma"},
        {"statisticType": "avg", "onStatisticField": "valor", "outStatisticFieldName": "media"},
        {"statisticType": "min", "onStatisticField": "valor", "outStatisticFieldName": "minimo"},
        {"statisticType": "max", "onStatisticField": "valor", "outStatisticFieldName": "maximo"},
    ]
    r = _query(sessao_a, cid, where=where, outStatistics=json.dumps(specs), groupByFieldsForStatistics="categoria")
    api = {f["attributes"]["categoria"]: f["attributes"] for f in r["features"]}
    assert set(api) == set(CATEGORIAS)
    contexto(conexao_plat_app, camada_100k["tenant_id"], usuario_id=camada_100k["admin_id"], login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(f'SELECT categoria, count(*) AS n_, sum(valor) AS soma, avg(valor) AS media, min(valor) AS minimo, '
                    f'max(valor) AS maximo FROM "{d["schema"]}"."{d["tabela"]}" WHERE n < 40 GROUP BY categoria')
        sql = {row["categoria"]: row for row in cur.fetchall()}
    conexao_plat_app.rollback()
    for cat in CATEGORIAS:
        assert api[cat]["n_"] == sql[cat]["n_"], cat
        for k in ("soma", "media", "minimo", "maximo"):
            assert api[cat][k] == pytest.approx(float(sql[cat][k]), rel=1e-9), (cat, k)


def test_filtro_valores_unicos_e_exportacao_respeitam_o_where(sessao_a, camada_100k):
    cid = camada_100k["id"]
    r = _query(sessao_a, cid, where="1=1", returnDistinctValues="true", outFields="categoria", returnGeometry="false")
    assert sorted(f["attributes"]["categoria"] for f in r["features"]) == CATEGORIAS  # o navegador ordena a lista
    # exportação: páginas de 5 mil com where; a soma das páginas é o count do where
    where = "categoria = 'C' AND n >= 90"
    esperado = _query(sessao_a, cid, where=where, returnCountOnly="true")["count"]
    assert 0 < esperado < N
    vistos = 0
    for offset in range(0, esperado + 5000, 5000):
        r = sessao_a.post(f"/rest/services/{cid}/FeatureServer/0/query",
                          data={"f": "geojson", "where": where, "resultOffset": offset, "resultRecordCount": 5000,
                                "returnGeometry": "true", "outFields": "*", "outSR": 4326})
        assert r.status_code == 200, r.text
        pagina = r.json()["features"]
        vistos += len(pagina)
        if len(pagina) < 5000:
            break
    assert vistos == esperado
    # 2 milhões (refutação): a tabela nunca pede a camada inteira; o teto por página do servidor é 5 mil
    r = _query(sessao_a, cid, where="1=1", resultRecordCount=1000000, returnGeometry="false", outFields="n")
    assert len(r["features"]) == 5000 and r.get("exceededTransferLimit") is True
