"""e2e do item L2-03-f-edicao-em-lote-calculo-campo: o painel "Edição em lote" da tela /mapa (sobre a edição do
L2-03-edicao) chama `POST /api/camadas/{id}/lote` — calcular campo por expressão com pré-visualização (antes/depois)
e aplicação real, atribuir valor com erro de domínio NOMEADO no painel (nunca 422 cru), erro de expressão nomeado,
prévia de apagar; capturas 390/1280; 0 erro de console. Depende da bancada `scripts/edicao_demo_camadas.py criar`
(camada edicao-pontos com os campos `ordem`/`calc`); NÃO depende do Martin (a seleção é por expressão, não por
clique no tile)."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.test_mapa_edicao import _selecionar_camada

ITEM = "L2-03-f-edicao-em-lote-calculo-campo"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _capturar(page, nome, larguras=(390, 1280)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


@pytest.fixture(scope="module")
def browser_context_args(browser_context_args, base_url):
    """A escrita pelo navegador exige Origin == PLAT_URL_PUBLICA (https): na trilha o servidor local roda com
    certificado autoassinado em 127.0.0.1 — só aí o navegador do e2e ignora o erro de certificado."""
    return {**browser_context_args, "ignore_https_errors": base_url.startswith("https://127.0.0.1")}


@pytest.fixture
def mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.esperar_status(404, 502, 503)  # tilejson/tiles sem Martin na trilha: a lista de camadas não depende deles
    tela.esperar_status(422)  # os erros nomeados provocados pelo teste (expressão inválida, fora do domínio)
    tela.ir("/mapa", "pagina_pronta_ms_mapa_lote")
    page.wait_for_selector("#edicao-camada", timeout=20000)
    opcoes = page.locator("#edicao-camada option").all_inner_texts()
    if not any("edicao-pontos" in o for o in opcoes):
        pytest.skip("bancada do item ausente: rode scripts/edicao_demo_camadas.py criar")
    return tela


def _previa(page):
    page.click("#lote-previa")
    page.wait_for_function("() => document.querySelector('#lote-resultado table tbody tr') "
                           "|| !document.getElementById('lote-erro').hidden", timeout=10000)
    return page.locator("#lote-resultado table tbody tr")


def _erro(page):
    page.wait_for_selector("#lote-erro:not([hidden])", timeout=10000)
    return page.text_content("#lote-erro") or ""


def test_calcular_campo_previa_aplicar_e_erros_nomeados(mapa, page, medida):
    _selecionar_camada(page, "edicao-pontos")
    page.wait_for_function("() => document.querySelectorAll('#lote-campo option').length >= 5")
    campos = page.locator("#lote-campo option").all_inner_texts()
    assert any(c.startswith("calc ") for c in campos), campos
    ajuda = page.text_content("#lote-ajuda") or ""
    assert "$ordem" in ajuda and "$area_m2" in ajuda, ajuda

    # 0. estado de partida (a bancada persiste entre rodadas): atribuir vazio = nulo em `calc`, todas as feições
    page.select_option("#lote-operacao", "atribuir")
    page.select_option("#lote-campo", "calc")
    page.fill("#lote-valor", "")
    page.check("input[name='lote-selecao'][value='todas']")
    page.click("#lote-aplicar")
    page.wait_for_selector("#lote-ok", timeout=15000)
    assert "3 alterada(s)" in (page.text_content("#lote-ok") or "")

    # 1. calcular: prévia (3 de 3, antes vazio, depois = expressão) sem gravar
    page.select_option("#lote-operacao", "calcular")
    page.select_option("#lote-campo", "calc")
    page.fill("#lote-expressao", "Arredondar($ordem * 2.5 + $x, 3)")
    page.check("input[name='lote-selecao'][value='todas']")
    linhas = _previa(page)
    assert linhas.count() == 3, (page.text_content("#lote-resultado"), page.text_content("#lote-erro"), mapa.console)
    assert "3 de 3" in (page.text_content("#lote-resultado") or "")
    assert "traduzida para SQL" in (page.text_content("#lote-resultado") or "")
    celulas = linhas.first.locator("td").all_inner_texts()
    assert celulas[1] == "—", celulas  # antes: calc ainda vazio
    assert abs(float(celulas[2]) - (1 * 2.5 - 46.533)) < 1e-6, celulas
    _capturar(page, "previa")

    # 2. aplicar de verdade: resumo no painel; a prévia seguinte mostra antes == depois
    page.click("#lote-aplicar")
    page.wait_for_selector("#lote-ok", timeout=15000)
    assert "3 alterada(s)" in (page.text_content("#lote-ok") or "")
    linhas = _previa(page)
    for i in range(3):
        c = linhas.nth(i).locator("td").all_inner_texts()
        assert c[1] == c[2] and c[1] != "—", c
    _capturar(page, "aplicado", (1280,))

    # 3. erro de expressão nomeado (campo fora da lista branca) — nunca o status cru
    page.fill("#lote-expressao", "$nao_existe + 1")
    _previa(page)
    texto = _erro(page)
    assert "campo_nao_permitido" in texto and "422" not in texto, texto
    _capturar(page, "erro_expressao", (1280,))

    # 4. atribuir fora do domínio: 422 fora_do_dominio nomeado; dentro do domínio com `onde`: 1 alterada
    page.select_option("#lote-operacao", "atribuir")
    page.select_option("#lote-campo", "categoria")
    page.fill("#lote-valor", "Z")
    page.click("#lote-aplicar")
    texto = _erro(page)
    assert "fora_do_dominio" in texto and "422" not in texto, texto
    page.fill("#lote-valor", "B")
    page.check("input[name='lote-selecao'][value='onde']")
    page.fill("#lote-onde", "$ordem == 2")
    page.click("#lote-aplicar")
    page.wait_for_function("() => (document.getElementById('lote-ok') || {}).textContent?.includes('1 alterada')",
                           timeout=15000)

    # 5. prévia de apagar por expressão (0 de 0: nenhuma feição da bancada é tocada)
    page.select_option("#lote-operacao", "apagar")
    page.fill("#lote-onde", "$ordem > 99")
    page.click("#lote-previa")
    page.wait_for_function("() => (document.getElementById('lote-resultado').textContent || '').includes('0 de 0')",
                           timeout=10000)

    mapa.verificar()
    gravar = medida(ITEM)
    gravar("e2e_estados_provados", 7, "estados",
           "atribuir nulo; prévia calcular; aplicar; erro de expressão nomeado; atribuir fora do domínio nomeado; "
           "atribuir com onde; prévia apagar (tests/e2e/test_edicao_lote.py)")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in mapa.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
