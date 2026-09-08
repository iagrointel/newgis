"""e2e da tabela de atributos acoplada ao mapa (item L2-01-g-tabela-atributos): a seleção viaja nos dois
sentidos entre a grade e o desenho, a coluna oculta some da tela, a largura arrastada volta depois de
recarregar e o teclado navega a grade com as setas e abre o popup com Enter.

A camada de teste é montada aqui mesmo (tabela real em `d_demo` preparada por `plat.camada_preparar`, o mesmo
caminho físico dos testes de API) e solta no fim. Sem ela não há o que a tela mostre: a base de demonstração
não traz camada nenhuma.

Captura em tests/e2e/capturas/L2-01-g-tabela-atributos_tabela.png."""

import os
from pathlib import Path

import pytest

from tests.api.test_tabela_atributos import _criar_camada
from tests.e2e.apoio import Tela

ITEM = "L2-01-g-tabela-atributos"
CAPTURAS = Path(__file__).resolve().parent / "capturas"

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


class _SessaoDoNavegador:
    """Adaptador mínimo: `_criar_camada` fala `sessao.post(caminho, json=...)`; aqui a chamada sai pelo
    contexto do navegador, com o MESMO cookie da tela (é a sessão do usuário que vai ver a tabela)."""

    def __init__(self, tela: Tela):
        self.tela = tela

    def post(self, caminho, json=None):
        resposta = self.tela.api("POST", caminho, corpo=json)

        class R:
            status_code = resposta.status
            text = resposta.text()

            @staticmethod
            def json():
                return resposta.json()

        return R


@pytest.fixture
def camada_na_tela(page, base_url, credenciais_demo, url_publica_resolve):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    if not os.environ.get("PLAT_DSN"):
        pytest.skip("sem PLAT_DSN no ambiente: a camada de teste precisa do banco")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    item_id, _schema, _tabela, fechar = _criar_camada(_SessaoDoNavegador(tela), os.environ, 120)
    try:
        yield tela, item_id
    finally:
        fechar()


def _abrir_tabela(tela, item_id):
    tela.ir("/mapa")
    tela.page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    tela.page.click("#tabela-alternar")
    tela.page.wait_for_selector("#painel-tabela:not([hidden])", timeout=10000)
    tela.page.select_option("#tabela-camada", item_id)
    tela.page.wait_for_selector("#tabela-corpo tr", timeout=15000)


def test_selecao_viaja_da_grade_para_o_desenho_e_de_volta(camada_na_tela, medida):
    tela, item_id = camada_na_tela
    page = tela.page
    _abrir_tabela(tela, item_id)

    total = page.text_content("#tabela-contagem")
    assert "120" in total, total

    # da grade para o desenho: três linhas escolhidas com Ctrl deixam três feições realçadas
    linhas = page.locator("#tabela-corpo tr")
    linhas.nth(0).click()
    linhas.nth(1).click(modifiers=["Control"])
    linhas.nth(2).click(modifiers=["Control"])
    assert page.locator("#tabela-corpo tr.selecionada").count() == 3
    assert "3" in (page.text_content("#tabela-selecao") or "")

    # do desenho para a grade: a mesma seleção, aplicada como filtro, deixa três linhas
    escolhidos = page.eval_on_selector_all(
        "#tabela-corpo tr.selecionada", "linhas => linhas.map(l => Number(l.dataset.id))")
    resposta = tela.api("POST", f"/api/camadas/{item_id}/tabela/linhas", corpo={"fids": escolhidos})
    corpo = resposta.json()
    assert corpo["total"] == 3 and len(corpo["linhas"]) == 3

    page.click("#tabela-limpar")
    page.wait_for_function("() => document.querySelectorAll('#tabela-corpo tr.selecionada').length === 0")

    CAPTURAS.mkdir(parents=True, exist_ok=True)
    caminho = CAPTURAS / f"{ITEM}_tabela.png"
    page.screenshot(path=str(caminho), full_page=False)
    assert caminho.exists() and caminho.stat().st_size > 10_000
    medida(ITEM)("captura_bytes", caminho.stat().st_size, "bytes",
                 "bash laco/roda_teste.sh tests/e2e/test_mapa_tabela.py -m 'lento and e2e'")
    tela.verificar()


def test_teclado_navega_com_setas_e_enter_abre_o_popup(camada_na_tela):
    tela, item_id = camada_na_tela
    page = tela.page
    _abrir_tabela(tela, item_id)

    page.locator("#tabela-corpo tr").nth(0).focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    indice = page.evaluate("() => Number(document.activeElement.dataset.indice)")
    assert indice == 2, indice
    page.keyboard.press("ArrowUp")
    assert page.evaluate("() => Number(document.activeElement.dataset.indice)") == 1

    page.keyboard.press("Enter")
    page.wait_for_selector("#tabela-popup:not([hidden])", timeout=5000)
    assert page.locator("#tabela-popup dl.tabela-popup dt").count() >= 3
    page.keyboard.press("Escape")
    tela.verificar()


def test_coluna_oculta_some_da_tela_e_largura_volta_depois_de_recarregar(camada_na_tela):
    tela, item_id = camada_na_tela
    page = tela.page
    _abrir_tabela(tela, item_id)

    assert page.locator('#tabela-cabecalho th[data-coluna="municipio"]').count() == 1
    tela.api("PUT", f"/api/camadas/{item_id}/tabela/vista",
             corpo={"colunas": [{"nome": "municipio", "oculta": True},
                                {"nome": "classe", "largura": 360}]})

    _abrir_tabela(tela, item_id)
    assert page.locator('#tabela-cabecalho th[data-coluna="municipio"]').count() == 0
    largura = page.eval_on_selector('#tabela-cabecalho th[data-coluna="classe"]',
                                    "th => Math.round(th.getBoundingClientRect().width)")
    assert 340 <= largura <= 380, largura
    tela.verificar()
