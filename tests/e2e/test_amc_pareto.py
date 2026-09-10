"""e2e /amc/pareto (item L3-08-pareto): o gráfico de dispersão e o mapa são a MESMA seleção.

Cláusula b) do portão, "gráfico e mapa ligados". A prova é: escovar um retângulo no gráfico e conferir
que (1) os pontos marcados no gráfico são exatamente os do retângulo e (2) o filtro que o MapLibre
ficou aplicando na camada de realce tem exatamente esses identificadores — lido de volta do mapa, não
da variável da página.

Preparação pela API (execução do motor de grades com dois fatores em eixos opostos), a mesma de
tests/api/amc/test_pareto.py. Captura em tests/e2e/capturas/L3-08-pareto_grafico_mapa.png.
"""

import math
import secrets
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

ITEM = "L3-08-pareto"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CENTRO = (-46.60, -23.50)
LADO_M = 1900.0
MEIA_LON = (LADO_M / 2) / (111_320.0 * math.cos(math.radians(CENTRO[1])))
MEIA_LAT = (LADO_M / 2) / 111_320.0


def _retangulo() -> dict:
    lon, lat = CENTRO
    return {"type": "Polygon", "coordinates": [[
        [lon - MEIA_LON, lat - MEIA_LAT], [lon + MEIA_LON, lat - MEIA_LAT],
        [lon + MEIA_LON, lat + MEIA_LAT], [lon - MEIA_LON, lat + MEIA_LAT], [lon - MEIA_LON, lat - MEIA_LAT],
    ]]}


def _amostras(eixo: str, n: int = 12) -> list[dict]:
    lon, lat = CENTRO
    x0, x1 = lon - MEIA_LON * 0.92, lon + MEIA_LON * 0.92
    y0, y1 = lat - MEIA_LAT * 0.92, lat + MEIA_LAT * 0.92
    saida = []
    for i in range(n):
        for j in range(n):
            fx, fy = i / (n - 1), j / (n - 1)
            saida.append({"lon": x0 + (x1 - x0) * fx, "lat": y0 + (y1 - y0) * fy,
                          "valor": 100.0 * (fx if eixo == "leste" else fy)})
    return saida


@pytest.fixture
def execucao(admin_api):
    r = admin_api.post("/api/multiescala/conjuntos",
                       data={"nome": f"zt-e2e-pareto-{secrets.token_hex(4)}", "area": _retangulo()})
    assert r.status == 201, r.text()
    conjunto = r.json()
    fatores = []
    for eixo in ("leste", "norte"):
        rf = admin_api.post("/api/multiescala/fatores", data={
            "nome": f"zt-e2e-{eixo}-{secrets.token_hex(4)}", "resolucao_fonte_m": 100.0,
            "papel": "atrai", "unidade": "un", "fonte": "amostra sintética de teste"})
        assert rf.status == 201, rf.text()
        f = rf.json()
        assert admin_api.post(f"/api/multiescala/fatores/{f['id']}/amostras",
                              data={"amostras": _amostras(eixo)}).status == 201
        fatores.append(f)
    rm = admin_api.post(f"/api/multiescala/conjuntos/{conjunto['id']}/macro", data={
        "resolucao_m": 500.0, "aprovacao_tipo": "top_pct", "aprovacao_valor": 50.0,
        "fatores": [{"fator_id": f["id"], "peso": 1.0} for f in fatores]})
    assert rm.status == 201, rm.text()
    yield rm.json()["id"]
    admin_api.delete(f"/api/multiescala/conjuntos/{conjunto['id']}")
    for f in fatores:
        admin_api.delete(f"/api/multiescala/fatores/{f['id']}")


def test_escovar_o_grafico_realca_as_mesmas_unidades_no_mapa(page, base_url, credenciais_demo, execucao):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir(f"/amc/pareto?execucao={execucao}", "pagina_pronta_ms_pareto")

    page.wait_for_selector(".objetivo input[type=checkbox]")
    for marca in page.query_selector_all(".objetivo input[type=checkbox]")[:2]:
        marca.check()
    page.click("#rodar")
    page.wait_for_selector("#grafico .ponto")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    page.wait_for_timeout(1000)

    caixa = page.query_selector("#grafico").bounding_box()
    # metade direita e metade de cima do gráfico
    page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + 2)
    page.mouse.down()
    page.mouse.move(caixa["x"] + caixa["width"] - 2, caixa["y"] + caixa["height"] / 2, steps=8)
    page.mouse.up()

    escovados = page.eval_on_selector_all(
        "#grafico .ponto.escovado", "els => els.map(e => Number(e.dataset.unidade)).sort((a,b)=>a-b)")
    assert escovados, "a escova não marcou ponto nenhum no gráfico"
    selecionados = page.eval_on_selector("#selecao", "el => JSON.parse(el.dataset.ids).sort((a,b)=>a-b)")
    assert selecionados == escovados
    realcadas = page.eval_on_selector("#mapa", "el => Number(el.dataset.realcadas)")
    assert realcadas == len(escovados), "o filtro que ficou valendo no mapa não é a seleção do gráfico"

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_grafico_mapa.png"))
