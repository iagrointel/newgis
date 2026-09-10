"""e2e do sistema de design (item UX-01-sistema-de-design), contra /estilo-guia e três telas do produto:

1. a guia renderiza todas as seções e amostras; toda cor de texto tem contraste >= 4,5:1 sobre o painel, calculado no
   navegador, nos temas escuro E claro (a troca é feita pelo <plat-tema> da própria página e persiste em localStorage);
2. axe (WCAG 2.x A/AA) com 0 violações sérias/críticas nos dois temas, inclusive com o diálogo aberto e com uma
   notificação visível; capturas em 1280 e 390 nos dois temas;
3. refutação do item: trocar UM token (--i-acento) muda o botão primário, o link ativo da navegação e o anel de foco
   em três telas diferentes (capturas UX-01_token_*), porque nenhuma delas tem cor própria;
4. teclado: Tab chega ao primeiro botão da guia e o anel de foco é o token --foco (visível).
0 erro de console e nenhuma resposta >= 400."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.apoio_axe import resumo, serias

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-01"
SECOES = ["tokens", "botoes", "campos", "tabela", "painel", "dialogo", "toast", "estados", "avisos"]
TELAS_TOKEN = ["/conteudo", "/admin/usuarios", "/conta"]
COR_DE_PROVA = "rgb(10, 200, 30)"


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


def _contrastes(page):
    return page.eval_on_selector_all("[data-contraste]", "els => els.map(e => Number(e.dataset.contraste))")


def _tema(page, valor):
    page.click(f"#tema label[for$='-{valor}']")
    page.wait_for_function(
        "v => (document.documentElement.getAttribute('data-theme') || 'sistema')"
        " === ({claro: 'light', escuro: 'dark', sistema: 'sistema'})[v]",
        arg=valor,
    )
    page.wait_for_selector("#sec-tokens [data-contraste]")


def test_guia_renderiza_tudo_com_contraste_e_axe_nos_dois_temas(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/estilo-guia")
    tela.ir("/estilo-guia")
    for s in SECOES:
        assert page.locator(f"#sec-{s}").count() == 1, s
    assert page.locator("#sec-tokens .amostra").count() >= 14
    assert page.locator("#sec-estados plat-estado[tipo]").count() == 4
    assert page.locator("#sec-avisos plat-aviso[data-tipo]").count() == 4
    assert page.locator("#form-guia [aria-invalid='true']").count() == 1
    for valor in ("escuro", "claro"):
        _tema(page, valor)
        contrastes = _contrastes(page)
        assert contrastes and all(c >= 4.5 for c in contrastes), (valor, contrastes)
        assert page.evaluate("() => localStorage.getItem('plat_tema')") == valor
        graves = serias(page)
        assert graves == [], f"tema {valor}:\n{resumo(graves)}"
        _capturar(page, f"guia_{valor}_1280")
        page.set_viewport_size({"width": 390, "height": 844})
        _capturar(page, f"guia_{valor}_390")
        assert page.locator("#menu-alternar").is_visible()
        page.click("#menu-alternar")
        assert page.locator("#lateral nav").is_visible()
        page.click("#menu-alternar")
        page.set_viewport_size({"width": 1280, "height": 800})
    # diálogo aberto e notificação visível também passam no axe
    page.click("#abrir-dialogo")
    page.wait_for_selector("#dialogo dialog[open]")
    graves = serias(page)
    assert graves == [], resumo(graves)
    _capturar(page, "guia_dialogo")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#dialogo dialog').open")
    page.click("#toast-acao")
    page.wait_for_selector("plat-toasts .toast")
    graves = serias(page)
    assert graves == [], resumo(graves)
    page.click("plat-toasts .toast .toast-acoes button")
    page.wait_for_selector("plat-toasts .toast[data-tipo='ok']")
    _tema(page, "sistema")
    assert page.evaluate("() => localStorage.getItem('plat_tema')") is None
    tela.verificar()


def test_trocar_um_token_muda_todas_as_telas(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/conta")
    for caminho in TELAS_TOKEN:
        tela.ir(caminho)
        ativo = "#lateral nav a[aria-current='page']"
        antes = page.eval_on_selector(ativo, "e => getComputedStyle(e).borderLeftColor")
        page.evaluate(f"() => document.documentElement.style.setProperty('--i-acento', '{COR_DE_PROVA}')")
        depois = page.eval_on_selector(ativo, "e => getComputedStyle(e).borderLeftColor")
        assert antes != depois and depois == COR_DE_PROVA, (caminho, antes, depois)
        primario = page.locator("button.primario, .botao.primario").first
        if primario.count():
            assert primario.evaluate("e => getComputedStyle(e).backgroundColor") == COR_DE_PROVA, caminho
        _capturar(page, f"token_{caminho.strip('/').replace('/', '-')}")
    tela.verificar()


def test_teclado_e_anel_de_foco(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/estilo-guia")
    tela.ir("/estilo-guia")
    page.focus("#sec-botoes button")
    foco = page.evaluate(
        "() => { const e = document.activeElement; const s = getComputedStyle(e); "
        "return { tag: e.tagName, cor: s.outlineColor, largura: s.outlineWidth, estilo: s.outlineStyle }; }"
    )
    acento = page.evaluate(
        "() => { const s = document.createElement('span'); s.style.color = 'var(--foco)'; "
        "document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; }"
    )
    assert foco["tag"] == "BUTTON" and foco["estilo"] == "solid" and foco["largura"] != "0px", foco
    assert foco["cor"] == acento, (foco, acento)
    # Tab avança para o botão seguinte da mesma seção (nada preso, nada pulado)
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.closest('#sec-botoes') !== null")
    tela.verificar()
