"""e2e /admin/logins, criação do provedor gov.br pela tela (item L0-08-c-govbr): o formulário mostra os campos que
o roteiro pede (issuer por ambiente, client_id, client_secret, redirect_uri fixa da instalação, escopos), cria o
provedor e ele aparece na lista com o modelo gov.br. Captura L0-08-c-govbr_logins.png. Sem IdP real: só a
configuração (o teste real fica pendente da credencial do órgão)."""

import pytest

from tests.e2e.apoio import CAPTURAS, Tela, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-08-c-govbr"


def test_criar_provedor_govbr_pela_tela(page, base_url, credenciais_demo, admin_api, medida):
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    provedor_id = None
    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/logins")
        tela.medidas["pagina_pronta_ms_logins_govbr"] = tela.ir("/admin/logins")
        page.click("#novo-oidc")
        page.wait_for_selector("#form-oidc", timeout=15000)
        assert page.input_value("#o-modelo") == "govbr"
        assert page.input_value("#o-issuer") == "https://sso.staging.acesso.gov.br"
        assert "govbr_confiabilidades" in page.input_value("#o-escopos")
        assert page.text_content("#o-redirect").endswith("/api/sso/oidc/retorno")
        page.select_option("#o-ambiente", "https://sso.acesso.gov.br")
        assert page.input_value("#o-issuer") == "https://sso.acesso.gov.br"
        page.fill("#o-client-id", f"cliente-govbr-e2e-{s}")
        page.fill("#o-client-secret", "segredo-e2e-nunca-mostrado")
        page.fill("#o-rotulo", f"Entrar com gov.br e2e {s}")
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_logins.png"), full_page=True)
        page.click("#oidc-salvar")
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#tabela tbody td')]"
            f".some(td => td.textContent === 'Entrar com gov.br e2e {s}')",
            timeout=15000,
        )
        lista = tela.api("GET", "/api/org/oidc").json()
        p = next(x for x in lista if x["client_id"] == f"cliente-govbr-e2e-{s}")
        provedor_id = p["id"]
        assert p["modelo"] == "govbr" and p["api_base"] == "https://api.acesso.gov.br"
        assert p["tem_client_secret"] is True and "segredo" not in str(p)
        tela.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (apoio.py Tela.ir)")
    finally:
        if provedor_id:
            admin_api.delete(f"/api/org/oidc/{provedor_id}")
