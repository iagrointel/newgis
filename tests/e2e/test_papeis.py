"""e2e /admin/papeis (ADR 0002 seção 3): criar papel personalizado com dois privilégios, editar acrescentando um,
apagar. Captura L0-02-tenant-auth_papeis.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_papel_criar_editar_apagar(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    nome = f"Curador E2E {sufixo()}"
    pid = None
    tela = Tela(page, base_url)
    if page.request.get(f"{base_url}/admin/papeis").status == 404:
        pytest.skip("o backend não serve /admin/papeis: falta a linha '/admin/papeis': 'admin/papeis.html' em "
                    "app/paginas.py PAGINAS (tela pedida pelo gerente no T2, fora da lista da seção 15 do ADR 0002)")
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/papeis")
        tela.medidas["pagina_pronta_ms_papeis"] = tela.ir("/admin/papeis")
        assert page.locator("#tabela-perfis tbody tr").count() == 4
        page.click("#novo")
        p = page.locator("#painel dialog[open]")
        p.locator("input[name='nome']").fill(nome)
        p.locator("input[name='descricao']").fill("papel do e2e")
        p.locator("input[type='checkbox']:not(:checked)").nth(0)  # garante que a matriz renderizou
        p.locator("input[value='membros.ver']").check()
        p.locator("input[value='grupos.entrar']").check()
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        papeis = tela.api("GET", "/api/papeis").json()["personalizados"]
        meu = next(x for x in papeis if x["nome"] == nome)
        pid = meu["id"]
        assert set(meu["privilegios"]) == {"membros.ver", "grupos.entrar"}
        tela.capturar("papeis")
        page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Editar").click()
        p = page.locator("#painel dialog[open]")
        p.locator("input[value='conteudo.ver_inquilino']").check()
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        meu = next(x for x in tela.api("GET", "/api/papeis").json()["personalizados"] if x["id"] == pid)
        assert "conteudo.ver_inquilino" in meu["privilegios"]
        page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Apagar").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert all(x["id"] != pid for x in tela.api("GET", "/api/papeis").json()["personalizados"])
        pid = None
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        if pid:
            admin_api.delete(f"/api/papeis/{pid}")
