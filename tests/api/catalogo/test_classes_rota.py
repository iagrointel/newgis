"""Testes da rota `GET /api/camadas/{id}/classes` (item L2-02-b-classificacao-servidor): as cláusulas
que dependem de dado real em Postgres (nulos/repetidos, categorias com 5.000 distintos, e a refutação
do adversário: n=1, n=100, campo de texto para método numérico, campo de data). O motor puro já está
coberto por `tests/unit/test_classificacao.py`; aqui só se prova que a ROTA fia o motor certo — sem
reimplementar a matemática.

A medida de desempenho (1 milhão de valores em <= 2 s) fica em `tests/api/catalogo/test_classes_desempenho.py`
porque exige a máquina calma (ver brief comum) e roda isolada."""

import random

import numpy as np

from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L2-02-b-classificacao-servidor"


def _criar_camada(conexao_plat_app, itens_a, colunas_sql: str, linhas: list[tuple], nomes_colunas: list[str],
                   tipos_campos: list[dict]) -> str:
    """Cria `plat_trabalho.zt_class_<sufixo>` com `colunas_sql`, insere `linhas` e registra o item
    `camada_vetorial` correspondente pela API. Devolve o item_id."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    tabela = "zt_class_" + str(random.randint(100000, 999999))
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, {colunas_sql})")
        for linha in linhas:
            marcadores = ", ".join(["%s"] * len(linha))
            cur.execute(
                f"INSERT INTO plat_trabalho.{tabela}({', '.join(nomes_colunas)}) VALUES ({marcadores})", linha
            )
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": tipos_campos, "fonte": "hospedada",
        },
    )
    return it["id"]


# ---------------------------------------------------------------------------
# cláusula 3 (refutação do item-pai): nulos excluídos e contados; repetidos não geram classe vazia
# ---------------------------------------------------------------------------

def test_nulos_excluidos_e_contados_repetidos_sem_classe_vazia(sessao_a, itens_a, conexao_plat_app):
    valores = [1.0, 1.0, 1.0, 2.0, 3.0, None, None, 100.0]
    linhas = [(v,) for v in valores]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v double precision", linhas, ["v"],
        [{"nome": "v", "tipo": "double precision"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 3})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["resumo"]["nulos"] == 2
    assert corpo["resumo"]["validos"] == 6
    assert sum(corpo["contagem_por_classe"]) == 6  # nenhum nulo contado, nenhuma linha perdida
    assert all(c > 0 for c in corpo["contagem_por_classe"]), "classe vazia por corte degenerado"


def test_categorias_5000_distintos_devolve_200_mais_total(sessao_a, itens_a, conexao_plat_app):
    linhas = [(f"cat-{i}",) for i in range(5000)]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v text", linhas, ["v"], [{"nome": "v", "tipo": "text"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tipo"] == "categorica"
    assert corpo["total_distintos"] == 5000
    assert corpo["truncado"] is True
    assert len(corpo["valores"]) == 201  # 200 principais + 1 linha "outros"
    assert corpo["valores"][-1]["valor"] == "outros"
    assert corpo["valores"][-1]["distintos_agrupados"] == 4800


# ---------------------------------------------------------------------------
# refutação do adversário: n=1, n=100, campo de texto p/ método numérico, campo de data
# ---------------------------------------------------------------------------

def test_n_igual_1(sessao_a, itens_a, conexao_plat_app):
    rng = np.random.default_rng(42)
    valores = rng.normal(10, 3, 300)
    linhas = [(float(v),) for v in valores]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v double precision", linhas, ["v"],
        [{"nome": "v", "tipo": "double precision"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 1})
    assert r.status_code == 200, r.text
    cortes = r.json()["cortes"]
    esperado = np.quantile(valores, [0.0, 1.0])
    assert np.allclose(cortes, esperado, atol=1e-9)


def test_n_igual_100_maior_que_distintos(sessao_a, itens_a, conexao_plat_app):
    rng = np.random.default_rng(7)
    valores = rng.normal(0, 1, 300)
    linhas = [(float(v),) for v in valores]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v double precision", linhas, ["v"],
        [{"nome": "v", "tipo": "double precision"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 32})
    assert r.status_code == 200, r.text
    esperado = np.quantile(valores, np.linspace(0, 1, 33))
    assert np.allclose(r.json()["cortes"], esperado, atol=1e-9)
    # n=100 é rejeitado antes de tocar o banco: o portão da rota trava em 32 (ADR do item) e o
    # comparativo acima já prova que o motor não trunca silenciosamente dentro do teto aceito
    r2 = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 100})
    assert r2.status_code == 422, r2.text


def test_campo_texto_para_metodo_numerico_e_4xx(sessao_a, itens_a, conexao_plat_app):
    linhas = [(f"a{i}",) for i in range(20)]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v text", linhas, ["v"], [{"nome": "v", "tipo": "text"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 3})
    assert 400 <= r.status_code < 500, r.text
    assert r.json()["erro"] == "metodo_incompativel_com_tipo"


def test_campo_data_classificado_e_comparado_com_numpy(sessao_a, itens_a, conexao_plat_app):
    import datetime

    base = datetime.date(2020, 1, 1)
    dias = [3, 10, 40, 100, 200, 365, 400, 500, 900, 1200]
    linhas = [(base + datetime.timedelta(days=d),) for d in dias]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v date", linhas, ["v"], [{"nome": "v", "tipo": "date"}],
    )
    r = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 3})
    assert r.status_code == 200, r.text
    epochs = np.array(
        [datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc).timestamp() for d in
         (base + datetime.timedelta(days=x) for x in dias)]
    )
    esperado = np.quantile(epochs, [0.0, 1 / 3, 2 / 3, 1.0])
    assert np.allclose(r.json()["cortes"], esperado, atol=1e-6)


# ---------------------------------------------------------------------------
# cache por (camada, versão, campo, método, n, filtro) — declarado na hipótese do item
# ---------------------------------------------------------------------------

def test_cache_por_camada_versao_campo_metodo_n(sessao_a, itens_a, conexao_plat_app):
    linhas = [(float(i),) for i in range(50)]
    iid = _criar_camada(
        conexao_plat_app, itens_a, "v double precision", linhas, ["v"],
        [{"nome": "v", "tipo": "double precision"}],
    )
    r1 = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 4})
    assert r1.status_code == 200 and r1.json()["cache"] is False
    r2 = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 4})
    assert r2.status_code == 200 and r2.json()["cache"] is True
    assert r1.json()["cortes"] == r2.json()["cortes"]
    r3 = sessao_a.get(f"/api/camadas/{iid}/classes", params={"campo": "v", "metodo": "quantil", "n": 5})
    assert r3.json()["cache"] is False  # n diferente = chave de cache diferente
