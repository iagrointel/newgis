"""Rota `/api/camadas/{id}/estatisticas` (item L2-06-e-estatisticas-servidor): 10 consultas de
referência batem com SQL à mão, faixa de mês respeita o fuso, 1 mi de linhas/100 categorias em <= 500 ms
p95, cache HIT <= 20 ms, grupo acima do limite = 422, e a MESMA rota alimenta `outStatistics`."""

import time

import pytest

from app.estatistica.rotas import limpar_cache
from tests.api.catalogo.conftest import titulo_zt

ITEM = "L2-06-e-estatisticas-servidor"


def _criar_camada_com_dados(itens_a, conexao_plat_app, linhas):
    """cria plat_trabalho.<tabela> com (id, categoria text, valor numeric, quando timestamptz) e
    registra no catálogo como camada_vetorial hospedada — mesmo padrão de test_lixeira.py."""
    tabela = "zt_estat_" + titulo_zt()[-8:].replace(" ", "_")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f"CREATE TABLE plat_trabalho.{tabela} "
            "(id serial PRIMARY KEY, categoria text, valor numeric, quando timestamptz, geom geometry(Point, 4326))"
        )
        if linhas:
            psycopg2_extras_execute_values(cur, tabela, linhas)
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}, {"nome": "categoria", "tipo": "text"},
                       {"nome": "valor", "tipo": "numeric"}, {"nome": "quando", "tipo": "timestamp"}],
            "fonte": "hospedada",
        },
    )
    return it, tabela


def psycopg2_extras_execute_values(cur, tabela, linhas):
    import psycopg2.extras

    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO plat_trabalho.{tabela}(categoria, valor, quando, geom) VALUES %s",
        linhas,
        template="(%s, %s, %s, ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326))",
    )


DADOS_REFERENCIA = [
    (f"cat{i % 5}", float((i * 37) % 953) / 3.0, f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d} 12:00:00-03")
    for i in range(600)
]


@pytest.fixture
def camada_referencia(itens_a, conexao_plat_app):
    it, tabela = _criar_camada_com_dados(itens_a, conexao_plat_app, DADOS_REFERENCIA)
    yield it, tabela


CONSULTAS_REFERENCIA = [
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}]},
     'SELECT categoria, sum(valor) AS s FROM plat_trabalho.{t} GROUP BY categoria ORDER BY 1'),
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "avg", "alias": "m"}]},
     'SELECT categoria, avg(valor) AS m FROM plat_trabalho.{t} GROUP BY categoria ORDER BY 1'),
    ({"estatisticas": [{"campo": "valor", "tipo": "percentile", "percentil": 90, "alias": "p90"}]},
     'SELECT percentile_cont(0.9) WITHIN GROUP (ORDER BY valor) AS p90 FROM plat_trabalho.{t}'),
    ({"estatisticas": [{"campo": "categoria", "tipo": "count_distinct", "alias": "nd"}]},
     'SELECT count(DISTINCT categoria) AS nd FROM plat_trabalho.{t}'),
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}],
      "having": "s > 1000"},
     'SELECT categoria, sum(valor) AS s FROM plat_trabalho.{t} GROUP BY categoria HAVING sum(valor) > 1000 ORDER BY 1'),
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "min", "alias": "mn"},
                                                 {"campo": "valor", "tipo": "max", "alias": "mx"}]},
     'SELECT categoria, min(valor) AS mn, max(valor) AS mx FROM plat_trabalho.{t} GROUP BY categoria ORDER BY 1'),
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "id", "tipo": "count", "alias": "n"}]},
     'SELECT categoria, count(id) AS n FROM plat_trabalho.{t} GROUP BY categoria ORDER BY 1'),
    ({"estatisticas": [{"campo": "valor", "tipo": "stddev", "alias": "d"}]},
     'SELECT stddev(valor) AS d FROM plat_trabalho.{t}'),
    ({"estatisticas": [{"campo": "valor", "tipo": "var", "alias": "v"}]},
     'SELECT variance(valor) AS v FROM plat_trabalho.{t}'),
    ({"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}],
      "filtro": "valor > 100"},
     'SELECT categoria, sum(valor) AS s FROM plat_trabalho.{t} WHERE valor > 100 GROUP BY categoria ORDER BY 1'),
]


@pytest.mark.parametrize("pedido,sql_mao", CONSULTAS_REFERENCIA)
def test_consulta_de_referencia_bate_com_sql_a_mao(sessao_a, camada_referencia, conexao_plat_app, pedido, sql_mao):
    it, tabela = camada_referencia
    limpar_cache()
    r = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=pedido)
    assert r.status_code == 200, r.text
    linhas_rota = r.json()["linhas"]

    # `conexao_plat_app` usa RealDictCursor (fixture do conftest): a linha já vem como dict.
    with conexao_plat_app.cursor() as tcur:
        tcur.execute(sql_mao.format(t=tabela))
        linhas_mao = [dict(row) for row in tcur.fetchall()]

    def normaliza(v):
        if hasattr(v, "quantize"):  # decimal.Decimal
            return round(float(v), 6)
        return round(float(v), 6) if isinstance(v, (int, float)) else v

    rota_norm = sorted(
        [{k: normaliza(v) for k, v in linha.items()} for linha in linhas_rota],
        key=lambda d: str(d),
    )
    mao_norm = sorted(
        [{k: normaliza(v) for k, v in linha.items()} for linha in linhas_mao],
        key=lambda d: str(d),
    )
    assert rota_norm == mao_norm


def test_faixa_de_mes_respeita_fronteira_do_fuso(sessao_a, itens_a, conexao_plat_app):
    """31/07 23:30 America/Sao_Paulo (UTC-3) é 01/08 02:30 UTC — tem de cair na faixa de JULHO, não
    agosto, e uma linha de 01/08 00:05 America/Sao_Paulo tem de cair em AGOSTO."""
    linhas = [
        ("x", 1.0, "2026-07-31 23:30:00-03"),
        ("x", 2.0, "2026-08-01 00:05:00-03"),
    ]
    it, tabela = _criar_camada_com_dados(itens_a, conexao_plat_app, linhas)
    limpar_cache()
    r = sessao_a.post(
        f"/api/camadas/{it['id']}/estatisticas",
        json={
            "faixa_data": {"campo": "quando", "granularidade": "mes", "fuso": "America/Sao_Paulo"},
            "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}],
            "ordenacao": "faixa",
        },
    )
    assert r.status_code == 200, r.text
    linhas_resp = r.json()["linhas"]
    assert len(linhas_resp) == 2
    assert linhas_resp[0]["faixa"].startswith("2026-07") and linhas_resp[0]["s"] == 1.0
    assert linhas_resp[1]["faixa"].startswith("2026-08") and linhas_resp[1]["s"] == 2.0


@pytest.mark.lento
def test_um_milhao_de_linhas_100_categorias_p95(sessao_a, itens_a, conexao_plat_app, medida):
    carga = float(open("/proc/loadavg").read().split()[0])
    if carga > 8:
        pytest.skip(f"carga_1min={carga:.1f} > 8: não mede desempenho com a máquina ocupada")
    tabela = "zt_estat_perf_" + titulo_zt()[-6:]
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            f"CREATE TABLE plat_trabalho.{tabela} "
            "(id serial PRIMARY KEY, categoria integer, valor double precision, geom geometry(Point, 4326))"
        )
        cur.execute(
            f"INSERT INTO plat_trabalho.{tabela}(categoria, valor, geom) "
            "SELECT (g % 100), random() * 1000, ST_SetSRID(ST_MakePoint(-47.9, -15.8), 4326) "
            "FROM generate_series(1, 1000000) g"
        )
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}, {"nome": "categoria", "tipo": "integer"},
                       {"nome": "valor", "tipo": "double"}],
            "fonte": "hospedada",
        },
    )
    pedido = {"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "avg", "alias": "m"}]}
    tempos = []
    for _ in range(7):
        limpar_cache()
        t0 = time.perf_counter()
        r = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=pedido)
        tempos.append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text
        assert r.json()["total_grupos"] == 100
    tempos.sort()
    p95 = tempos[int(len(tempos) * 0.95) if int(len(tempos) * 0.95) < len(tempos) else -1]
    ram_livre = int(open("/proc/meminfo").readlines()[1].split()[1]) // (1024 * 1024)
    medida(ITEM)("agregacao_1mi_100cat_p95_ms", round(p95 * 1000, 1), "ms",
                 f"pytest tests/api/test_estatisticas.py::test_um_milhao_de_linhas_100_categorias_p95 "
                 f"(carga_1min={carga:.2f}, ram_livre_gb={ram_livre})")
    assert p95 <= 0.5, f"p95={p95*1000:.1f}ms > 500ms (carga_1min={carga:.2f})"


def test_cache_hit_no_segundo_pedido_igual(sessao_a, camada_referencia):
    it, tabela = camada_referencia
    limpar_cache()
    pedido = {"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}]}
    r1 = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=pedido)
    assert r1.status_code == 200 and r1.json()["cache"] is False
    t0 = time.perf_counter()
    r2 = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=pedido)
    dt = time.perf_counter() - t0
    assert r2.status_code == 200 and r2.json()["cache"] is True
    assert r2.json()["linhas"] == r1.json()["linhas"]
    assert dt <= 0.020, f"cache HIT levou {dt*1000:.2f} ms > 20 ms"


def test_grupo_acima_do_limite_e_422(sessao_a, itens_a, conexao_plat_app):
    tabela = "zt_estat_limite_" + titulo_zt()[-6:]
    with conexao_plat_app.cursor() as cur:
        cur.execute(f"CREATE TABLE plat_trabalho.{tabela} (id serial PRIMARY KEY, categoria integer)")
        cur.execute(
            f"INSERT INTO plat_trabalho.{tabela}(categoria) SELECT g FROM generate_series(1, 10005) g"
        )
    conexao_plat_app.commit()
    it = itens_a.criar(
        "camada_vetorial",
        dados={
            "schema": "plat_trabalho", "tabela": tabela, "geometria": "Point", "srid": 4326,
            "campos": [{"nome": "id", "tipo": "integer"}, {"nome": "categoria", "tipo": "integer"}],
            "fonte": "hospedada",
        },
    )
    limpar_cache()
    r = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json={"grupos": ["categoria"]})
    assert r.status_code == 422
    assert r.json()["erro"] == "limite_de_grupos_excedido"


def test_percentil_150_reprova(sessao_a, camada_referencia):
    it, _ = camada_referencia
    r = sessao_a.post(
        f"/api/camadas/{it['id']}/estatisticas",
        json={"estatisticas": [{"campo": "valor", "tipo": "percentile", "percentil": 150, "alias": "p"}]},
    )
    assert r.status_code == 422


def test_agrupar_por_geometria_reprova(sessao_a, camada_referencia):
    it, _ = camada_referencia
    r = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json={"grupos": ["geom"]})
    assert r.status_code == 422


def test_50_estatisticas_no_mesmo_pedido(sessao_a, camada_referencia):
    it, _ = camada_referencia
    stats = [{"campo": "valor", "tipo": "sum", "alias": f"s{i}"} for i in range(50)]
    r = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json={"estatisticas": stats})
    assert r.status_code == 200, r.text
    stats51 = stats + [{"campo": "valor", "tipo": "avg", "alias": "extra"}]
    r51 = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json={"estatisticas": stats51})
    assert r51.status_code == 422


def test_mesma_rota_alimenta_outstatistics(sessao_a, camada_referencia):
    """compara o caminho `outStatistics` (Esri) com o pedido canônico equivalente escrito à mão — a
    mesma rota, o mesmo motor (`agregacao.traduzir_outstatistics` -> `montar_pedido` -> `construir_sql`)."""
    it, _ = camada_referencia
    q_esri = {
        "outStatistics": [{"statisticType": "sum", "onStatisticField": "valor", "outStatisticFieldName": "s"}],
        "groupByFieldsForStatistics": "categoria",
    }
    from app.estatistica.agregacao import traduzir_outstatistics

    corpo_esri = traduzir_outstatistics(q_esri)
    corpo_canonico = {"grupos": ["categoria"], "estatisticas": [{"campo": "valor", "tipo": "sum", "alias": "s"}]}

    limpar_cache()
    r_esri = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=corpo_esri)
    limpar_cache()
    r_canonico = sessao_a.post(f"/api/camadas/{it['id']}/estatisticas", json=corpo_canonico)
    assert r_esri.status_code == 200 and r_canonico.status_code == 200
    assert sorted(r_esri.json()["linhas"], key=str) == sorted(r_canonico.json()["linhas"], key=str)
