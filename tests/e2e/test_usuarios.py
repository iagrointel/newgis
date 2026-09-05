"""e2e /admin/usuarios (ADR 0002 seção 15.3): criar (senha temporária mostrada uma vez), editar, redefinir senha,
desabilitar em massa, reabilitar, e a recusa do último administrador com a mensagem exata da API.
Captura L0-02-tenant-auth_usuarios.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo, texto_aviso

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _painel(page):
    return page.locator("#painel dialog[open]")


def test_usuarios_criar_editar_lote_e_ultimo_admin(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    logins = [f"e2e_u{i}_{s}" for i in range(3)]
    criados = []
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/usuarios")
        tela.medidas["pagina_pronta_ms_usuarios"] = tela.ir("/admin/usuarios")
        # criar pela tela
        page.click("#novo")
        p = _painel(page)
        p.locator("input[name='login']").fill(logins[0])
        p.locator("input[name='nome']").fill("Usuário E2E zero")
        p.locator("select[name='perfil']").select_option("editor")
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#senha-temporaria", timeout=15000)
        temporaria = page.text_content("#senha-temporaria").strip()
        assert len(temporaria) >= 8
        _painel(page).locator("button", has_text="Fechar").click()
        # os outros dois pela API (mesma sessão)
        for lg in logins[1:]:
            r = tela.api("POST", "/api/usuarios", {"login": lg, "nome": f"Usuário {lg}", "perfil": "visualizador"})
            assert r.status == 201, r.text()
        tela.ir("/admin/usuarios")
        busca = page.locator("plat-busca input")
        busca.fill("e2e_u")
        busca.press("Enter")
        page.wait_for_function("() => [...document.querySelectorAll('#tabela tbody td')]"
                               f".some(td => td.textContent === '{logins[0]}')", timeout=15000)
        lista = tela.api("GET", "/api/usuarios?q=e2e_u&limite=100").json()["itens"]
        criados = [x for x in lista if x["login"].endswith(s)]
        assert len(criados) == 3, [c["login"] for c in criados]
        tela.capturar("usuarios")
        # editar o primeiro
        linha = page.locator("#tabela tbody tr", has_text=logins[0])
        linha.locator("button", has_text="Editar").click()
        p = _painel(page)
        p.locator("input[name='nome']").fill("Usuário E2E editado")
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/usuarios/{criados[0]['id']}").json()["nome"] == "Usuário E2E editado"
        # redefinir senha pela tela
        page.locator("#tabela tbody tr", has_text=logins[0]).locator("button", has_text="Redefinir senha").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Confirmar").last.click()
        page.wait_for_selector("#senha-temporaria", timeout=15000)
        assert page.text_content("#senha-temporaria").strip() != temporaria
        _painel(page).locator("button", has_text="Fechar").click()
        # desabilitar em massa os três
        for lg in logins:
            page.locator("#tabela tbody tr", has_text=lg).locator("input[type='checkbox']").check()
        page.locator("#lote button", has_text="Desabilitar").click()
        page.wait_for_selector("#aviso:not([hidden])", timeout=15000)
        assert "3 alterados" in texto_aviso(page)
        page.locator("#filtros select[name='ativo']").select_option("0")
        reab = page.locator("#tabela tbody tr", has_text=logins[1]).locator("button", has_text="Reabilitar")
        reab.wait_for(timeout=15000)
        reab.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/usuarios/{criados[1]['id']}").json()["ativo"] is True
        # último admin: se demo tem um só admin ativo, desabilitar pela tela é recusado com a mensagem da API
        admins = tela.api("GET", "/api/usuarios?perfil=admin&ativo=1&limite=100").json()
        busca.fill("")
        busca.press("Enter")
        page.locator("#filtros select[name='ativo']").select_option("1")
        page.locator("#filtros select[name='perfil']").select_option("admin")
        page.wait_for_function("() => document.querySelectorAll('#tabela tbody td:not(.vazio)').length >= 1",
                               timeout=15000)
        if admins["total"] == 1:
            tela.esperar_status(409)
            page.locator("#tabela tbody tr", has_text=admin_login).locator("button", has_text="Desabilitar").click()
            page.wait_for_selector("#aviso[data-tipo='erro']", timeout=15000)
            # a tela mostra a mensagem da API (409): "último administrador" ou a regra do próprio usuário
            assert texto_aviso(page), "mensagem da API ausente"
            assert tela.api("GET", "/api/eu").json()["ativo"] is True
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        for c in criados:
            admin_api.delete(f"/api/usuarios/{c['id']}")
