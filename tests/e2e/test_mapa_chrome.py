"""e2e do item UX-04-tela-mapa-polimento: o chrome único do visualizador.

1. um trilho à esquerda com um botão por painel; cada painel (pesquisar, camadas, legenda, medição, desenho, anotações,
   impressão, exportar) abre na MESMA gaveta como <plat-painel>, com captura em 1280 e 390; a tabela de atributos abre
   ancorada ao rodapé do mapa; só um painel visível por vez; fechar devolve o foco ao botão do trilho;
2. atalhos de teclado: letra abre/fecha o painel, t a tabela, Esc fecha, ? lista os atalhos num diálogo; com o foco num
   campo de texto a letra é texto, não atalho;
3. tela cheia (botão e tecla f) e impressão pelo navegador (@media print esconde o chrome e deixa o canvas);
4. em 390 px o trilho vai para o rodapé e a gaveta vira painel inferior de no máximo 390 px sobre o mapa;
5. o mapa-base é escuro (fundo do estilo = token escuro) e trocar de base mantém o chrome;
6. axe sem violação séria com cada painel aberto; nenhuma chave crua de i18n em nenhum painel; 0 erro de console."""

import json

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-04"
PAINEIS = ["busca", "camadas", "legenda", "medicao", "desenho", "anotacoes", "impressao", "exportar", "rotas", "motor",
           "selecao", "layout"]
ATALHOS = {
    "b": "busca",
    "c": "camadas",
    "l": "legenda",
    "m": "medicao",
    "d": "desenho",
    "a": "anotacoes",
    "i": "impressao",
    "e": "exportar",
    "r": "rotas",
    "o": "motor",
    "s": "selecao",
    "y": "layout",
}


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"))


def _aberto(page):
    return page.evaluate("() => window.plat.mapa.painelAberto()")


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _entrar_no_mapa(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/mapa")
    page.wait_for_selector("#mapa canvas.maplibregl-canvas", timeout=20000)
    return tela


def test_cada_painel_abre_no_mesmo_chrome_com_capturas_e_axe(page, base_url, credenciais_demo):
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    chaves, espacos = set(dic), {k.split(".")[0] for k in dic}
    r = tela.api("GET", "/api/privilegios")
    privilegios = {p["nome"] for p in r.json()} if r.status == 200 else set()
    assert page.locator("#trilho .trilho-botao").count() == len(PAINEIS) + 1
    for largura in (1280, 390):
        page.set_viewport_size({"width": largura, "height": 800 if largura > 400 else 844})
        for p in PAINEIS:
            page.click(f"#trilho [data-painel='{p}']")
            page.wait_for_selector(f"#painel-{p}:not([hidden])", timeout=5000)
            assert _aberto(page) == p
            # só um painel visível; todos são <plat-painel> com o mesmo cabeçalho (h2 + fechar)
            assert page.locator(".mapa-gaveta plat-painel:not([hidden])").count() == 1
            assert page.locator(f"#painel-{p} > .painel-cabecalho h2").count() == 1
            assert page.locator(f"#painel-{p} > .painel-cabecalho .fechar-x").count() == 1
            assert page.locator(f"#trilho [data-painel='{p}'][aria-pressed='true']").count() == 1
            if largura == 1280:
                _axe(page, f"painel {p}")
                cruas = _cruas(_texto(page), chaves, espacos, privilegios)
                assert cruas == [], (p, cruas)
            _capturar(page, f"painel_{p}_{largura}")
        # tabela ancorada ao rodapé do mapa
        page.click("#tabela-alternar")
        page.wait_for_selector("#painel-tabela:not([hidden])", timeout=5000)
        caixa = page.locator("#painel-tabela").bounding_box()
        mapa = page.locator(".mapa-area").bounding_box()
        # ancorada ao rodapé do mapa: dentro da área do mapa e encostada embaixo (folga da barra de rolagem)
        fundo_tabela, fundo_mapa = caixa["y"] + caixa["height"], mapa["y"] + mapa["height"]
        assert caixa["y"] >= mapa["y"] and 0 <= fundo_mapa - fundo_tabela < 20, (caixa, mapa)
        if largura == 1280:
            _axe(page, "tabela")
        _capturar(page, f"tabela_{largura}")
        page.click("#tabela-fechar")
        page.wait_for_selector("#painel-tabela", state="hidden", timeout=5000)
        if largura == 390:
            # trilho no rodapé e gaveta como painel inferior de no máximo 390 px
            trilho = page.locator("#trilho").bounding_box()
            assert trilho["y"] > mapa["y"] + mapa["height"] - 2, (trilho, mapa)
            gaveta = page.locator("#gaveta").bounding_box()
            assert gaveta and gaveta["height"] <= 390 and gaveta["y"] >= mapa["y"], (gaveta, mapa)
    page.set_viewport_size({"width": 1280, "height": 800})
    # fechar pelo x devolve o foco ao botão do trilho
    ultimo = PAINEIS[-1]
    page.click(f"#painel-{ultimo} > .painel-cabecalho .fechar-x")
    page.wait_for_selector("#gaveta", state="hidden", timeout=5000)
    assert _aberto(page) is None
    assert page.evaluate("() => document.activeElement.dataset.painel") == ultimo
    tela.verificar()


def test_atalhos_tela_cheia_impressao_e_base_escura(page, base_url, credenciais_demo):
    tela = _entrar_no_mapa(page, base_url, credenciais_demo)
    page.evaluate("() => window.plat.mapa.fecharGaveta()")
    page.focus("#mapa")
    for tecla, painel in ATALHOS.items():
        page.keyboard.press(tecla)
        page.wait_for_selector(f"#painel-{painel}:not([hidden])", timeout=5000)
        assert _aberto(page) == painel
    page.keyboard.press("Escape")
    page.wait_for_selector("#gaveta", state="hidden", timeout=5000)
    # com o foco num campo, a letra é texto
    page.keyboard.press("b")
    page.wait_for_selector("#painel-busca:not([hidden])", timeout=5000)
    page.fill("#busca-campo", "")
    page.focus("#busca-campo")
    page.keyboard.type("lm")
    assert page.input_value("#busca-campo") == "lm" and _aberto(page) == "busca"
    page.keyboard.press("Escape")
    page.focus("#mapa")
    page.keyboard.press("t")
    page.wait_for_selector("#painel-tabela:not([hidden])", timeout=5000)
    page.keyboard.press("t")
    page.wait_for_selector("#painel-tabela", state="hidden", timeout=5000)
    page.keyboard.press("?")
    page.wait_for_selector("#dialogo-atalhos dialog[open]", timeout=5000)
    assert page.locator("#dialogo-atalhos dialog[open] kbd").count() >= len(ATALHOS) + 3
    _axe(page, "diálogo de atalhos")
    _capturar(page, "atalhos")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#dialogo-atalhos dialog').open")
    # tela cheia: botão presente e ligado à tecla f; o headless pode não conceder o modo, então o que se prova é o
    # pedido e o retorno sem erro (o estado é lido do documento, nunca fingido)
    assert page.locator("#btn-tela-cheia").count() == 1
    page.focus("#mapa")
    page.keyboard.press("f")
    page.wait_for_timeout(300)
    estado = page.evaluate(
        "() => ({ el: !!document.fullscreenElement, "
        "aria: document.getElementById('btn-tela-cheia').getAttribute('aria-pressed') })"
    )
    assert estado["aria"] == ("true" if estado["el"] else "false")
    if estado["el"]:
        page.keyboard.press("f")
        page.wait_for_function("() => !document.fullscreenElement")
    # impressão pelo navegador: no @media print só o mapa fica
    page.emulate_media(media="print")
    escondidos = page.evaluate(
        "() => ['.mapa-barra', '#trilho', '#gaveta'].map(s => getComputedStyle(document.querySelector(s)).display)"
    )
    assert escondidos == ["none", "none", "none"], escondidos
    assert page.evaluate("() => getComputedStyle(document.querySelector('.mapa-area')).position") == "fixed"
    page.emulate_media(media="screen")
    # mapa-base escuro: o fundo do estilo é o token escuro do instrumento, e trocar de base mantém o chrome
    fundo = page.evaluate(
        "() => window.plat.mapa.map.getStyle().layers.find(l => l.type === 'background')"
        ".paint['background-color']"
    )
    escuro = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--i-fundo').trim()")
    assert fundo.lower() == "#0b0f10" and escuro, (fundo, escuro)
    page.evaluate("() => window.plat.mapa.abrirPainel('camadas')")
    page.select_option("#seletor-base", "sem-base")
    page.wait_for_function("() => window.plat.mapa.map.getStyle().name === 'plat-sem-base'", timeout=10000)
    assert page.locator("#trilho .trilho-botao").count() == len(PAINEIS) + 1
    _capturar(page, "sem_base")
    tela.verificar()


@pytest.mark.parametrize("largura", [1280, 390])
def test_zero_estilo_inline_e_tokens(page, base_url, credenciais_demo, largura):
    """nenhum elemento do chrome do mapa carrega style= com cor ou tamanho literal (o resto é a guarda de tokens)."""
    _entrar_no_mapa(page, base_url, credenciais_demo)
    page.set_viewport_size({"width": largura, "height": 800})
    inline = page.evaluate(
        "() => [...document.querySelectorAll('.mapa-barra [style], #trilho [style], #gaveta [style]')]"
        ".map(e => e.getAttribute('style')).filter(s => /#[0-9a-f]{3,8}|rgb|px|rem/i.test(s))"
    )
    assert inline == [], inline
