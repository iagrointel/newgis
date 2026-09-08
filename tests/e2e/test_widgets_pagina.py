"""e2e do item L5-01-d-widgets-pagina-menu no executor de páginas (/executar): um documento `app` gravado pela API
com os 12 widgets (texto markdown com {campo}, imagem, botão, cartão, incorporar, divisor, menu, controlador,
compartilhar, login, idioma, tema) em duas páginas; cada widget desenhado de verdade; 10 vetores XSS em texto, cartão,
botão, imagem e embed nunca executam script (e o console termina sem erro); iframe com sandbox e lista de domínios;
QR local; menu/botão/cartão trocam de página; controlador abre/fecha; tema muda data-theme; captura."""

import secrets
from pathlib import Path

import pytest

from tests.e2e.apoio import Tela, sufixo

ITEM = "L5-01-d-widgets-pagina-menu"
CAPTURAS = Path(__file__).resolve().parent / "capturas"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
pytestmark = [pytest.mark.lento, pytest.mark.e2e]

VETORES_XSS = [
    '<script>window.__xss=1</script>',
    '<img src=x onerror="window.__xss=2">',
    '<svg onload="window.__xss=3">',
    '<a href="javascript:window.__xss=4">clique</a>',
    '<iframe src="javascript:window.__xss=5"></iframe>',
    '<div onmouseover="window.__xss=6">x</div>',
    '<math><mi xlink:href="javascript:window.__xss=7">y</mi></math>',
    '<object data="data:text/html;base64,PHNjcmlwdD53aW5kb3cuX194c3M9ODwvc2NyaXB0Pg=="></object>',
    '<style>@import "javascript:window.__xss=9"</style>',
    '[link](javascript:window.__xss=10) ![i](javascript:window.__xss=11)',
]


def _ulid() -> str:
    return secrets.choice("01234567") + "".join(secrets.choice(_CROCKFORD) for _ in range(25))


def _no(tipo, pai, propriedades, largura=12):
    return {"id": _ulid(), "tipo": tipo, "pai": pai, "propriedades": propriedades, "largura_colunas": largura}


def _documento():
    inicio = _no("pagina", None, {"titulo": "Início", "caminho": "inicio", "tipo_pagina": "rolavel", "ordem": 0,
                                  "inicial": True})
    sobre = _no("pagina", None, {"titulo": "Sobre", "caminho": "sobre", "tipo_pagina": "rolavel", "ordem": 1})
    xss = "\n\n".join(VETORES_XSS)
    texto = _no("texto", inicio["id"], {"texto": f"# Olá **{{nome}}**\n\nparágrafo com {{falta}}\n\n{xss}",
                                        "formato": "markdown"})
    imagem = _no("imagem", inicio["id"], {"url": "/static/favicon.svg", "alternativo": "ícone",
                                          "legenda": "legenda da imagem"}, 3)
    imagem_ma = _no("imagem", inicio["id"], {"url": "javascript:window.__xss=20", "alternativo": "ruim"}, 3)
    botao = _no("botao", inicio["id"], {"rotulo": "Ir para Sobre", "acao": {"tipo": "pagina", "pagina": "sobre"}}, 3)
    botao_ma = _no("botao", inicio["id"], {"rotulo": "Link mau",
                                           "acao": {"tipo": "link", "url": "javascript:window.__xss=21"}}, 3)
    botao_link = _no("botao", inicio["id"], {"rotulo": "Link bom",
                                             "acao": {"tipo": "link", "url": "https://exemplo.invalido/x",
                                                      "nova_aba": True}}, 3)
    cartao = _no("cartao", inicio["id"], {"titulo": "Cartão {nome}", "texto": "corpo **forte** " + VETORES_XSS[1],
                                          "imagem": "/static/favicon.svg", "pagina": "sobre",
                                          "link_rotulo": "abrir sobre"}, 4)
    divisor = _no("divisor", inicio["id"], {"estilo": "tracejado"})
    embed_ok = _no("incorporar", inicio["id"], {"url": "https://exemplo.invalido/mapa", "titulo": "embed permitido",
                                                "dominios_permitidos": ["exemplo.invalido"],
                                                "sandbox": ["allow-scripts", "allow-same-origin"]}, 6)
    embed_fora = _no("incorporar", inicio["id"], {"url": "https://outro.invalido/x", "titulo": "embed fora",
                                                  "dominios_permitidos": ["exemplo.invalido"]}, 6)
    embed_html = _no("incorporar", inicio["id"], {"html": "<p>seguro</p>" + VETORES_XSS[0] + VETORES_XSS[1],
                                                  "titulo": "embed html", "altura": 80}, 6)
    menu = _no("menu_widget", inicio["id"], {"orientacao": "horizontal", "itens": [
        {"rotulo": "Início", "pagina": "inicio"}, {"rotulo": "Sobre", "pagina": "sobre"},
        {"rotulo": "Externo", "url": "https://exemplo.invalido/"},
        {"rotulo": "Mau", "url": "javascript:window.__xss=22"}]})
    controlador = _no("controlador", inicio["id"], {"alvos": [{"id": cartao["id"], "rotulo": "cartão"},
                                                              {"id": "inexistente", "rotulo": "nada"}]})
    compartilhar = _no("compartilhar", sobre["id"], {"qr": True, "incorporar": True}, 6)
    login = _no("login", sobre["id"], {}, 3)
    idioma = _no("idioma", sobre["id"], {"idiomas": ["pt-BR"]}, 3)
    tema = _no("tema", sobre["id"], {}, 3)
    texto_puro = _no("texto", sobre["id"], {"texto": "puro " + VETORES_XSS[0], "nivel": "titulo"})
    nos = [inicio, sobre, texto, imagem, imagem_ma, botao, botao_ma, botao_link, cartao, divisor, embed_ok, embed_fora,
           embed_html, menu, controlador, compartilhar, login, idioma, tema, texto_puro]
    ids = {"cartao": cartao["id"], "embed_ok": embed_ok["id"], "embed_fora": embed_fora["id"],
           "embed_html": embed_html["id"], "texto": texto["id"], "imagem_ma": imagem_ma["id"],
           "botao_ma": botao_ma["id"], "botao_link": botao_link["id"]}
    return {"nos": nos, "ligacoes": []}, ids


def _criar_app(admin_api, corpo):
    r = admin_api.post("/api/itens", data={"tipo": "app", "titulo": f"zt-widgets-{sufixo()}",
                                            "dados": {"tipo": "app", "esquema_versao": 2, "corpo": corpo}})
    assert r.status == 201, (r.status, r.text())
    return r.json()["id"]


def _widget(page, no_id):
    return page.locator(f'[data-no-id="{no_id}"]')


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}.png"), full_page=True)


def test_doze_widgets_no_executor_sem_script_executado(page, base_url, credenciais_demo, admin_api):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    corpo, ids = _documento()
    iid = _criar_app(admin_api, corpo)
    try:
        page.add_init_script("window.__xss = undefined;")
        # o vetor <img src=x onerror> perde o onerror e vira um <img src="x"> inerte: o 404 desse `x` é o único erro
        # de rede aceito (prova de que o atributo foi cortado, não de que algo rodou)
        tela.esperar_status(404)
        tela.ir(f"/executar?item={iid}")
        page.wait_for_selector('.exec-pagina[data-pagina="inicio"]', timeout=15000)
        # ---- texto markdown: título, {campo} ausente visível, nenhum vetor executa
        t = _widget(page, ids["texto"])
        assert t.locator("h1").count() == 1 and "{falta}" in t.text_content()
        assert t.locator("script, iframe, object, style, svg, math").count() == 0
        assert t.locator("[onerror], [onload], [onmouseover]").count() == 0
        assert page.evaluate(
            "() => [...document.querySelectorAll('a[href]')]"
            ".every((a) => !a.href.toLowerCase().startsWith('javascript:'))")
        # ---- imagem boa e imagem com javascript: recusada com erro nomeado
        assert page.locator("plat-w-imagem img[src='/static/favicon.svg']").count() >= 1
        assert page.locator("plat-w-imagem figcaption").text_content() == "legenda da imagem"
        assert "recusado" in _widget(page, ids["imagem_ma"]).locator("[role=alert]").text_content()
        # ---- botão: link mau recusado, link bom com rel/target, botão de página troca de página
        assert "recusado" in _widget(page, ids["botao_ma"]).locator("[role=alert]").text_content()
        link = _widget(page, ids["botao_link"]).locator("a")
        assert link.get_attribute("rel") == "noopener noreferrer" and link.get_attribute("target") == "_blank"
        # ---- cartão com {campo} do texto sem feição: fica literal; sem onerror
        cartao = _widget(page, ids["cartao"])
        assert "Cartão {nome}" in cartao.locator("h3").text_content()
        assert cartao.locator("[onerror]").count() == 0 and cartao.locator("strong").count() == 1
        # ---- divisor
        assert page.locator("plat-w-divisor hr.plat-divisor-tracejado").count() == 1
        # ---- incorporar: sandbox sem allow-same-origin; fora da lista = erro; html sanitizado em srcdoc
        ok = _widget(page, ids["embed_ok"]).locator("iframe")
        assert ok.get_attribute("sandbox") == "allow-scripts" and ok.get_attribute("src") == "https://exemplo.invalido/mapa"
        assert "fora da lista" in _widget(page, ids["embed_fora"]).locator("[role=alert]").text_content()
        html = _widget(page, ids["embed_html"]).locator("iframe")
        srcdoc = html.get_attribute("srcdoc")
        assert html.get_attribute("sandbox") == "" and "<script" not in srcdoc and "onerror" not in srcdoc
        assert "<p>seguro</p>" in html.get_attribute("srcdoc")
        # ---- menu configurável: item mau sem href; item externo com href; item de página navega
        assert page.locator("plat-w-menu a[aria-disabled='true']").count() == 1
        assert page.locator("plat-w-menu a[href='https://exemplo.invalido/']").count() == 1
        # ---- controlador: fecha e abre o cartão; alvo inexistente marcado
        botao_ctrl = page.locator(f'plat-w-controlador button[data-alvo="{ids["cartao"]}"]')
        assert botao_ctrl.get_attribute("aria-expanded") == "true"
        botao_ctrl.click()
        assert cartao.evaluate("el => el.hidden") is True and botao_ctrl.get_attribute("aria-expanded") == "false"
        botao_ctrl.click()
        assert cartao.evaluate("el => el.hidden") is False
        assert page.locator('plat-w-controlador button[data-alvo="inexistente"]').get_attribute("title") is not None
        _capturar(page, "inicio")
        # ---- navegação por menu widget → página Sobre
        page.click('plat-w-menu button[data-pagina="sobre"]')
        page.wait_for_selector('.exec-pagina[data-pagina="sobre"]', timeout=5000)
        assert "pagina=sobre" in page.url
        # texto puro: HTML inerte, nível traduzido para h2
        puro = page.locator(".exec-pagina plat-w-texto h2")
        assert puro.count() == 1 and "<script>" in puro.text_content()
        # compartilhar: link, QR local, embed
        comp = page.locator("plat-w-compartilhar")
        assert comp.locator("input[aria-label='link']").input_value() == page.url
        qr = comp.locator("img.plat-w-qr")
        assert qr.get_attribute("src").startswith("/api/qr.svg?texto=")
        page.wait_for_function(
            "() => { const i = document.querySelector('img.plat-qr'); return i && i.complete && i.naturalWidth > 0; }",
            timeout=10000)
        assert "sandbox=" in comp.locator("textarea").input_value()
        # login: mostra quem está autenticado
        page.wait_for_selector("plat-w-login[data-autenticado='1'] .plat-login-nome", timeout=10000)
        assert page.locator("plat-w-login .plat-login-nome").text_content().strip() != ""
        # idioma: seletor com o idioma disponível
        assert page.locator("plat-w-idioma select option").count() == 1
        # tema: escuro põe data-theme no <html>; sistema tira
        page.click('plat-w-tema button[data-tema="dark"]')
        assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
        assert page.locator('plat-w-tema button[data-tema="dark"]').get_attribute("aria-pressed") == "true"
        _capturar(page, "sobre_escuro")
        page.click('plat-w-tema button[data-tema="sistema"]')
        assert page.evaluate("() => document.documentElement.dataset.theme") is None
        # ---- volta pelo botão de página e pelo cartão
        page.go_back()
        page.wait_for_selector('.exec-pagina[data-pagina="inicio"]', timeout=5000)
        page.click("plat-w-botao button:has-text('Ir para Sobre')")
        page.wait_for_selector('.exec-pagina[data-pagina="sobre"]', timeout=5000)
        page.go_back()
        page.wait_for_selector('.exec-pagina[data-pagina="inicio"]', timeout=5000)
        page.click("plat-w-cartao button:has-text('abrir sobre')")
        page.wait_for_selector('.exec-pagina[data-pagina="sobre"]', timeout=5000)
        # ---- veredito da refutação: nenhum vetor executou, console limpo
        page.wait_for_timeout(300)
        assert page.evaluate("() => window.__xss") is None
        tela.verificar()
    finally:
        admin_api.delete(f"/api/itens/{iid}")
