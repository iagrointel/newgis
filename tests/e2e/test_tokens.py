"""e2e /admin/tokens (ADR 0002 seções 8 e 15.5): criar token pela tela (mostrado uma vez, prefixo plat_), usar com
Bearer em /api/eu, ver o acesso na aba Acessos, revogar e provar o 401 token_revogado em seguida.
Captura L0-02-tenant-auth_tokens.png."""

import time

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def test_token_criar_usar_acessos_revogar(page, base_url, credenciais_demo, medida):
    slug, admin_login, senha_admin = credenciais_demo
    nome = f"token e2e {sufixo()}"
    tela = Tela(page, base_url)
    tela.entrar(slug, admin_login, senha_admin, proximo="/admin/tokens")
    tela.medidas["pagina_pronta_ms_tokens"] = tela.ir("/admin/tokens")
    page.click("#novo")
    p = page.locator("#painel dialog[open]")
    p.locator("input[name='nome']").fill(nome)
    p.locator("input[value='catalogo:ler']").check()
    p.locator("button[type='submit']").click()
    page.wait_for_selector("#token-valor", timeout=15000)
    token = page.text_content("#token-valor").strip()
    assert token.startswith("plat_") and len(token) >= 40, token
    page.locator("#painel dialog[open] button", has_text="Fechar").click()
    linha = page.locator("#tabela tbody tr", has_text=nome)
    assert token[:12] in linha.text_content()
    # uso por Bearer, fora do cookie
    ctx = page.context.browser.new_context()
    r = ctx.request.get(f"{base_url}/api/eu", headers={"Authorization": f"Bearer {token}"})
    assert r.status == 200 and r.json()["login"] == admin_login, r.text()
    tid = r.json()["token"]["id"]
    tela.capturar("tokens")
    page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Acessos").click()
    page.wait_for_function("() => [...document.querySelectorAll('#painel dialog[open] tbody td')]"
                           ".some(td => td.textContent.includes('/api/eu'))", timeout=15000)
    page.locator("#painel dialog[open] button", has_text="Fechar").click()
    # revogar pela tela e provar o 401 em <= 1 s
    page.locator("#tabela tbody tr", has_text=nome).locator("button", has_text="Revogar").click()
    page.locator("plat-dialogo dialog[open] button", has_text="Revogar").last.click()
    page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
    t0 = time.perf_counter()
    r2 = ctx.request.get(f"{base_url}/api/eu", headers={"Authorization": f"Bearer {token}"})
    tela.medidas["tempo_revogacao_ms_e2e"] = round((time.perf_counter() - t0) * 1000, 1)
    assert r2.status == 401 and r2.json()["erro"] == "token_revogado", r2.text()
    ctx.close()
    assert "revogado" in page.locator("#tabela tbody tr", has_text=nome).text_content()
    assert tela.api("GET", f"/api/tokens/{tid}").json()["revogado_em"]
    tela.verificar()
    gravar_medidas(medida, tela)
