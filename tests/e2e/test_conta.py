"""e2e /conta (ADR 0002 seção 15.2): usuário novo entra com senha temporária, cai em /conta#senha com a pendência,
troca a senha pela tela, vê as sessões (a atual marcada) e encerra as outras. Captura L0-02-tenant-auth_conta.png.

Item L0-02-g-perfil-usuario: editar nome/unidades, enviar foto e vê-la na barra lateral, e-mail fora do domínio
do próprio inquilino recusado com mensagem — captura L0-02-tenant-auth_perfil.png."""

import io

import pytest
from PIL import Image

from tests.e2e.apoio import Tela, gravar_medidas, sufixo

pytestmark = [pytest.mark.lento, pytest.mark.e2e]


def _png_bytes(cor=(200, 60, 30)) -> bytes:
    im = Image.new("RGB", (64, 64), cor)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


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


def _corpo_org_atual(org: dict) -> dict:
    return {
        "nome": org["nome"], "cor": org["cor"], "idioma_padrao": org["idioma_padrao"],
        "centro": org["mapa"]["centro"], "zoom": org["mapa"]["zoom"], "basemap": org["mapa"]["basemap"],
        "srid_padrao": org["mapa"]["srid_padrao"], "cota_bytes": org["armazenamento"]["cota_bytes"],
        "cota_usuarios": org["usuarios"]["cota"], "auth": dict(org["auth"]),
    }


def test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio(
    page, base_url, credenciais_demo, admin_api, medida
):
    """Portão do item L0-02-g: editar nome e unidades pela tela, enviar foto e vê-la na barra lateral (sem
    recarregar a página), e-mail com domínio fora da lista do PRÓPRIO inquilino recusado com mensagem."""
    slug = credenciais_demo[0]
    login = f"e2e_perfil_{sufixo()}"
    r = admin_api.post("/api/usuarios", data={"login": login, "nome": "Perfil E2E", "perfil": "editor"})
    assert r.status == 201, r.text()
    criado = r.json()
    uid, temporaria = criado["usuario"]["id"], criado["senha_temporaria"]
    nova = f"Nova{sufixo()}9x"

    org_original = admin_api.get("/api/org").json()
    tela = Tela(page, base_url)
    try:
        tela.entrar(slug, login, temporaria)
        page.fill("#form-senha input[name='atual']", temporaria)
        page.fill("#form-senha input[name='nova']", nova)
        page.click("#form-senha button[type='submit']")
        page.wait_for_selector("#form-senha plat-aviso[data-tipo='ok']", timeout=15000)
        tela.medidas["pagina_pronta_ms_perfil"] = tela.ir("/conta")

        # sem foto: nenhum <img> na barra
        assert page.locator(".lateral .pessoa img").count() == 0

        # 1) editar nome e unidades
        novo_nome = f"Perfil E2E {sufixo()}"
        page.fill("#form-dados input[name='nome']", novo_nome)
        page.select_option("#form-dados select[name='unidades']", "imperial")
        page.click("#form-dados button[type='submit']")
        page.wait_for_selector("#form-dados plat-aviso[data-tipo='ok']", timeout=15000)
        assert page.locator("#pessoa-nome").inner_text().startswith(novo_nome)

        # 2) enviar foto e vê-la na barra, sem recarregar
        page.set_input_files("#foto-arquivo", {"name": "avatar.png", "mimeType": "image/png", "buffer": _png_bytes()})
        page.wait_for_selector("#foto-preview:not([hidden])", timeout=15000)
        page.wait_for_selector(".lateral .pessoa img.foto-perfil", timeout=15000)
        assert page.locator("#pessoa-foto").count() == 1
        tela.capturar("perfil")

        # 3) e-mail fora do domínio do PRÓPRIO inquilino, recusado com mensagem
        auth_restrito = {**org_original["auth"], "dominios_email": ["exemplo-permitido.com.br"]}
        r_org = admin_api.put("/api/org", data=_corpo_org_atual(org_original) | {"auth": auth_restrito})
        assert r_org.status == 200, r_org.text()
        tela.esperar_status(422)  # o PUT /api/eu com e-mail fora do domínio é REJEITADO de propósito
        page.fill("#form-dados input[name='email']", "gente@fora-da-lista.com")
        page.click("#form-dados button[type='submit']")
        erro = page.locator("#form-dados [data-campo='email'] .erro-campo")
        erro.wait_for(timeout=15000)
        assert "domínio" in (erro.inner_text() or "").lower()

        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        admin_api.put("/api/org", data=_corpo_org_atual(org_original))
        admin_api.delete(f"/api/usuarios/{uid}")
