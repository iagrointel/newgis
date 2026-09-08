"""e2e playwright da tela /construtor-camada (item `L5-31-construtor-de-camada-esquema`) contra a URL interna
real (nginx da trilha na frente do uvicorn, porque a app não serve /static/ sozinha — mesma razão do
plat-homolog). Prova o MECANISMO de arrasto (dragstart/drop nativo do HTML5, sem biblioteca) montando um campo
por arrasto e outro por clique (a alternativa de teclado), depois cria a camada de verdade e confere que a
tela mostra os campos de volta no formato FeatureServer, com o alias já certo. 0 erro de console; capturas em
tests/e2e/capturas/L5-31-construtor-de-camada-esquema_*.png."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

CAPTURAS = Path(__file__).resolve().parent / "capturas"
ITEM = "L5-31-construtor-de-camada-esquema"


def _capturar(page, nome: str) -> None:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


@pytest.fixture(scope="session")
def api_camada_esquema(api_auth):
    faltam = [r for r in ("/api/camadas/esquema", "/api/camadas/{item_id}/campos") if r not in api_auth]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (item {ITEM})")
    return api_auth


def _arrastar(page, origem_sel: str, destino_sel: str) -> None:
    """drag-and-drop nativo do HTML5: o Playwright `drag_to` dispara os eventos reais (dragstart/dragover/
    drop) que `web/js/catalogo/camada_esquema.js` escuta — não é um atalho de teclado disfarçado."""
    page.locator(origem_sel).drag_to(page.locator(destino_sel))


def test_construtor_camada_arrasto_e_clique_criam_a_mesma_estrutura(page, base_url, credenciais_demo,
                                                                     api_camada_esquema):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/construtor-camada")
    _capturar(page, "vazio")

    titulo = f"zt e2e camada {sufixo()}"
    page.fill("#camada-titulo", titulo)
    page.select_option("#camada-geometria", "Point")

    # campo 1: arrasto real da paleta até a zona de campos
    _arrastar(page, "#paleta .chip-tipo[data-tipo='text']", "#zona-campos")
    page.wait_for_selector("#zona-campos .campo-linha")
    linhas = page.locator("#zona-campos .campo-linha")
    assert linhas.count() == 1
    linhas.nth(0).locator("input[data-campo='nome']").fill("nome_talhao")
    linhas.nth(0).locator("label:has-text('alias') input").fill("Nome do talhão")
    _capturar(page, "campo_por_arrasto")

    # campo 2: clique na paleta (alternativa de teclado/mouse simples, sem arrastar)
    page.click("#paleta .chip-tipo[data-tipo='integer']")
    page.wait_for_function("() => document.querySelectorAll('#zona-campos .campo-linha').length === 2")
    linhas = page.locator("#zona-campos .campo-linha")
    linhas.nth(1).locator("input[data-campo='nome']").fill("ano_plantio")
    _capturar(page, "campo_por_clique")

    tela.esperar_status(201)
    page.click("#criar-camada")
    page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
    page.wait_for_selector("#resultado-cartao:not([hidden])", timeout=15000)
    linhas_resultado = page.locator("#resultado-corpo tr")
    assert linhas_resultado.count() == 2
    texto_resultado = page.text_content("#resultado-corpo")
    assert "nome_talhao" in texto_resultado
    assert "Nome do talhão" in texto_resultado  # o alias já veio certo, sem reconfigurar nada
    assert "ano_plantio" in texto_resultado
    _capturar(page, "camada_criada")

    tela.verificar()
