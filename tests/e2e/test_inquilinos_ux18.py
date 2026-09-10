"""e2e do item UX-18-plataforma-sem-tela: as rotas de escrita POST /api/plataforma/inquilinos, POST .../suspender,
POST .../reativar e DELETE .../{id} têm controle na tela /admin/inquilinos (console do superadmin), com os quatro
estados do sistema de design (UX-01):

1. negado REAL: o admin de `demo` (não superadmin) abre a tela e a API responde 404 — estado negado nomeado; a
   entrada do menu nem aparece para ele;
2. superadmin (inquilino `plataforma`, 2FA obrigatório: o código TOTP entra na tela de login): lista real; vazio e
   erro forjados; criar REAL (slug zt-…, senha temporária mostrada uma vez com copiar) e os erros nomeados no campo —
   422 validacao (slug com espaço, REAL), 409 slug_existente (REAL), 409 slug_reservado (forjado);
3. suspender REAL (o admin do inquilino novo deixa de entrar), reativar REAL, 409 plataforma_nao_suspende (forjado)
   e 404 inquilino_inexistente (forjado) nomeados no controle; apagar REAL com dupla confirmação (204, some da
   lista);
4. axe 0 violações sérias; 0 erro de console; capturas 390/1280; medidas em
   tests/medidas/UX-18-plataforma-sem-tela.json."""

import json

import pytest

from tests.api.conftest import entrar, ligar_2fa, novo_cliente, totp_guardado, totp_guardar
from tests.e2e.apoio import CAPTURAS, Tela, credenciais, esperar_proximo_passo, passo_atual, sufixo, totp
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-18-plataforma-sem-tela"
LARGURAS = (390, 1280)
pytestmark = [pytest.mark.lento, pytest.mark.e2e]
_ERRO_SLUG = ("() => (document.querySelector('#form-inquilino [data-campo=slug] .erro-campo')?.textContent || '')"
              ".includes('{c}')")
_LINHA_COM = "(s) => [...document.querySelectorAll('#tabela tbody tr')].some((tr) => tr.textContent.includes(s){extra})"


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


def _axe(page, onde, acumulado):
    graves = serias(page)
    acumulado[onde] = len(graves)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _forjar(page, padrao, metodo, status, corpo, vezes=1):
    restantes = {"n": vezes}

    def rota(route):
        if route.request.method != metodo or restantes["n"] <= 0:
            route.fallback()
            return
        restantes["n"] -= 1
        route.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    page.route(padrao, rota)
    return lambda: page.unroute(padrao, rota)


@pytest.fixture
def superadmin():
    """(login, senha, segredo_totp) do superadmin do inquilino técnico; liga o 2FA pela API na primeira vez (o
    segredo fica no arquivo de credenciais TOTP da trilha, fora do git), como tests/api/conftest.py::sessao_plat."""
    c = credenciais()
    if "plataforma" not in c:
        pytest.skip("sem credenciais do inquilino técnico `plataforma` neste ambiente")
    login, senha = c["plataforma"]
    cli = novo_cliente()
    r = entrar(cli, "plataforma", login, senha, totp_guardado("plataforma"))
    if r.status_code != 200:
        pytest.skip(f"não foi possível entrar como superadmin pela API: {r.status_code} {r.text[:200]}")
    segredo = totp_guardado("plataforma")
    if "configurar_2fa" in r.json()["usuario"]["pendencias"] or not segredo:
        segredo, _codigos = ligar_2fa(cli)
        totp_guardar("plataforma", login, segredo)
    cli.post("/api/logout")
    return login, senha, segredo


def _entrar_superadmin(tela, page, login, senha, segredo, proximo="/admin/inquilinos"):
    esperar_proximo_passo(passo_atual())  # anti-replay: o código usado pela API há pouco não vale de novo
    page.goto(f"/entrar?inquilino=plataforma&proximo={proximo}", wait_until="domcontentloaded")
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    page.fill("#login", login)
    page.fill("#senha", senha)
    page.click("#entrar")
    page.wait_for_selector("#form-2fa:not([hidden])", timeout=20000)
    page.fill("#codigo", totp(segredo))
    page.click("#confirmar")
    page.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)


def test_console_de_inquilinos_com_estados_nomeados(page, base_url, credenciais_demo, superadmin, medida):
    slug_demo, login_demo, senha_demo = credenciais_demo
    login, senha, segredo = superadmin
    tela = Tela(page, base_url)
    violacoes = {}
    estados = []
    novo_id = None
    novo_slug = f"zt-ux18-{sufixo()}"

    # ------------------------------------------------------------ 1. negado REAL (admin de demo não é superadmin)
    tela.esperar_status(404)  # a API não confirma a rota a quem não é superadmin
    tela.entrar(slug_demo, login_demo, senha_demo, proximo="/admin/inquilinos")
    tela.ir("/admin/inquilinos", "pagina_pronta_ms_inquilinos_negado")
    page.wait_for_selector("#lista-estado[tipo='negado']:not([hidden])")
    assert "superadmin" in (page.text_content("#lista-estado") or "")
    assert page.locator("#novo").is_hidden()
    assert page.locator("#lateral a[href='/admin/inquilinos']").count() == 0
    estados.append("lista:negado(real)")
    _axe(page, "/admin/inquilinos negado", violacoes)
    _capturar(page, "negado")
    tela.sair()

    # ------------------------------------------------------------ 2. superadmin: lista; vazio e erro forjados; criar
    _entrar_superadmin(tela, page, login, senha, segredo)
    page.wait_for_function("() => document.getElementById('lista-estado').hidden")
    assert page.locator("#tabela tbody tr").count() >= 3  # plataforma, demo, demo2
    assert page.locator("#lateral a[href='/admin/inquilinos']").count() == 1
    estados.append("lista:conteudo")
    _axe(page, "/admin/inquilinos lista", violacoes)
    _capturar(page, "lista")
    parar = _forjar(page, "**/api/plataforma/inquilinos", "GET", 200, [])
    page.click("#recarregar")
    page.wait_for_selector("#lista-estado[tipo='vazio']:not([hidden])")
    assert page.locator("#lista-estado button[data-acao='novo']").count() == 1
    estados.append("lista:vazio")
    _capturar(page, "vazia", (1280,))
    parar()
    tela.esperar_status(500, 409, 422)
    parar = _forjar(page, "**/api/plataforma/inquilinos", "GET", 500,
                    {"erro": "erro_forjado", "mensagem": "banco indisponível (forjado)", "req_id": "e2e-ux18-500"})
    page.click("#recarregar")
    page.wait_for_selector("#lista-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#lista-estado") or ""
    assert "banco indisponível (forjado)" in texto and "e2e-ux18-500" in texto, texto
    estados.append("lista:erro")
    parar()
    page.click("#lista-estado button[data-acao='tentar']")
    page.wait_for_function("() => document.getElementById('lista-estado').hidden")
    # criar: 422 validacao REAL (slug com espaço) e 409 slug_existente REAL (demo) nomeados no campo slug
    page.click("#novo")
    page.wait_for_selector("#form-inquilino input[name=slug]")
    _axe(page, "/admin/inquilinos novo", violacoes)
    page.fill("#form-inquilino input[name=slug]", "A B")
    page.fill("#form-inquilino input[name=nome]", "Inquilino zt")
    page.fill("#form-inquilino input[name=admin_login]", "gestor")
    page.fill("#form-inquilino input[name=admin_nome]", "Gestor")
    page.click("#form-inquilino button[type=submit]")
    page.wait_for_selector("#form-inquilino [data-campo='slug'] .erro-campo")
    texto = page.text_content("#form-inquilino [data-campo='slug'] .erro-campo") or ""
    assert "validacao" in texto and "422" not in texto, texto
    estados.append("criar:422:slug(real)")
    page.fill("#form-inquilino input[name=slug]", "demo")
    page.click("#form-inquilino button[type=submit]")
    page.wait_for_function(_ERRO_SLUG.format(c="slug_existente"))
    estados.append("criar:409:slug_existente(real)")
    _capturar(page, "criar_409")
    parar = _forjar(page, "**/api/plataforma/inquilinos", "POST", 409,
                    {"erro": "slug_reservado", "mensagem": "este identificador é reservado",
                     "req_id": "e2e-ux18-ref-a"})
    page.fill("#form-inquilino input[name=slug]", "static")
    page.click("#form-inquilino button[type=submit]")
    page.wait_for_function(_ERRO_SLUG.format(c="slug_reservado"))
    estados.append("criar:409:slug_reservado")
    parar()
    page.fill("#form-inquilino input[name=slug]", novo_slug)
    with page.expect_response(lambda r: r.request.method == "POST"
                              and r.url.endswith("/api/plataforma/inquilinos")) as resp:
        page.click("#form-inquilino button[type=submit]")
    assert resp.value.status == 201, resp.value.text()
    novo = resp.value.json()
    novo_id = novo["id"]
    page.wait_for_selector("#inquilino-criado")
    assert page.text_content("#senha-temporaria") == novo["senha_temporaria"]
    assert len(novo["senha_temporaria"]) == 12
    estados.append("criar:ok")
    _axe(page, "/admin/inquilinos criado", violacoes)
    _capturar(page, "criado")
    page.click("plat-dialogo dialog[open] .dialogo-botoes button")
    page.wait_for_function(_LINHA_COM.format(extra=""), arg=novo_slug, timeout=15000)
    # o admin novo entra pela API com a senha temporária (prova de que o inquilino nasceu inteiro)
    cli = novo_cliente()
    r = entrar(cli, novo_slug, "gestor", novo["senha_temporaria"])
    assert r.status_code == 200 and r.json()["usuario"]["pendencias"] == ["trocar_senha"], r.text

    # ------------------------------------------------------------ 3. suspender / reativar / apagar
    linha = page.locator("#tabela tbody tr", has_text=novo_slug)
    parar = _forjar(page, f"**/api/plataforma/inquilinos/{novo_id}/suspender", "POST", 409,
                    {"erro": "plataforma_nao_suspende", "mensagem": "o inquilino da plataforma não se suspende",
                     "req_id": "e2e-ux18-ref-b"})
    linha.locator("button", has_text="Suspender").click()
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    page.wait_for_selector("#acao-estado[tipo='erro']:not([hidden])")
    texto = page.text_content("#acao-estado") or ""
    assert "plataforma_nao_suspende" in texto and "409" not in texto, texto
    estados.append("suspender:409:nomeado")
    _capturar(page, "suspender_409", (1280,))
    parar()
    page.click("#acao-estado button[data-acao='fechar']")
    linha.locator("button", has_text="Suspender").click()
    with page.expect_response(lambda r: r.request.method == "POST"
                              and r.url.endswith(f"/{novo_id}/suspender")) as resp:
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    assert resp.value.status == 204
    page.wait_for_function(_LINHA_COM.format(extra=" && tr.textContent.includes('suspenso')"), arg=novo_slug,
                           timeout=15000)
    assert cli.get("/api/eu").status_code == 401  # a sessão do admin do inquilino suspenso morreu
    estados.append("suspender:ok")
    _capturar(page, "suspenso", (1280,))
    parar = _forjar(page, f"**/api/plataforma/inquilinos/{novo_id}/reativar", "POST", 404,
                    {"erro": "inquilino_inexistente", "mensagem": "inquilino inexistente", "req_id": "e2e-ux18-ref-c"})
    tela.esperar_status(404)
    linha.locator("button", has_text="Reativar").click()
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.primario").click()
    page.wait_for_function(
        "() => (document.getElementById('acao-estado').textContent || '').includes('inquilino_inexistente')")
    estados.append("reativar:404:nomeado")
    parar()
    page.click("#acao-estado button[data-acao='fechar']")
    linha.locator("button", has_text="Reativar").click()
    with page.expect_response(lambda r: r.request.method == "POST"
                              and r.url.endswith(f"/{novo_id}/reativar")) as resp:
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.primario").click()
    assert resp.value.status == 204
    page.wait_for_function(_LINHA_COM.format(extra=" && !tr.textContent.includes('suspenso')"), arg=novo_slug,
                           timeout=15000)
    estados.append("reativar:ok")
    # apagar: duas confirmações, 204, some da lista
    linha.locator("button", has_text="Apagar").click()
    page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    page.wait_for_function(
        "() => document.querySelector('plat-dialogo dialog[open]')?.textContent.includes('Última confirmação')")
    _capturar(page, "apagar_confirma2", (1280,))
    with page.expect_response(lambda r: r.request.method == "DELETE"
                              and r.url.endswith(f"/api/plataforma/inquilinos/{novo_id}")) as resp:
        page.locator("plat-dialogo dialog[open] .dialogo-botoes button.perigo").click()
    assert resp.value.status == 204
    page.wait_for_function("(s) => !" + _LINHA_COM.format(extra="")[6:], arg=novo_slug, timeout=15000)
    novo_id = None
    estados.append("apagar:ok")
    _axe(page, "/admin/inquilinos final", violacoes)
    _capturar(page, "lista_final", (1280,))

    # ------------------------------------------------------------ 4. 0 erro de console; medidas
    tela.verificar()
    gravar = medida(ITEM)
    gravar("estados_provados", len(estados), "estados", "; ".join(estados))
    gravar("violacoes_serias_axe", sum(violacoes.values()), "violações",
           f"axe-core 4.10.3 wcag2a/aa em {', '.join(violacoes)}")
    gravar("erros_de_console", 0, "erros", "Tela.verificar (console.error, pageerror, respostas >= 400 não declaradas)")
    for nome, valor in tela.medidas.items():
        gravar(nome, valor, "ms", "goto até body[data-pronto=1] no chromium do playwright")
