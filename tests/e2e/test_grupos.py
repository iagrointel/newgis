"""e2e /admin/grupos (ADR 0002 seção 15.4): admin cria grupo pela tela, convida um usuário pela busca; o convidado
aceita em /conta; o grupo lista o membro ativo; o convidado sai; o dono apaga. Captura L0-02-tenant-auth_grupos.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, local, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_grupo_criar_convidar_aceitar_sair_apagar(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    login = f"e2e_g_{s}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "Convidado E2E", "perfil": "editor"})
    assert r.status == 201, r.text()
    uid, temporaria = r.json()["usuario"]["id"], r.json()["senha_temporaria"]
    nome_grupo = f"Grupo E2E {s}"
    gid = None
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/grupos")
        tela.medidas["pagina_pronta_ms_grupos"] = tela.ir("/admin/grupos")
        page.click("#novo")
        p = page.locator("#painel dialog[open]")
        p.locator("input[name='nome']").fill(nome_grupo)
        p.locator("textarea[name='resumo']").fill("grupo criado pelo e2e")
        p.locator("select[name='visibilidade']").select_option("inquilino")
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        grupos = tela.api("GET", "/api/grupos?meus=1&limite=100").json()["itens"]
        gid = next(g["id"] for g in grupos if g["nome"] == nome_grupo)
        # abrir e convidar
        page.locator("#tabela tbody tr", has_text=nome_grupo).locator("button", has_text="Abrir").click()
        p = page.locator("#painel dialog[open]")
        p.locator("[role='tab']", has_text="Membros").click()
        p.locator("plat-busca input").fill(login)
        p.locator("plat-busca input").press("Enter")
        p.locator("#convidar-resultados button", has_text="Convidar").click()
        page.wait_for_function("() => [...document.querySelectorAll('#painel dialog[open] tbody td')]"
                               ".some(td => td.textContent.trim() === 'convidado')", timeout=15000)
        tela.capturar("grupos")
        # o convidado aceita em /conta (troca a senha temporária antes)
        ctx2 = page.context.browser.new_context(base_url=base_url, locale="pt-BR",
                                                viewport={"width": 1280, "height": 800},
                                                ignore_https_errors=local(base_url))
        pag2 = ctx2.new_page()
        tela2 = Tela(pag2, base_url)
        tela2.entrar(slug, login, temporaria)
        nova = f"Senha{s}4z"
        pag2.fill("#form-senha input[name='atual']", temporaria)
        pag2.fill("#form-senha input[name='nova']", nova)
        pag2.click("#form-senha button[type='submit']")
        pag2.wait_for_selector("#form-senha plat-aviso[data-tipo='ok']", timeout=15000)
        tela2.ir("/conta#convites")
        pag2.locator("#tabela-convites tbody tr", has_text=nome_grupo).locator("button", has_text="Aceitar").click()
        pag2.wait_for_selector("#aviso-convites[data-tipo='ok']", timeout=15000)
        membros = tela2.api("GET", f"/api/grupos/{gid}/membros").json()
        assert any(m["usuario"]["id"] == uid and m["estado"] == "ativo" for m in membros), membros
        # o convidado sai pela tela
        tela2.ir("/admin/grupos")
        pag2.locator("#tabela tbody tr", has_text=nome_grupo).locator("button", has_text="Abrir").click()
        pag2.locator("#painel dialog[open] #sair-grupo").click()
        pag2.locator("plat-dialogo dialog[open] button", has_text="Confirmar").last.click()
        pag2.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        tela2.verificar()
        ctx2.close()
        # o dono apaga pela tela
        tela.ir("/admin/grupos")
        page.locator("#tabela tbody tr", has_text=nome_grupo).locator("button", has_text="Abrir").click()
        page.locator("#painel dialog[open] #apagar-grupo").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        tela.esperar_status(404)
        assert tela.api("GET", f"/api/grupos/{gid}").status == 404
        gid = None
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        if gid:
            admin_api.delete(f"/api/grupos/{gid}")
        admin_api.delete(f"/api/usuarios/{uid}")
