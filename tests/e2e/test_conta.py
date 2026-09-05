"""e2e /conta (ADR 0002 seção 15.2): usuário novo entra com senha temporária, cai em /conta#senha com a pendência,
troca a senha pela tela, vê as sessões (a atual marcada) e encerra as outras. Captura L0-02-tenant-auth_conta.png."""

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_pendencia_de_senha_troca_e_sessoes(page, base_url, credenciais_demo, admin_api, medida):
    slug = credenciais_demo[0]
    login = f"e2e_conta_{sufixo()}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "Conta E2E", "perfil": "visualizador"})
    assert r.status == 201, r.text()
    criado = r.json()
    uid, temporaria = criado["usuario"]["id"], criado["senha_temporaria"]
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, login, temporaria)
        assert page.url.endswith("/conta#senha"), page.url
        tela.medidas["pagina_pronta_ms_conta"] = tela.ir("/conta")
        assert "temporária" in (page.text_content("#pendencia") or "")
        nova = f"Nova{sufixo()}9x"
        page.fill("#form-senha input[name='atual']", temporaria)
        page.fill("#form-senha input[name='nova']", nova)
        page.click("#form-senha button[type='submit']")
        page.wait_for_selector("#form-senha plat-aviso[data-tipo='ok']", timeout=15000)
        assert (page.text_content("#pendencia") or "").strip() == ""
        # segunda sessão pela API, para a tabela ter uma linha a encerrar
        ctx2 = page.context.browser.new_context()
        r2 = ctx2.request.post(f"{base_url}/api/login", data={"inquilino": slug, "login": login, "senha": nova})
        assert r2.status == 200 and r2.json()["ok"] is True
        tela.ir("/conta")
        linhas = page.locator("#tabela-sessoes tbody tr")
        assert linhas.count() >= 2
        assert page.locator("#tabela-sessoes .marcador.ok").count() == 1
        tela.capturar("conta")
        page.click("#encerrar-outras")
        page.wait_for_selector("#aviso-sessoes[data-tipo='ok']", timeout=15000)
        page.wait_for_function("() => document.querySelectorAll('#tabela-sessoes tbody tr').length === 1",
                               timeout=15000)
        tela.esperar_status(401)
        assert ctx2.request.get(f"{base_url}/api/eu").status == 401
        ctx2.close()
        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        admin_api.delete(f"/api/usuarios/{uid}")
