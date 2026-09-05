"""e2e 2FA (ADR 0002 seções 7 e 15): usuário novo liga o segundo fator pela tela (QR do servidor + segredo em texto),
recebe 8 códigos de recuperação, sai, entra com senha + código TOTP (calculado pela função de 6 linhas), depois desliga
pela tela. Anti-replay respeitado: o teste espera o passo seguinte antes de reusar o segredo."""

import re

import pytest

from tests.e2e.apoio import Tela, esperar_proximo_passo, gravar_medidas, passo_atual, sufixo, totp

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_ligar_entrar_com_codigo_e_desligar(page, base_url, credenciais_demo, admin_api, medida):
    slug = credenciais_demo[0]
    login = f"e2e_2fa_{sufixo()}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "Dois Fatores E2E", "perfil": "editor"})
    assert r.status == 201, r.text()
    uid, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
    senha = f"Senha{sufixo()}7q"
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, login, temporaria)
        page.fill("#form-senha input[name='atual']", temporaria)
        page.fill("#form-senha input[name='nova']", senha)
        page.click("#form-senha button[type='submit']")
        page.wait_for_selector("#form-senha plat-aviso[data-tipo='ok']", timeout=15000)

        page.click("#ligar-2fa")
        page.wait_for_selector("#segredo-2fa", timeout=15000)
        segredo = page.text_content("#segredo-2fa").strip()
        assert re.fullmatch(r"[A-Z2-7]{16,64}", segredo), segredo
        assert page.locator(".svg-qr svg").count() == 1
        assert page.locator(".svg-qr script").count() == 0  # DOMPurify: nada de script no SVG vindo do servidor
        passo = passo_atual()
        page.fill("#area-2fa input[name='codigo']", totp(segredo))
        page.click("#area-2fa button[type='submit']")
        page.wait_for_selector("#codigos-recuperacao", timeout=15000)
        codigos = [x.strip() for x in page.locator("#codigos-recuperacao li").all_text_contents()]
        assert len(codigos) == 8 and all(re.fullmatch(r"[a-z0-9-]{8,14}", c) for c in codigos), codigos
        assert page.text_content("#estado-2fa").strip() == "ligado"
        tela.medidas["pagina_pronta_ms_2fa"] = tela.ir("/conta#2fa")
        tela.capturar("2fa")

        tela.sair()
        page.fill("#login", login)
        page.fill("#senha", senha)
        page.click("#entrar")
        page.wait_for_selector("#form-2fa:not([hidden])", timeout=15000)
        assert page.locator("#form-senha").is_hidden()
        assert re.search(r"\d:\d\d", page.text_content("#contador") or "")
        esperar_proximo_passo(passo)
        passo = passo_atual()
        page.fill("#codigo", totp(segredo))
        page.click("#confirmar")
        page.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        eu = tela.api("GET", "/api/eu").json()
        assert eu["login"] == login and eu["totp_ativo"] is True

        tela.ir("/conta#2fa")
        page.click("#desligar-2fa")
        esperar_proximo_passo(passo)
        dlg = page.locator("plat-dialogo dialog[open]")
        dlg.locator("input[name='senha']").fill(senha)
        dlg.locator("input[name='codigo']").fill(totp(segredo))
        dlg.locator("button[type='submit']").click()
        page.wait_for_selector("#area-2fa plat-aviso[data-tipo='ok']", timeout=15000)
        assert page.text_content("#estado-2fa").strip() == "desligado"
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        admin_api.delete(f"/api/usuarios/{uid}")
