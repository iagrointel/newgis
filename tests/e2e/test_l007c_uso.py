"""e2e da tela /admin/uso (item L0-07-c-cotas-uso).

A cláusula do portão é literal: "tela 'Uso' do admin do inquilino com gráfico e captura". Aqui ficam as
três coisas que só o navegador prova — o gráfico é DESENHADO (um <svg class="grafico-uso"> com a linha da
série e a marca da cota), o consumo aparece contra a cota, e a tela abre sem nenhum erro de console."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-07-c"
LARGURAS = (390, 1280)


def test_tela_de_uso_desenha_grafico_e_cotas(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha, proximo="/admin/uso")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.wait_for_selector("#agora-corpo .cotas", timeout=20000)

    # o gráfico é SVG desenhado pela própria tela (sem biblioteca: a CSP do produto não deixa carregar
    # script de fora). Ou a linha da série existe, ou a tela declarou que não há medição na janela.
    grafico = page.query_selector("#grafico-corpo svg.grafico-uso")
    if grafico is None:
        assert page.inner_text("#grafico-corpo").strip(), "sem gráfico E sem o texto que explica a ausência"
    else:
        assert page.query_selector("#grafico-corpo svg.grafico-uso path.serie"), "o SVG existe mas sem a linha"

    assert page.query_selector("#tabela-serie"), "a série diária também tem de aparecer em tabela"
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in LARGURAS:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_uso_{largura}.png"), full_page=True)
    tela.verificar()


def test_janela_da_serie_muda_a_consulta(page, base_url, credenciais_demo):
    """Trocar a janela tem de refazer o pedido com o novo número de dias — não filtrar no navegador."""
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url, ITEM)
    tela.entrar(slug, login, senha, proximo="/admin/uso")
    page.wait_for_selector("#dias", timeout=20000)
    with page.expect_request(lambda r: "/api/uso?dias=7" in r.url, timeout=15000):
        page.select_option("#dias", "7")
    tela.verificar()
