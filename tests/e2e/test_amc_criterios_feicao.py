"""e2e da tela de critérios sobre a própria feição (item L3-06-criterios-de-feicao): /amc/criterios-feicao
avalia o pedido, ranqueia, desenha o histograma de cada critério e a matriz de correlação, e exporta CSV.

Como os demais e2e desta árvore (ver tests/e2e/test_amc_explicacao.py), salta quando PLAT_URL_PUBLICA da
trilha não resolve — a URL de trilha é deliberadamente inválida (laco/trilha_ambiente.sh) e o teste corre de
verdade em homologação/CI. Captura em tests/e2e/capturas/L3-06-criterios-de-feicao_painel.png.
"""

import json
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela

ITEM = "L3-06-criterios-de-feicao"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
DADOS = Path(__file__).resolve().parents[1] / "dados"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _pedido() -> dict:
    """O mesmo dado aberto dos testes de unidade e de API, cortado em 200 feições para a tela não pesar."""
    feicoes = json.loads((DADOS / "l3_06_feicoes.geojson").read_text(encoding="utf-8"))["features"][:200]
    pontos = json.loads((DADOS / "l3_06_camada_pontos.geojson").read_text(encoding="utf-8"))["features"]
    return {
        "feicoes": feicoes,
        "camadas": {"lugares": pontos},
        "criterios": [
            {"id": "area", "tipo": "atributo", "campo": "area_m2", "influencia": "positiva", "peso": 3,
             "minimo": 0, "maximo": 1000, "faixa_inclusao": {"minimo": 20.0}},
            {"id": "lugares_1km", "tipo": "contagem_raio", "camada": "lugares", "raio_m": 1000,
             "influencia": "positiva", "peso": 2},
            {"id": "dist_lugar", "tipo": "distancia_mais_proxima", "camada": "lugares", "influencia": "inversa",
             "peso": 2},
            {"id": "area_ideal", "tipo": "atributo", "campo": "area_m2", "influencia": "ideal", "alvo": 200,
             "alcance": 200, "peso": 1},
        ],
    }


def test_tela_ranqueia_desenha_histograma_e_matriz_e_exporta(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/amc/criterios-feicao", "pagina_pronta_ms_criterios_feicao")

    page.fill("#pedido", json.dumps(_pedido()))
    page.click("#rodar")
    page.wait_for_selector("#ranque-corpo tr", timeout=30000)

    # 1. ranqueia: 200 linhas, a primeira com posição 1
    assert page.locator("#ranque-corpo tr").count() == 200
    assert page.locator("#ranque-corpo tr").first.locator("td").first.inner_text().strip() == "1"

    # 2. histograma de cada um dos quatro critérios, com barra desenhada
    assert page.locator(".histograma").count() == 4
    assert page.locator(".histograma svg rect").count() > 0

    # 3. matriz de correlação 4 x 4, com a diagonal em 1
    linhas = page.locator("#correlacao-corpo tr")
    assert linhas.count() == 4
    assert linhas.first.locator("td").count() == 4
    assert linhas.first.locator('td[data-par="0-0"]').inner_text().strip().startswith("1.00")

    # 4. filtro de inclusão aparece na tela como 'filtrada', não como nota zero
    filtradas = page.locator('#ranque-corpo tr[data-estado="filtrada"]')
    if filtradas.count():
        assert filtradas.first.locator("td").nth(2).inner_text().strip() == "—"

    # 5. export CSV: o clique dispara download de verdade
    with page.expect_download(timeout=30000) as espera:
        page.click("#baixar-csv")
    baixado = espera.value
    assert baixado.suggested_filename.endswith(".csv")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_painel.png"), full_page=True)

    erros = [c for c in tela.console if "console.error" in c or "pageerror" in c]
    assert erros == [], erros

    gravar = medida(ITEM)
    gravar("pagina_pronta_ms_criterios_feicao", tela.medidas.get("pagina_pronta_ms_criterios_feicao"), "ms",
           "tests/e2e/test_amc_criterios_feicao.py::test_tela_ranqueia_desenha_histograma_e_matriz_e_exporta")
