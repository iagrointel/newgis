"""Rota `POST /api/camadas/{id}/grafico` (item L2-01-i-graficos-de-camada), contra Postgres real:
  * soma/média/contagem de cada barra batem com SQL escrito à mão (portão);
  * histograma de 10 faixas confere com numpy.histogram nos MESMOS dados — contagens e bordas (portão), inclusive
    inteiros nas bordas e campo com um valor só;
  * regressão da dispersão confere com numpy.polyfit (tolerância 1e-6, portão) e o r² com numpy.corrcoef²;
  * a contagem do filtro de uma barra (`campo = 'valor'` / `IS NULL`) é a contagem da barra (é o que o mapa
    seleciona ao clicar — portão, provado no e2e com o mapa);
  * refutação: 5.000 categorias viram N maiores + `outros` coerente e a resposta fica < 1 MB; campo todo nulo;
    datas fora de faixa (ano 1, ano 9999, infinity); filtro hostil = 400, campo/tipo errado = 422, nunca 500;
  * camada de 1 mi de linhas (bancada `scripts/mapa_demo_camadas.py criar`) responde ≤ 500 ms p95 (portão,
    marcado `lento`; salta sem a bancada)."""

import json
import statistics
import time

import numpy as np
import psycopg2.extras
import pytest

from app import limites
from app.estatistica.rotas import limpar_cache
from tests.api.catalogo.conftest import titulo_zt

ITEM = "L2-01-i-graficos-de-camada"


def _criar_camada(itens_a, conexao_plat_app, linhas, colunas_extra=""):
    """plat_trabalho.<tabela>(id, categoria text, valor float8, y float8, quando timestamptz, geom) + item."""
    tabela = "zt_graf_" + titulo_zt()[-8:].replace(" ", "_")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, categoria text, valor double precision, "
            f"y double precision, inteiro integer, quando timestamptz{colunas_extra}, geom geometry(Point, 4326))"
        )
        if linhas:
            psycopg2.extras.execute_values(
                cur, f"INSERT INTO plat_trabalho.{tabela}(categoria, valor, y, inteiro, quando, geom) VALUES %s",
                linhas, template="(%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))", page_size=2000,
            )
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326, "fonte": "hospedada",
            "campos": [{"nome": "categoria", "tipo": "text"}, {"nome": "valor", "tipo": "double precision"},
                       {"nome": "y", "tipo": "double precision"}, {"nome": "inteiro", "tipo": "integer"},
                       {"nome": "quando", "tipo": "timestamp"}],
        },
    )
    return it, tabela


def _dados(n=3000, semente=7):
    rng = np.random.default_rng(semente)
    x = rng.uniform(0, 100, n)
    y = 3 * x + 7 + rng.normal(0, 5, n)
    linhas = []
    for i in range(n):
        cat = None if i % 25 == 0 else f"c{i % 7}"
        val = None if i % 40 == 0 else float(x[i])
        linhas.append((cat, val, float(y[i]), int(i % 100), f"2026-{1 + i % 12:02d}-{1 + i % 27:02d} 12:00:00-03",
                       -47.9 + (i % 10) * 0.01, -15.8 + (i // 10 % 10) * 0.01))
    return linhas, x, y


@pytest.fixture
def camada(itens_a, conexao_plat_app):
    """uma tabela por teste (a fixture de conexão é por função); o custo é 3.000 linhas, desprezível."""
    linhas, x, y = _dados()
    it, tabela = _criar_camada(itens_a, conexao_plat_app, linhas)
    return {"item": it, "tabela": tabela, "x": x, "y": y, "linhas": linhas}


def _grafico(sessao_a, item_id, corpo, esperado=200):
    limpar_cache()
    r = sessao_a.post(f"/api/camadas/{item_id}/grafico", json=corpo)
    assert r.status_code == esperado, r.text
    assert len(r.content) <= limites.GRAFICO_RESPOSTA_BYTES_MAX, len(r.content)
    return r.json()


def _sql(conexao_plat_app, sql, params=()):
    with conexao_plat_app.cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


@pytest.mark.parametrize("estatistica, expr", [("count", "count(*)"), ("sum", "sum(valor)"), ("avg", "avg(valor)")])
def test_cada_barra_bate_com_sql_direto(sessao_a, conexao_plat_app, camada, estatistica, expr):
    corpo = {"tipo": "barras", "campo": "categoria", "estatistica": estatistica, "max_categorias": 500}
    if estatistica != "count":
        corpo["campo_y"] = "valor"
    j = _grafico(sessao_a, camada["item"]["id"], corpo)
    mao = {r["categoria"]: r["v"] for r in _sql(
        conexao_plat_app, f"SELECT categoria, {expr} AS v FROM plat_trabalho.{camada['tabela']} GROUP BY 1")}
    assert len(j["series"]) == len(mao) == 8  # 7 categorias + a nula
    for barra in j["series"]:
        ref = mao[barra["chave"]]
        assert barra["valor"] == pytest.approx(float(ref), rel=1e-9), (barra, ref)
    assert j["total"] == len(camada["linhas"]) and j["truncado"] is False and j["outros"] is None
    assert j["nulos"] == sum(1 for linha in camada["linhas"] if linha[0] is None)
    # ordenado por valor decrescente: é a ordem que o gráfico desenha
    valores = [b["valor"] if b["valor"] is not None else float("-inf") for b in j["series"]]
    assert valores == sorted(valores, reverse=True)


def test_histograma_10_faixas_confere_com_numpy(sessao_a, camada):
    j = _grafico(sessao_a, camada["item"]["id"], {"tipo": "histograma", "campo": "valor", "faixas": 10})
    validos = np.array([linha[1] for linha in camada["linhas"] if linha[1] is not None])
    contas, bordas = np.histogram(validos, bins=10)
    assert [s["n"] for s in j["series"]] == contas.tolist()
    assert j["bordas"] == bordas.tolist()  # bordas IDÊNTICAS (mesma aritmética de linspace), não aproximadas
    assert j["nulos"] == len(camada["linhas"]) - len(validos)
    assert sum(s["n"] for s in j["series"]) == len(validos)
    assert [s["de"] for s in j["series"]] == bordas[:-1].tolist()
    assert [s["ate"] for s in j["series"]] == bordas[1:].tolist()


@pytest.mark.parametrize("faixas", [1, 3, 10, 37])
def test_histograma_de_inteiros_nas_bordas_confere_com_numpy(sessao_a, camada, faixas):
    """inteiros 0..99: valores caem EXATAMENTE nas bordas — o caso em que floor((x-lo)/(hi-lo)*N) e a busca binária
    nas bordas podem divergir por 1 ulp; as bordas vêm do mesmo linspace, então as contagens têm de ser iguais."""
    j = _grafico(sessao_a, camada["item"]["id"], {"tipo": "histograma", "campo": "inteiro", "faixas": faixas})
    inteiros = np.array([linha[3] for linha in camada["linhas"]])
    contas, bordas = np.histogram(inteiros, bins=faixas)
    assert [s["n"] for s in j["series"]] == contas.tolist(), faixas
    assert j["bordas"] == bordas.tolist()


def test_histograma_de_um_valor_so_e_de_campo_nulo(sessao_a, itens_a, conexao_plat_app):
    linhas = [("a", 42.0, None, 1, None, -47.9, -15.8)] * 12 + [("b", None, None, 2, None, -47.9, -15.8)] * 3
    it, _ = _criar_camada(itens_a, conexao_plat_app, linhas)
    j = _grafico(sessao_a, it["id"], {"tipo": "histograma", "campo": "valor", "faixas": 10})
    contas, bordas = np.histogram(np.array([42.0] * 12), bins=10)
    assert [s["n"] for s in j["series"]] == contas.tolist() and j["bordas"] == bordas.tolist()
    assert j["nulos"] == 3 and j["total"] == 15
    # campo TODO nulo (refutação): resposta vazia e honesta, não 500
    j = _grafico(sessao_a, it["id"], {"tipo": "histograma", "campo": "y", "faixas": 10})
    assert j["series"] == [] and j["bordas"] == [] and j["nulos"] == 15 and j["total"] == 15
    j = _grafico(sessao_a, it["id"], {"tipo": "barras", "campo": "y"})
    assert j["series"] == [{"chave": None, "n": 15, "valor": 15}] and j["nulos"] == 15
    j = _grafico(sessao_a, it["id"], {"tipo": "dispersao", "campo": "valor", "campo_y": "y"})
    assert j["regressao"] is None and j["series"] == [] and j["nulos"] == 15
    j = _grafico(sessao_a, it["id"], {"tipo": "linha", "campo": "quando", "granularidade": "mes"})
    assert j["series"] == [{"chave": None, "n": 15, "valor": 15}] and j["nulos"] == 15


def test_regressao_confere_com_numpy_polyfit(sessao_a, camada):
    corpo = {"tipo": "dispersao", "campo": "valor", "campo_y": "y", "amostra": 500}
    j = _grafico(sessao_a, camada["item"]["id"], corpo)
    pares = [(linha[1], linha[2]) for linha in camada["linhas"] if linha[1] is not None]
    x = np.array([p[0] for p in pares])
    y = np.array([p[1] for p in pares])
    a, b = np.polyfit(x, y, 1)
    reg = j["regressao"]
    assert abs(reg["a"] - a) <= 1e-6 and abs(reg["b"] - b) <= 1e-6, (reg, a, b)
    assert abs(reg["r2"] - np.corrcoef(x, y)[0, 1] ** 2) <= 1e-9
    assert reg["n"] == len(pares) and j["nulos"] == len(camada["linhas"]) - len(pares)
    # a amostra desenhada é limitada e declarada como amostra; a regressão usa TODAS as linhas
    assert 10 <= len(j["series"]) <= 500 and j["amostra"] is True
    assert j["x_min"] == pytest.approx(float(x.min())) and j["x_max"] == pytest.approx(float(x.max()))
    # camada pequena: sem TABLESAMPLE, todos os pontos vêm
    j2 = _grafico(sessao_a, camada["item"]["id"], {**corpo, "amostra": 5000})
    assert len(j2["series"]) == len(pares) and j2["amostra"] is False


def test_contagem_do_filtro_da_barra_e_a_contagem_da_barra(sessao_a, camada):
    """é o que o clique na barra faz no mapa: filtro `campo = 'valor'` → contagem selecionada == barra."""
    barras = _grafico(sessao_a, camada["item"]["id"], {"tipo": "barras", "campo": "categoria"})["series"]
    for barra in barras:
        filtro = "categoria IS NULL" if barra["chave"] is None else f"categoria = '{barra['chave']}'"
        c = _grafico(sessao_a, camada["item"]["id"], {"tipo": "contagem", "filtro": filtro})
        assert c["total"] == barra["n"], (barra, c)
    # histograma: a faixa vira `campo >= de AND campo < ate` (última: <= ate)
    h = _grafico(sessao_a, camada["item"]["id"], {"tipo": "histograma", "campo": "valor", "faixas": 5})
    for i, faixa in enumerate(h["series"]):
        op = "<=" if i == len(h["series"]) - 1 else "<"
        c = _grafico(sessao_a, camada["item"]["id"],
                     {"tipo": "contagem", "filtro": f"valor >= {faixa['de']!r} AND valor {op} {faixa['ate']!r}"})
        assert c["total"] == faixa["n"], (faixa, c)


def test_filtro_e_extensao_reagem_no_grafico(sessao_a, conexao_plat_app, camada):
    t = camada["tabela"]
    j = _grafico(sessao_a, camada["item"]["id"],
                 {"tipo": "barras", "campo": "categoria", "estatistica": "sum", "campo_y": "valor",
                  "filtro": "(inteiro < 50 OR categoria = 'c3') AND valor IS NOT NULL"})
    mao = {r["categoria"]: float(r["v"]) for r in _sql(
        conexao_plat_app, f"SELECT categoria, sum(valor) AS v FROM plat_trabalho.{t} "
                          f"WHERE (inteiro < 50 OR categoria = 'c3') AND valor IS NOT NULL GROUP BY 1")}
    assert {b["chave"]: pytest.approx(b["valor"]) for b in j["series"]} == mao
    ext = {"xmin": -47.9, "ymin": -15.8, "xmax": -47.85, "ymax": -15.75}
    j = _grafico(sessao_a, camada["item"]["id"], {"tipo": "contagem", "extensao": ext})
    n = _sql(conexao_plat_app, f"SELECT count(*) AS n FROM plat_trabalho.{t} "
                               f"WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
             (ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"]))[0]["n"]
    assert 0 < j["total"] == n < len(camada["linhas"])


def test_linha_por_mes_e_por_dia_batem_com_sql(sessao_a, conexao_plat_app, camada):
    t = camada["tabela"]
    for gran, unidade in (("mes", "month"), ("dia", "day")):
        j = _grafico(sessao_a, camada["item"]["id"],
                     {"tipo": "linha", "campo": "quando", "granularidade": gran, "estatistica": "avg", "campo_y": "y"})
        mao = _sql(conexao_plat_app,
                   f"SELECT date_trunc('{unidade}', quando AT TIME ZONE 'America/Sao_Paulo') AS f, count(*) AS n, "
                   f"avg(y) AS v FROM plat_trabalho.{t} GROUP BY 1 ORDER BY 1")
        assert len(j["series"]) == len(mao)
        for s, m in zip(j["series"], mao, strict=True):
            assert s["n"] == m["n"] and s["valor"] == pytest.approx(float(m["v"]))
            if m["f"] is None:
                assert s["chave"] is None
            else:
                assert s["chave"][:10] == m["f"].strftime("%Y-%m-%d"), (s, m)


def test_5000_categorias_viram_maiores_mais_outros_e_resposta_abaixo_de_1_mb(sessao_a, itens_a, conexao_plat_app):
    linhas = [(f"cat-{i % 5000:04d}", float(i % 977), None, i % 100, None, -47.9, -15.8) for i in range(15000)]
    it, t = _criar_camada(itens_a, conexao_plat_app, linhas)
    for estat, mx in (("count", 50), ("sum", 500), ("avg", 1)):
        corpo = {"tipo": "pizza", "campo": "categoria", "estatistica": estat, "max_categorias": mx}
        if estat != "count":
            corpo["campo_y"] = "valor"
        j = _grafico(sessao_a, it["id"], corpo)
        assert len(j["series"]) == mx and j["truncado"] is True and j["grupos"] == 5000
        assert j["outros"]["categorias"] == 5000 - mx
        assert j["outros"]["n"] + sum(s["n"] for s in j["series"]) == 15000 == j["total"]
        if estat == "sum":
            total = _sql(conexao_plat_app, f"SELECT sum(valor) AS s FROM plat_trabalho.{t}")[0]["s"]
            assert j["outros"]["valor"] + sum(s["valor"] for s in j["series"]) == pytest.approx(float(total))
        if estat == "avg":
            resto = _sql(conexao_plat_app, f"SELECT avg(valor) AS a FROM plat_trabalho.{t} WHERE categoria <> %s",
                         (j["series"][0]["chave"],))[0]["a"]
            assert j["outros"]["valor"] == pytest.approx(float(resto))
    # o teto de categorias é o do limites.py, nunca a tabela inteira
    _grafico(sessao_a, it["id"], {"tipo": "barras", "campo": "categoria", "max_categorias": 5000}, esperado=422)


def test_datas_fora_de_faixa_nao_derrubam_a_linha(sessao_a, itens_a, conexao_plat_app):
    linhas = [("a", 1.0, None, 1, "0001-01-01 00:00:00+00", -47.9, -15.8),
              ("a", 1.0, None, 1, "9999-12-31 23:59:59+00", -47.9, -15.8),
              ("a", 1.0, None, 1, "2026-07-31 23:30:00-03", -47.9, -15.8),
              ("a", 1.0, None, 1, "2026-08-01 00:05:00-03", -47.9, -15.8),
              ("a", 1.0, None, 1, None, -47.9, -15.8)]
    it, t = _criar_camada(itens_a, conexao_plat_app, linhas)
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"INSERT INTO plat_trabalho.{t}(categoria, quando, geom) VALUES "
                    f"('a', 'infinity', ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326)), "
                    f"('a', '-infinity', ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326))")
    conexao_plat_app.commit()
    for gran in ("ano", "mes", "dia"):
        j = _grafico(sessao_a, it["id"], {"tipo": "linha", "campo": "quando", "granularidade": gran})
        assert j["total"] == 7 and j["nulos"] == 1
        assert sum(s["n"] for s in j["series"]) == 7
    j = _grafico(sessao_a, it["id"], {"tipo": "linha", "campo": "quando", "granularidade": "mes"})
    faixas = [s["chave"] for s in j["series"] if s["chave"]]
    # 31/07 23:30 America/Sao_Paulo fica em JULHO e 01/08 00:05 em AGOSTO (corte no fuso, herdado do L2-06-e);
    # ano 1 UTC truncado no fuso vira ano 1 a.C. ("BC", que o datetime do Python não tem: por isso a faixa é TEXTO)
    assert any(f.startswith("2026-07") for f in faixas) and any(f.startswith("2026-08") for f in faixas)
    assert "infinity" in faixas and "-infinity" in faixas and any(f.endswith(" BC") for f in faixas), faixas


@pytest.mark.parametrize("corpo, status, erro", [
    ({"tipo": "radar", "campo": "categoria"}, 422, "tipo_invalido"),
    ({"tipo": "barras"}, 422, "identificador_invalido"),
    ({"tipo": "barras", "campo": "nao_existe"}, 422, "campo_inexistente"),
    ({"tipo": "barras", "campo": "geom"}, 422, "campo_inexistente"),
    ({"tipo": "barras", "campo": "categoria; DROP TABLE x"}, 422, "identificador_invalido"),
    ({"tipo": "histograma", "campo": "categoria"}, 422, "campo_tipo_invalido"),
    ({"tipo": "histograma", "campo": "valor", "faixas": 0}, 422, "faixas_invalido"),
    ({"tipo": "histograma", "campo": "valor", "faixas": 10**6}, 422, "faixas_invalido"),
    ({"tipo": "barras", "campo": "categoria", "estatistica": "sum"}, 422, "campo_y_obrigatorio"),
    ({"tipo": "barras", "campo": "categoria", "estatistica": "median", "campo_y": "valor"}, 422,
     "estatistica_invalida"),
    ({"tipo": "linha", "campo": "valor"}, 422, "campo_tipo_invalido"),
    ({"tipo": "linha", "campo": "quando", "granularidade": "hora"}, 422, "granularidade_invalida"),
    ({"tipo": "dispersao", "campo": "valor"}, 422, "campo_y_obrigatorio"),
    ({"tipo": "dispersao", "campo": "valor", "campo_y": "categoria"}, 422, "campo_tipo_invalido"),
    ({"tipo": "contagem", "filtro": "categoria = 'a' OR 1=1; --"}, 400, "caractere_invalido"),
    ({"tipo": "contagem", "filtro": "tenant_id = 1"}, 400, "campo_nao_permitido"),
    ({"tipo": "contagem", "filtro": "pg_sleep(10) = 1"}, 400, "sintaxe_invalida"),
    ({"tipo": "contagem", "extensao": {"xmin": "a"}}, 422, "extensao_invalida"),
    ({"tipo": "dispersao", "campo": "valor", "campo_y": "y", "amostra": 10**7}, 422, "amostra_invalido"),
])
def test_recusas_com_codigo_nunca_500(sessao_a, camada, corpo, status, erro):
    limpar_cache()
    r = sessao_a.post(f"/api/camadas/{camada['item']['id']}/grafico", json=corpo)
    assert r.status_code == status, r.text
    assert r.json()["erro"] == erro, r.text


def test_item_que_nao_e_camada_e_404(sessao_a, itens_a):
    mapa = itens_a.criar("mapa")
    r = sessao_a.post(f"/api/camadas/{mapa['id']}/grafico", json={"tipo": "contagem"})
    assert r.status_code == 404, r.text


def test_cache_devolve_o_mesmo_com_marca(sessao_a, camada):
    corpo = {"tipo": "barras", "campo": "categoria"}
    a = _grafico(sessao_a, camada["item"]["id"], corpo)
    b = sessao_a.post(f"/api/camadas/{camada['item']['id']}/grafico", json=corpo).json()
    assert b["cache"] is True and a["cache"] is False
    assert b["series"] == a["series"]


@pytest.mark.lento
def test_camada_de_1_milhao_responde_em_ate_500_ms_p95(sessao_a, medida):
    r = sessao_a.get("/api/mapa/camadas")
    assert r.status_code == 200, r.text
    fichas = [c for c in r.json()["camadas"] if "mapa-1mi (L2-01" in c["titulo"]]
    if not fichas:
        pytest.skip("bancada ausente: rode scripts/mapa_demo_camadas.py criar (1 mi de pontos)")
    item = fichas[0]["id"]
    assert fichas[0]["n_feicoes"] >= 1_000_000
    pedidos = {
        "barras_1mi": {"tipo": "barras", "campo": "categoria", "estatistica": "avg", "campo_y": "valor"},
        "pizza_1mi": {"tipo": "pizza", "campo": "categoria"},
        "histograma_1mi": {"tipo": "histograma", "campo": "valor", "faixas": 10},
        "dispersao_1mi": {"tipo": "dispersao", "campo": "fid", "campo_y": "valor"},
        "contagem_filtro_1mi": {"tipo": "contagem", "filtro": "categoria = 'norte'"},
    }
    gravar = medida(ITEM)
    for nome, corpo in pedidos.items():
        tempos = []
        for _ in range(20):
            limpar_cache()
            t0 = time.perf_counter()
            r = sessao_a.post(f"/api/camadas/{item}/grafico", json=corpo)
            tempos.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200, r.text
            assert len(r.content) <= limites.GRAFICO_RESPOSTA_BYTES_MAX
        p95 = sorted(tempos)[int(0.95 * len(tempos)) - 1]
        comando = f"20 pedidos POST /api/camadas/{{id}}/grafico {json.dumps(corpo)}"
        gravar(f"{nome}_p95_ms", round(p95, 1), "ms", comando)
        gravar(f"{nome}_mediana_ms", round(statistics.median(tempos), 1), "ms", "idem, mediana")
        gravar(f"{nome}_bytes", len(r.content), "bytes", "tamanho da resposta")
        assert p95 <= 500, (nome, p95, tempos)
