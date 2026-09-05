"""e2e /entrar (ADR 0002 seção 15.1): senha errada mostra a mensagem da API; senha certa entra, guarda o inquilino e
mostra a barra lateral com o nome do usuário; 0 erro de console; captura L0-02-tenant-auth_login*.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, texto_aviso

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_senha_errada_mostra_mensagem_e_nao_entra(page, base_url, credenciais_demo):
    slug, login, _ = credenciais_demo
    tela = Tela(page, base_url)
    tela.esperar_status(401)
    tela.ir(f"/entrar?inquilino={slug}", "pagina_pronta_ms_login")
    assert page.text_content("#inquilino-rotulo").strip() != ""
    page.fill("#login", login)
    page.fill("#senha", "senha-errada-1")
    page.click("#entrar")
    page.wait_for_selector("#aviso:not([hidden])", timeout=15000)
    assert "inválid" in texto_aviso(page).lower()
    assert "/entrar" in page.url
    tela.capturar("login_erro")
    tela.verificar()


def test_login_com_senha_entra_e_mostra_barra(page, base_url, credenciais_demo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.ir(f"/entrar?inquilino={slug}", "pagina_pronta_ms_login")
    tela.capturar("login")
    tela.entrar(slug, login, senha, proximo="/conta")
    assert page.url.rstrip("/").endswith("/conta")
    assert login in page.text_content("#pessoa-nome")
    assert page.evaluate("() => localStorage.getItem('plat_inquilino')") == slug
    eu = tela.api("GET", "/api/eu").json()
    assert eu["login"] == login and eu["inquilino"]["slug"] == slug
    tela.sair()
    assert "/entrar" in page.url
    tela.esperar_status(401)
    assert tela.api("GET", "/api/eu").status == 401
    tela.verificar()
    gravar_medidas(medida, tela)
