"""e2e /admin/usuarios (ADR 0002 seção 15.3): criar (senha temporária mostrada uma vez), editar, redefinir senha,
desabilitar em massa, reabilitar, e a recusa do último administrador com a mensagem exata da API.
Captura L0-02-tenant-auth_usuarios.png."""

import time

import pytest

from tests.e2e.apoio import Tela, gravar_medidas, sufixo, texto_aviso, totp

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


def test_usuarios_perfil_lote_2fa_desbloquear_apagar_com_grupos_e_401(
    page, base_url, credenciais_demo, admin_api, playwright, medida
):
    """Complemento do teste acima (item L0-02-f): as cláusulas do portão ainda não exercitadas pela tela — mudar
    perfil em massa, desligar 2FA, desbloquear, apagar recusado com os 2 grupos nomeados, e o tempo até o usuário
    desabilitado receber 401 na próxima requisição."""
    slug, admin_login, senha_admin = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    criados: list[int] = []
    grupos: list[int] = []
    contextos = []

    def _login(ctx, login: str, senha: str):
        """POST /api/login com espera e nova tentativa no 429 do nginx (`plat_login`, 10 r/min, burst 10 nodelay,
        `/etc/nginx/conf.d/plat_limites.conf`): este teste faz login de verdade várias vezes (2FA, bloqueio,
        grupos, 401) e a máquina roda outras trilhas do turno contra a mesma URL ao mesmo tempo."""
        for tentativa in range(6):
            r = ctx.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha})
            if r.status != 429:
                return r
            time.sleep(6 * (tentativa + 1))
        return r

    def _como(login: str, senha: str):
        """Sessão de API própria de um usuário recém-criado, já com a pendência `trocar_senha` resolvida — sem
        isso a API barra qualquer rota fora da exceção (403 `pendencia`), inclusive `POST /api/grupos`."""
        ctx = playwright.request.new_context(base_url=base_url)
        contextos.append(ctx)
        r = _login(ctx, login, senha)
        assert r.status == 200, r.text()
        if r.json()["usuario"]["pendencias"]:
            r2 = ctx.put("/api/eu/senha", data={"atual": senha, "nova": f"Senha-definitiva-{s}9z"})
            assert r2.status == 204, r2.text()
        return ctx

    try:
        tela.entrar(slug, admin_login, senha_admin, proximo="/admin/usuarios")
        busca = page.locator("plat-busca input")

        def _buscar_ate_aparecer(termo: str, login_esperado: str):
            tela.ir("/admin/usuarios")
            busca.fill(termo)
            busca.press("Enter")
            page.wait_for_function(
                "([t]) => [...document.querySelectorAll('#tabela tbody td')].some(td => td.textContent === t)",
                arg=[login_esperado],
                timeout=15000,
            )

        # ---------- mudar perfil em massa (3 usuários) pela tela ----------
        logins_p = [f"e2e_pl{i}_{s}" for i in range(3)]
        for lg in logins_p:
            r = tela.api("POST", "/api/usuarios", {"login": lg, "nome": f"Perfil {lg}", "perfil": "visualizador"})
            assert r.status == 201, r.text()
            criados.append(r.json()["usuario"]["id"])
        _buscar_ate_aparecer("e2e_pl", logins_p[0])
        for lg in logins_p:
            page.locator("#tabela tbody tr", has_text=lg).locator("input[type='checkbox']").check()
        page.locator("#lote select[name='perfil_lote']").select_option(label="editor")
        page.wait_for_selector("#aviso:not([hidden])", timeout=15000)
        assert "3 alterados" in texto_aviso(page)
        for cid in criados[-3:]:
            assert tela.api("GET", f"/api/usuarios/{cid}").json()["perfil"] == "editor"

        # ---------- desligar 2FA pela tela (o usuário liga o próprio 2FA antes, pela API) ----------
        login_2fa = f"e2e_2fa_{s}"
        r = tela.api("POST", "/api/usuarios", {"login": login_2fa, "nome": "2FA E2E", "perfil": "editor"})
        assert r.status == 201, r.text()
        u2fa, temp2fa = r.json()["usuario"], r.json()["senha_temporaria"]
        criados.append(u2fa["id"])
        ctx = _como(login_2fa, temp2fa)
        r = ctx.post("/api/eu/2fa/iniciar", data={})
        assert r.status == 200, r.text()
        segredo = r.json()["segredo"]
        r = ctx.post("/api/eu/2fa/confirmar", data={"codigo": totp(segredo)})
        assert r.status == 200, r.text()
        _buscar_ate_aparecer(login_2fa, login_2fa)
        page.locator("#tabela tbody tr", has_text=login_2fa).locator("button", has_text="Desligar 2FA").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Confirmar").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/usuarios/{u2fa['id']}").json()["totp_ativo"] is False

        # ---------- desbloquear pela tela (5 senhas erradas bloqueiam antes) ----------
        login_bl = f"e2e_bl_{s}"
        r = tela.api("POST", "/api/usuarios", {"login": login_bl, "nome": "Bloqueio E2E", "perfil": "editor"})
        assert r.status == 201, r.text()
        ubl = r.json()["usuario"]
        criados.append(ubl["id"])
        ctx_bl = playwright.request.new_context(base_url=base_url)
        contextos.append(ctx_bl)
        # bloqueio_tentativas padrão = 5 (app/limites.py): a 5ª senha errada já bloqueia, mas ainda responde 401
        # (o "já bloqueado" só é visto na tentativa seguinte); por isso 6 tentativas, não 5.
        ultima = None
        for _ in range(6):
            ultima = _login(ctx_bl, login_bl, "senha-errada-xx")
        assert ultima.status == 423, ultima.text()
        _buscar_ate_aparecer(login_bl, login_bl)  # o bloqueio não muda `ativo`: continua no filtro padrão
        page.locator("#tabela tbody tr", has_text=login_bl).locator("button", has_text="Desbloquear").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela.api("GET", f"/api/usuarios/{ubl['id']}").json()["bloqueado_ate"] is None

        # ---------- apagar usuário com 2 grupos: recusa listando os 2 nomes ----------
        login_gr = f"e2e_gr_{s}"
        r = tela.api("POST", "/api/usuarios", {"login": login_gr, "nome": "Grupos E2E", "perfil": "editor"})
        assert r.status == 201, r.text()
        ugr, tempgr = r.json()["usuario"], r.json()["senha_temporaria"]
        criados.append(ugr["id"])
        ctx_gr = _como(login_gr, tempgr)
        nomes_grupos = [f"Grupo E2E apagar {i} {s}" for i in range(2)]
        for ng in nomes_grupos:
            rg = ctx_gr.post("/api/grupos", data={"nome": ng})
            assert rg.status == 201, rg.text()
            grupos.append(rg.json()["id"])
        _buscar_ate_aparecer(login_gr, login_gr)
        tela.esperar_status(409)
        page.locator("#tabela tbody tr", has_text=login_gr).locator("button", has_text="Apagar").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").last.click()
        page.wait_for_selector("#aviso[data-tipo='erro']", timeout=15000)
        aviso_txt = texto_aviso(page)
        assert all(ng in aviso_txt for ng in nomes_grupos), aviso_txt
        for gid in grupos:
            assert tela.api("DELETE", f"/api/grupos/{gid}").status == 204
        grupos = []
        _buscar_ate_aparecer(login_gr, login_gr)
        page.locator("#tabela tbody tr", has_text=login_gr).locator("button", has_text="Apagar").click()
        page.locator("plat-dialogo dialog[open] button", has_text="Apagar").last.click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        criados.remove(ugr["id"])

        # ---------- desabilitar pela tela -> 401 na PRÓXIMA requisição do usuário em <= 1 s ----------
        login_401 = f"e2e_401_{s}"
        r = tela.api("POST", "/api/usuarios", {"login": login_401, "nome": "401 E2E", "perfil": "editor"})
        assert r.status == 201, r.text()
        u401, temp401 = r.json()["usuario"], r.json()["senha_temporaria"]
        criados.append(u401["id"])
        ctx401 = _como(login_401, temp401)
        assert ctx401.get("/api/eu").status == 200
        _buscar_ate_aparecer(login_401, login_401)
        t0 = time.perf_counter()
        page.locator("#tabela tbody tr", has_text=login_401).locator("button", has_text="Desabilitar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        r401 = ctx401.get("/api/eu")
        ms = round((time.perf_counter() - t0) * 1000, 1)
        assert r401.status == 401, r401.text()
        assert ms <= 1000, f"{ms} ms"
        tela.medidas["desabilitar_para_401_ms"] = ms

        tela.verificar()
        gravar_medidas(medida, tela)
    finally:
        for gid in grupos:
            admin_api.delete(f"/api/grupos/{gid}")
        for cid in criados:
            admin_api.delete(f"/api/usuarios/{cid}")
        for ctx in contextos:
            ctx.dispose()
