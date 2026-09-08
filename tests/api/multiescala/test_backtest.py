"""Backtest contra decisão REAL sobre DADO ABERTO (item L3-09-backtest-decisao-real), pela API:
`POST /api/multiescala/execucoes/{id}/backtest`.

O dado aberto desta casa: `cbre.osm_buildings_ind` (OpenStreetMap, prédios industriais) e `cbre.osm_roads`
(vias). A plataforma NÃO lê esse schema — o papel do inquilino é isolado dele, e assim tem de ser. Quem lê é a
FIXTURE, como a casa leria qualquer dado aberto antes de trazê-lo: os pontos das escolhas e as amostras do
fator entram na plataforma pela API dela mesma. Sem o dado no banco, a suíte é pulada com a razão.

Montagem: janela de ~30 km × 22 km sobre Guarulhos e entorno; fator "proximidade de via arterial" (100·e^(−d/2 km)
até a via motorway/trunk/primary mais próxima, uma amostra por célula); grade macro de 500 m; escolhas = centróide
dos galpões OSM com área > 5.000 m² dentro da janela (a mesma regra que o item nomeia).
Cláusulas provadas aqui: relatório com AUC, percentil mediano, nulo e p-valor sobre o dado aberto; escolhas
sintéticas do próprio modelo com AUC ≥ 0,95 e aleatórias 0,5 ± 0,05 pela API; camada anacrônica marcada.
Refutação: escolhas = todas as células (AUC indefinida, com a frase) e escolhas fora da grade (contagem)."""

from __future__ import annotations

import secrets
import shutil
import subprocess

import pytest

from tests.api.test_rls import contexto, ids_por_slug

JANELA = {"lon0": -46.65, "lat0": -23.55, "lon1": -46.35, "lat1": -23.35}
RESOLUCAO_M = 500.0
PASSO_LON, PASSO_LAT = 0.005, 0.0045   # ~500 m nesta latitude


def _psql(sql: str) -> list[list[str]]:
    """Lê o dado aberto da casa como `postgres` (a plataforma não tem acesso ao schema, e não deve ter)."""
    if not shutil.which("sudo"):
        pytest.skip("sem sudo nesta máquina para ler o dado aberto da casa")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", "iagro_sat", "-At", "-F", "|", "-c", sql],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        pytest.skip(f"dado aberto indisponível nesta instalação: {r.stderr.strip()[:200]}")
    return [linha.split("|") for linha in r.stdout.splitlines() if linha.strip()]


@pytest.fixture(scope="module")
def dado_aberto():
    linhas = _psql("SELECT to_regclass('cbre.osm_buildings_ind')::text, to_regclass('cbre.osm_roads')::text")
    if not linhas or linhas[0][0] in ("", None) or linhas[0][1] in ("", None):
        pytest.skip("cbre.osm_buildings_ind / cbre.osm_roads ausentes nesta instalação")
    galpoes = _psql(
        "SELECT round(ST_X(ST_PointOnSurface(geom))::numeric,6), round(ST_Y(ST_PointOnSurface(geom))::numeric,6) "
        f"FROM cbre.osm_buildings_ind WHERE area_m2 > 5000 AND ST_Intersects(geom, ST_MakeEnvelope("
        f"{JANELA['lon0']}, {JANELA['lat0']}, {JANELA['lon1']}, {JANELA['lat1']}, 4326))"
    )
    amostras = _psql(
        "WITH p AS (SELECT %s + %s*i AS lon, %s + %s*j AS lat FROM generate_series(0,60) i, "
        "generate_series(0,44) j) "
        "SELECT round(lon::numeric,6), round(lat::numeric,6), round((100*exp(-d/2000.0))::numeric,3) FROM ("
        "  SELECT lon, lat, (SELECT ST_Distance(g::geography, r.geom::geography) FROM cbre.osm_roads r "
        "          WHERE r.highway IN ('motorway','trunk','primary') ORDER BY r.geom <-> g LIMIT 1) AS d "
        "  FROM (SELECT lon, lat, ST_SetSRID(ST_MakePoint(lon,lat),4326) AS g FROM p) q) w WHERE d IS NOT NULL"
        % (JANELA["lon0"], PASSO_LON, JANELA["lat0"], PASSO_LAT)
    )
    if len(galpoes) < 100 or len(amostras) < 1000:
        pytest.skip(f"dado aberto insuficiente na janela: {len(galpoes)} galpões, {len(amostras)} amostras")
    return {
        "galpoes": [(float(a), float(b)) for a, b in galpoes],
        "amostras": [{"lon": float(a), "lat": float(b), "valor": float(c)} for a, b, c in amostras],
    }


@pytest.fixture(scope="module")
def execucao(sessao_a, dado_aberto):
    area = {"type": "Polygon", "coordinates": [[
        [JANELA["lon0"], JANELA["lat0"]], [JANELA["lon1"], JANELA["lat0"]],
        [JANELA["lon1"], JANELA["lat1"]], [JANELA["lon0"], JANELA["lat1"]],
        [JANELA["lon0"], JANELA["lat0"]]]]}
    r = sessao_a.post("/api/multiescala/conjuntos",
                      json={"nome": f"zt-backtest-{secrets.token_hex(4)}", "area": area})
    assert r.status_code == 201, r.text
    conjunto = r.json()
    r = sessao_a.post("/api/multiescala/fatores", json={
        "nome": "proximidade de via arterial (OSM)", "resolucao_fonte_m": 500.0, "papel": "atrai",
        "unidade": "índice", "fonte": "OpenStreetMap, vias motorway/trunk/primary (dado aberto)",
    })
    assert r.status_code == 201, r.text
    fator = r.json()
    ra = sessao_a.post(f"/api/multiescala/fatores/{fator['id']}/amostras",
                       json={"amostras": dado_aberto["amostras"]})
    assert ra.status_code == 201, ra.text
    r = sessao_a.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", json={
        "resolucao_m": RESOLUCAO_M, "fatores": [{"fator_id": fator["id"], "peso": 1.0}],
        "aprovacao_tipo": "top_pct", "aprovacao_valor": 25.0,
    })
    assert r.status_code == 201, r.text
    macro = r.json()
    assert macro["celulas_com_nota"] >= 1000, macro
    yield macro
    sessao_a.delete(f"/api/multiescala/conjuntos/{conjunto['id']}")
    sessao_a.delete(f"/api/multiescala/fatores/{fator['id']}")


def _backtest(sessao, eid, **corpo):
    r = sessao.post(f"/api/multiescala/execucoes/{eid}/backtest", json=corpo)
    return r


def test_relatorio_sobre_galpoes_reais_do_osm(sessao_a, execucao, dado_aberto, medida):
    pontos = [{"lon": lon, "lat": lat} for lon, lat in dado_aberto["galpoes"]]
    r = _backtest(sessao_a, execucao["id"], pontos=pontos, n_permutacoes=500, semente=7,
                  data_decisao="2026-01-01", data_camada="2025-06-01")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["escolhas_recebidas"] == len(pontos)
    assert j["n_escolhas"] >= 50 and j["n_unidades"] >= 1000
    assert j["auc"] is not None and 0.0 <= j["auc"] <= 1.0
    assert j["percentil_mediano"] is not None and j["p_valor"] is not None
    assert 0.45 <= j["nulo"]["auc_media"] <= 0.55, j["nulo"]
    assert j["permutacoes"] == 500 and j["anacronica"] is False
    assert any("não acerto futuro" in x for x in j["ressalvas"])
    assert any("distância" in x for x in j["ressalvas"])
    assert j["grade"]["resolucao_m"] == RESOLUCAO_M
    # preferência revelada do fator real, com sinal e sem peso
    nomes = {f["nome"] for f in j["fatores"]}
    assert "proximidade de via arterial (OSM)" in nomes
    fator = next(f for f in j["fatores"] if f["nome"] == "proximidade de via arterial (OSM)")
    assert fator["sinal"] in ("procurou", "evitou", "indiferente")
    assert "peso" not in fator
    m = medida("L3-09-backtest-decisao-real")
    m("galpoes_osm_na_janela", len(pontos), "galpoes", "OSM, prédio industrial com área > 5.000 m², 30 km × 22 km")
    m("auc_galpoes_osm", round(j["auc"], 4), "auc", "modelo de 1 fator (proximidade de via arterial) × galpões reais")
    m("percentil_mediano_galpoes", round(j["percentil_mediano"], 2), "percentil", "mediana das escolhas no ranking")
    m("p_valor_galpoes", j["p_valor"], "p", "nulo por permutação, 500 sorteios de igual número de unidades")
    m("celulas_da_grade", j["n_unidades"], "celulas", "grade macro de 500 m com nota")


def test_escolhas_do_modelo_e_ao_acaso_pela_api(sessao_a, execucao, conexao_plat_app, medida):
    """As mesmas duas calibragens do portão, agora ponta a ponta: as células mais favoráveis da execução como
    escolhas dão AUC alta; células sorteadas dão meio a meio."""
    import random

    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo"], usuario_id=1, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT ST_X(ST_PointOnSurface(c.geom)) AS lon, ST_Y(ST_PointOnSurface(c.geom)) AS lat, r.nota "
            "FROM plat.escala_resultado r JOIN plat.escala_celula c ON c.id = r.celula_id "
            "WHERE r.execucao_id = %s::uuid AND r.nota IS NOT NULL ORDER BY r.nota DESC", (execucao["id"],),
        )
        celulas = [dict(x) for x in cur.fetchall()]
    conexao_plat_app.rollback()
    assert len(celulas) >= 500
    n = max(50, len(celulas) // 20)
    melhores = [{"lon": c["lon"], "lat": c["lat"]} for c in celulas[:n]]
    j = _backtest(sessao_a, execucao["id"], pontos=melhores, n_permutacoes=200, semente=3).json()
    assert j["auc"] >= 0.95, j["auc"]
    assert j["p_valor"] <= 0.01
    sorteadas = random.Random(11).sample(celulas, n)
    j2 = _backtest(sessao_a, execucao["id"], pontos=[{"lon": c["lon"], "lat": c["lat"]} for c in sorteadas],
                   n_permutacoes=200, semente=3).json()
    assert 0.45 <= j2["auc"] <= 0.55, j2["auc"]
    m = medida("L3-09-backtest-decisao-real")
    m("auc_escolhas_do_modelo", round(j["auc"], 4), "auc", "as células mais favoráveis da execução como escolhas")
    m("auc_escolhas_ao_acaso", round(j2["auc"], 4), "auc", "mesmo número de células sorteadas na mesma grade")


def test_camada_anacronica_marcada(sessao_a, execucao, dado_aberto):
    pontos = [{"lon": lon, "lat": lat} for lon, lat in dado_aberto["galpoes"][:200]]
    j = _backtest(sessao_a, execucao["id"], pontos=pontos, n_permutacoes=50,
                  data_decisao="2015-01-01", data_camada="2026-09-01").json()
    assert j["anacronica"] is True
    assert any("ANACRÔNICO" in x for x in j["ressalvas"])


# ---- refutação do item
def test_escolhas_fora_da_grade_sao_contadas(sessao_a, execucao, dado_aberto):
    dentro = [{"lon": lon, "lat": lat} for lon, lat in dado_aberto["galpoes"][:100]]
    fora = [{"lon": -30.0, "lat": -5.0}, {"lon": -60.0, "lat": -15.0}, {"lon": 0.0, "lat": 0.0}]
    j = _backtest(sessao_a, execucao["id"], pontos=dentro + fora, n_permutacoes=50).json()
    assert j["n_fora"] >= 3, j
    assert j["escolhas_recebidas"] == len(dentro) + len(fora)
    so_fora = _backtest(sessao_a, execucao["id"], pontos=fora, n_permutacoes=50).json()
    assert so_fora["n_escolhas"] == 0 and so_fora["n_fora"] == 3
    assert so_fora["auc"] is None and "não há o que comparar" in so_fora["auc_indefinida"]


def test_todas_as_celulas_escolhidas_diz_que_a_auc_nao_existe(sessao_a, execucao, conexao_plat_app):
    contexto(conexao_plat_app, ids_por_slug(conexao_plat_app)["demo"], usuario_id=1, login="admin")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT ST_X(ST_PointOnSurface(c.geom)) AS lon, ST_Y(ST_PointOnSurface(c.geom)) AS lat "
            "FROM plat.escala_resultado r JOIN plat.escala_celula c ON c.id = r.celula_id "
            "WHERE r.execucao_id = %s::uuid AND r.nota IS NOT NULL", (execucao["id"],),
        )
        todas = [{"lon": float(x["lon"]), "lat": float(x["lat"])} for x in cur.fetchall()]
    conexao_plat_app.rollback()
    j = _backtest(sessao_a, execucao["id"], pontos=todas, n_permutacoes=50).json()
    assert j["auc"] is None
    assert "sem não-escolhas" in j["auc_indefinida"] and "não é 0,5 nem 1,0" in j["auc_indefinida"]
    assert j["percentil_mediano"] is not None


def test_recusas_da_rota(sessao_a, execucao):
    eid = execucao["id"]
    assert _backtest(sessao_a, eid).status_code == 422                       # nem item nem pontos
    r = _backtest(sessao_a, eid, pontos=[{"lon": -46.5, "lat": -23.5}],
                  escolhas_item_id="00000000-0000-4000-8000-000000000000")
    assert r.status_code == 422 and r.json()["erro"] == "escolhas_ausentes"   # os dois ao mesmo tempo
    r = _backtest(sessao_a, eid, escolhas_item_id="00000000-0000-4000-8000-000000000000")
    assert r.status_code == 404 and r.json()["erro"] == "camada_inexistente"
    nulo = "00000000-0000-4000-8000-000000000000"
    assert _backtest(sessao_a, nulo, pontos=[{"lon": -46.5, "lat": -23.5}]).status_code == 404
    r = _backtest(sessao_a, eid, pontos=[{"lon": -46.5, "lat": -23.5}], n_permutacoes=0)
    assert r.status_code == 422


def test_mesma_semente_mesmo_relatorio(sessao_a, execucao, dado_aberto):
    pontos = [{"lon": lon, "lat": lat} for lon, lat in dado_aberto["galpoes"][:150]]
    a = _backtest(sessao_a, execucao["id"], pontos=pontos, n_permutacoes=300, semente=5).json()
    b = _backtest(sessao_a, execucao["id"], pontos=pontos, n_permutacoes=300, semente=5).json()
    for chave in ("auc", "p_valor", "nulo", "percentil_mediano", "fatores"):
        assert a[chave] == b[chave], chave
