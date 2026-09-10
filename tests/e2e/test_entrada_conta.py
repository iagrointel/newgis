"""e2e do item UX-02-telas-entrada-conta-convite: o fluxo inteiro entrar → 2FA → conta → sair, com capturas em 360 e
1280, axe (WCAG A/AA) sem violação séria em cada tela, 0 erro de console, e os textos em pt-BR/en/es pelo seletor de
idioma e pela preferência da conta. Refutação do item: "campo inválido nunca some sem mensagem" — o envio com campo
vazio marca o campo (aria-invalid + .erro-campo) e o foco vai para ele; senha errada marca o campo senha; código de
2FA errado marca o campo código. Também as telas públicas de convite e redefinição nos estados de token ausente,
inválido e formulário, e a troca da preferência de idioma em /conta refletida na barra lateral."""

import re

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, esperar_proximo_passo, passo_atual, sufixo, totp
from tests.e2e.apoio_axe import resumo, serias

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-02"
LARGURAS = (360, 1280)


def _capturar(page, nome):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in LARGURAS:
        page.set_viewport_size({"width": largura, "height": 800 if largura > 400 else 780})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _erro_do_campo(page, id_):
    return (page.locator(f"#{id_} ~ .erro-campo, .campo:has(#{id_}) .erro-campo").first.text_content() or "").strip()


def test_fluxo_entrar_2fa_conta_sair_com_estados_e_idiomas(page, base_url, credenciais_demo, admin_api):
    slug = credenciais_demo[0]
    login = f"e2e_ux02_{sufixo()}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "Entrada UX02", "perfil": "editor"})
    assert r.status == 201, r.text()
    uid, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
    senha = f"Senha{sufixo()}9k"
    tela = Tela(page, base_url)
    tela.esperar_status(401)
    try:
        # --- /entrar: vazio marca campos; senha errada marca a senha; idioma pelo seletor
        tela.ir(f"/entrar?inquilino={slug}")
        _axe(page, "/entrar")
        _capturar(page, "entrar")
        page.click("#entrar")
        assert page.evaluate("() => document.activeElement.id") == "login"
        assert page.locator("#login[aria-invalid='true']").count() == 1
        assert page.locator("#senha[aria-invalid='true']").count() == 1
        assert _erro_do_campo(page, "login") != "" and _erro_do_campo(page, "senha") != ""
        _capturar(page, "entrar_erro_campo")
        page.fill("#login", login)
        page.fill("#senha", "senha-errada-1")
        page.click("#entrar")
        page.wait_for_selector("#senha[aria-invalid='true']", timeout=15000)
        assert "inválid" in _erro_do_campo(page, "senha").lower()
        assert page.locator("#aviso:not([hidden])").count() == 1
        # idioma: en e es trocam os rótulos sem recarregar; a escolha fica em localStorage
        page.select_option("#idioma select", "en")
        page.wait_for_function("() => document.documentElement.lang === 'en'")
        assert page.text_content("#entrar").strip() == "Sign in"
        assert page.evaluate("() => localStorage.getItem('plat_idioma')") == "en"
        _capturar(page, "entrar_en")
        page.select_option("#idioma select", "es")
        page.wait_for_function("() => document.documentElement.lang === 'es'")
        assert page.text_content("#entrar").strip() == "Entrar"
        assert page.text_content("label[for='senha']").strip() == "contraseña"
        page.select_option("#idioma select", "pt-BR")
        page.wait_for_function("() => document.documentElement.lang === 'pt-BR'")
        # entra com a temporária: pendência de senha leva a /conta#senha
        page.fill("#senha", temporaria)
        page.click("#entrar")
        page.wait_for_url(lambda u: "/conta" in u, timeout=20000)
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        assert page.locator("#pendencia .aviso-pendencia").count() == 1
        _axe(page, "/conta com pendência")
        _capturar(page, "conta_pendencia")
        page.fill("#form-senha input[name='atual']", temporaria)
        page.fill("#form-senha input[name='nova']", senha)
        page.click("#form-senha button[type='submit']")
        page.wait_for_selector("#form-senha plat-aviso[data-tipo='ok']", timeout=15000)
        # --- 2FA: passos numerados, QR, código
        page.click("#ligar-2fa")
        page.wait_for_selector("#segredo-2fa", timeout=15000)
        assert page.locator("#area-2fa ol.passos li").count() == 3
        segredo = page.text_content("#segredo-2fa").strip()
        _axe(page, "/conta 2fa em ativação")
        _capturar(page, "conta_2fa_ativar")
        passo = passo_atual()
        page.fill("#area-2fa input[name='codigo']", totp(segredo))
        page.click("#area-2fa button[type='submit']")
        page.wait_for_selector("#codigos-recuperacao", timeout=15000)
        assert page.text_content("#estado-2fa").strip() == "ligado"
        _capturar(page, "conta_2fa_codigos")
        # --- preferência de idioma da conta reflete na barra e persiste
        page.select_option("#form-dados select[name='idioma_preferido']", "en")
        page.click("#form-dados button[type='submit']")
        page.wait_for_selector("#form-dados plat-aviso[data-tipo='ok']", timeout=15000)
        page.wait_for_function("() => document.documentElement.lang === 'en'")
        assert page.text_content("#lateral nav a[href='/conta']").strip() == "My account"
        tela.ir("/conta")
        assert page.evaluate("() => document.documentElement.lang") == "en"
        assert page.text_content("#t-sessoes").strip() == "Sessions"
        _axe(page, "/conta en")
        _capturar(page, "conta_en")
        page.select_option("#form-dados select[name='idioma_preferido']", "pt-BR")
        page.click("#form-dados button[type='submit']")
        page.wait_for_function("() => document.documentElement.lang === 'pt-BR'")
        # --- sair e entrar de novo com senha + código; código errado marca o campo
        tela.sair()
        _capturar(page, "entrar_apos_sair")
        page.fill("#login", login)
        page.fill("#senha", senha)
        page.click("#entrar")
        page.wait_for_selector("#form-2fa:not([hidden])", timeout=15000)
        assert page.locator("#form-senha").is_hidden()
        assert re.search(r"\d:\d\d", page.text_content("#contador") or "")
        _axe(page, "/entrar 2fa")
        _capturar(page, "entrar_2fa")
        page.fill("#codigo", "12")
        page.click("#confirmar")
        assert page.locator("#codigo[aria-invalid='true']").count() == 1
        assert "6" in _erro_do_campo(page, "codigo")
        page.fill("#codigo", "000000")
        page.click("#confirmar")
        page.wait_for_selector("#codigo[aria-invalid='true']", timeout=15000)
        esperar_proximo_passo(passo)
        page.fill("#codigo", totp(segredo))
        page.click("#confirmar")
        page.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        assert tela.api("GET", "/api/eu").json()["totp_ativo"] is True
        tela.sair()
        assert "/entrar" in page.url
        tela.verificar()
    finally:
        admin_api.delete(f"/api/usuarios/{uid}")


def test_convite_e_redefinicao_estados_publicos(page, base_url, credenciais_demo, admin_api):
    slug = credenciais_demo[0]
    tela = Tela(page, base_url)
    tela.esperar_status(410, 422, 429)
    # convite: sem token, token inválido, token válido com formulário e erro por campo
    tela.ir("/aceitar-convite")
    assert page.locator("#estado[tipo='erro']").count() == 1 and page.locator("#form-aceitar").is_hidden()
    _axe(page, "/aceitar-convite sem token")
    tela.ir("/aceitar-convite?token=naoexiste")
    assert page.locator("#estado[tipo='erro']").count() == 1
    _capturar(page, "convite_invalido")
    email = f"ux02_{sufixo()}@exemplo.test"
    r = admin_api.post("/api/convites", data={"email": email, "perfil": "visualizador"})
    assert r.status == 201, r.text()
    convite = r.json()
    token = (convite.get("link_manual") or "").split("token=")[-1] if convite.get("link_manual") else ""
    if token:
        tela.ir(f"/aceitar-convite?token={token}")
        page.wait_for_selector("#form-aceitar:not([hidden])", timeout=15000)
        assert email in (page.text_content("#convite-email") or "")
        _axe(page, "/aceitar-convite formulário")
        _capturar(page, "convite_formulario")
        page.fill("#login", "Nome Invalido!")
        page.fill("#nome", "")
        page.fill("#senha", "123")
        page.click("#aceitar")
        assert page.locator("#login[aria-invalid='true']").count() == 1
        assert page.locator("#nome[aria-invalid='true']").count() == 1
        assert page.locator("#senha[aria-invalid='true']").count() == 1
        assert page.evaluate("() => document.activeElement.id") == "login"
        _capturar(page, "convite_erro_campo")
        admin_api.delete(f"/api/convites/{convite['id']}")
    # redefinição: solicitar (campos), link inválido
    tela.ir("/redefinir-senha")
    page.wait_for_selector("#form-solicitar:not([hidden])")
    _axe(page, "/redefinir-senha solicitar")
    _capturar(page, "redefinir_solicitar")
    page.fill("#inquilino", slug)
    page.fill("#email", "sem-arroba")
    page.click("#solicitar")
    assert page.locator("#email[aria-invalid='true']").count() == 1
    assert _erro_do_campo(page, "email") != ""
    tela.ir("/redefinir-senha?token=naoexiste")
    assert page.locator("#estado[tipo='erro']").count() == 1 and page.locator("#form-aplicar").is_hidden()
    assert page.locator("#estado button").count() == 1
    _axe(page, "/redefinir-senha link inválido")
    _capturar(page, "redefinir_invalido")
    tela.verificar()
