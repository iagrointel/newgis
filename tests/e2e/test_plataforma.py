"""e2e /plataforma (item L0-07-f-console-plataforma): o superadmin cria o inquilino `demo3` pela tela (senha
temporária mostrada uma vez), o admin de demo3 entra pela tela de login noutro navegador, o superadmin suspende
demo3 com mensagem, o admin vê o 503 com a mensagem no navegador (captura), o superadmin reativa e o admin volta
a navegar. Cookie do superadmin obtido por POST /api/login (+ 2FA por TOTP, segredo do arquivo da trilha) pelo
contexto de pedidos do próprio navegador — nunca por "entrar como".

Capturas: tests/e2e/capturas/L0-07-f-console-plataforma_{console,suspenso}.png."""

import pytest

from tests.api.conftest import credenciais, totp_guardado, totp_guardar
from tests.e2e.apoio import CAPTURAS, Tela, esperar_proximo_passo, passo_atual, texto_aviso, totp

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "L0-07-f-console-plataforma"
SLUG = "demo3"


def _entrar_superadmin(tela: Tela) -> None:
    """Login do superadmin pelo contexto de pedidos do navegador (o cookie fica na página). 2FA obrigatório no
    inquilino `plataforma`: liga na primeira vez e guarda o segredo fora do git (mesma regra de tests/api/conftest)."""
    c = credenciais()
    if "plataforma" not in c:
        pytest.skip("credenciais sem a linha de plataforma (rode install.sh / trilha_ambiente.sh)")
    login, senha = c["plataforma"]
    r = tela.api("POST", "/api/login", {"inquilino": "plataforma", "login": login, "senha": senha})
    assert r.status == 200, r.text()
    j = r.json()
    if j.get("exige_2fa"):
        segredo = totp_guardado("plataforma")
        assert segredo, "plataforma exige 2FA e o segredo não é conhecido"
        passo = passo_atual()
        r = tela.api("POST", "/api/login/2fa", {"desafio": j["desafio"], "codigo": totp(segredo)})
        if r.status == 401 and r.json().get("erro") == "codigo_invalido":
            esperar_proximo_passo(passo)
            r = tela.api("POST", "/api/login", {"inquilino": "plataforma", "login": login, "senha": senha})
            r = tela.api("POST", "/api/login/2fa", {"desafio": r.json()["desafio"], "codigo": totp(segredo)})
        assert r.status == 200, r.text()
        j = r.json()
    if "configurar_2fa" in j["usuario"].get("pendencias", []):
        r = tela.api("POST", "/api/eu/2fa/iniciar", {})
        assert r.status == 200, r.text()
        segredo = r.json()["segredo"]
        r = tela.api("POST", "/api/eu/2fa/confirmar", {"codigo": totp(segredo)})
        assert r.status == 200, r.text()
        totp_guardar("plataforma", login, segredo)
    assert tela.api("GET", "/api/eu").json()["superadmin"] is True


def _apagar_demo3(tela: Tela) -> None:
    for t in tela.api("GET", "/api/plataforma/inquilinos").json():
        if t["slug"] == SLUG:
            assert tela.api("DELETE", f"/api/plataforma/inquilinos/{t['id']}").status == 204


def _painel(page):
    return page.locator("#painel dialog[open]")


def test_criar_demo3_suspender_ver_503_e_reativar(page, browser, browser_context_args, base_url, medida):
    tela = Tela(page, base_url)
    _entrar_superadmin(tela)
    _apagar_demo3(tela)  # rodada anterior abortada
    ctx2 = browser.new_context(**browser_context_args)
    page2 = ctx2.new_page()
    tela2 = Tela(page2, base_url)
    try:
        tela.medidas["pagina_pronta_ms_plataforma"] = tela.ir("/plataforma")
        assert page.locator("#lateral a[href='/plataforma']").count() == 1  # entrada de navegação só do superadmin
        page.wait_for_function("() => document.querySelectorAll('#tabela tbody tr').length >= 3", timeout=15000)
        # criar demo3 pela tela
        page.click("#novo")
        p = _painel(page)
        p.locator("input[name='slug']").fill(SLUG)
        p.locator("input[name='nome']").fill("Inquilino demo3 (e2e)")
        p.locator("input[name='admin_nome']").fill("Administrador demo3")
        p.locator("input[name='cota_usuarios']").fill("15")
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#senha-temporaria", timeout=15000)
        temporaria = page.text_content("#senha-temporaria").strip()
        assert len(temporaria) >= 8
        _painel(page).locator("button", has_text="Fechar").click()
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#tabela tbody td')].some(td => td.textContent === '{SLUG}')",
            timeout=15000,
        )
        demo3 = next(t for t in tela.api("GET", "/api/plataforma/inquilinos").json() if t["slug"] == SLUG)
        assert demo3["cota_usuarios"] == 15 and demo3["ativo"] is True
        CAPTURAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_console.png"), full_page=True)
        # o admin de demo3 entra pela tela de login noutro navegador (senha temporária -> pendência -> /conta)
        tela2.entrar(SLUG, "admin", temporaria, proximo="/conta")
        assert "/conta" in page2.url
        assert tela2.api("GET", "/api/eu").json()["inquilino"]["slug"] == SLUG
        # o superadmin suspende demo3 pela tela, com mensagem para os membros
        linha = page.locator("#tabela tbody tr", has_text=SLUG)
        linha.locator("button", has_text="Suspender").click()
        p = _painel(page)
        p.locator("textarea[name='mensagem']").fill("manutenção programada até sexta")
        p.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert SLUG in texto_aviso(page)
        # o admin de demo3 vê o 503 no navegador, com a mensagem; nada foi apagado
        tela2.esperar_status(503)
        page2.goto("/conta", wait_until="domcontentloaded")
        page2.wait_for_selector("plat-aviso[data-tipo='erro']", timeout=15000)
        falha = page2.text_content("main")
        assert "503" in falha and "manutenção programada até sexta" in falha, falha
        r = tela2.api("GET", "/api/eu")
        assert r.status == 503 and r.json()["erro"] == "inquilino_suspenso"
        page2.screenshot(path=str(CAPTURAS / f"{ITEM}_suspenso.png"), full_page=True)
        # login novo também recebe o 503 com a mensagem
        tela2.esperar_status(503)
        page2.goto(f"/entrar?inquilino={SLUG}", wait_until="domcontentloaded")
        page2.wait_for_selector("body[data-pronto='1']", timeout=20000)
        page2.fill("#login", "admin")
        page2.fill("#senha", temporaria)
        page2.click("#entrar")
        page2.wait_for_selector("#aviso:not([hidden])", timeout=15000)
        assert "manutenção programada até sexta" in texto_aviso(page2)
        # reativar pela tela: a MESMA sessão do admin volta a funcionar (dado intacto)
        linha = page.locator("#tabela tbody tr", has_text=SLUG)
        linha.locator("button", has_text="Reativar").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        assert tela2.api("GET", "/api/eu").status == 200
        tela2.ir("/conta")
        assert page2.locator("plat-aviso[data-tipo='erro']").count() == 0
        # a trilha da plataforma registrou tudo, na tela
        page.wait_for_function(
            "() => [...document.querySelectorAll('#eventos-tabela tbody td')].some(td => td.textContent === 'inquilinos/reativar')",
            timeout=15000,
        )
        tipos = [td.strip() for td in page.locator("#eventos-tabela tbody td.mono").all_text_contents()]
        assert {"inquilinos/criar", "inquilinos/suspender", "inquilinos/reativar"} <= set(tipos), tipos
        tela.verificar()
        tela2.verificar()
        gravar = medida(ITEM)
        for nome, valor in tela.medidas.items():
            gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright (tests/e2e/apoio.py Tela.ir)")
        gravar("e2e_demo3_criar_suspender_503_reativar", 1, "fluxo", "tests/e2e/test_plataforma.py: criar demo3 pela tela, admin entra, suspender com mensagem, 503 no navegador, reativar")
    finally:
        _apagar_demo3(tela)
        ctx2.close()
