"""e2e do item UX-06-tela-administracao-inquilino. Sobre as suítes já existentes das telas de admin (test_usuarios,
test_papeis, test_grupos, test_tokens, test_log_acesso), este arquivo prova o que o item acrescenta:

1. /admin: hub com um cartão por assunto (número lido da rota que já existe), eventos recentes, captura 390/1280, axe,
   nenhuma chave crua; a entrada "Administração" está na barra lateral;
2. refutação: perfil visualizador vê 403 amigável em /admin (estado "sem permissão" com o caminho de volta) e em
   /admin/usuarios e /admin/acervo (página "sem permissão" do exigirSessao), nunca tela quebrada, 0 erro de console
   além do 403 esperado;
3. /admin/acervo (fecha UX-10): lista com busca, ficha de procedência, "adicionar ao catálogo" — inclusive o caminho
   LGPD (409 confirmacao_pii_exigida provocado → diálogo de confirmação → segunda chamada com confirma_risco_pii);
4. seção LDAP em /admin/organizacao: GET/PUT /api/org/ldap pela tela (provedor desabilitado com endereço válido),
   POST importar respondendo 409 nomeado; o aviso "evento registrado" aparece depois da escrita (portão do item);
5. PUT /api/papeis/{id} pela tela (editar um papel) e a ficha do membro (GET /api/usuarios/{id});
6. estados explícitos: usuários vazio com "limpar filtros", tokens em erro (rota derrubada pela página), log aberto por
   link profundo já na aba de eventos com o tipo preenchido."""

import json
import os
import re
from urllib.parse import urlparse

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

ITEM = "UX-06"
LARGURAS = (390, 1280)
COOKIE = "plat_sessao"
ROTA_TOKENS = re.compile(r".*/api/tokens(\?.*)?$")
# um <plat-estado> deixou de estar em "carregando" (ou não existe / está escondido)
ESTADO_PRONTO = (
    "(sel) => { const e = document.querySelector(sel); "
    "return !e || e.hidden || e.getAttribute('tipo') !== 'carregando'; }"
)


def _capturar(page, nome, larguras=LARGURAS):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{ITEM}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def _privilegios(tela):
    r = tela.api("GET", "/api/privilegios")
    return {p["nome"] for p in r.json()} if r.status == 200 else set()


def _erro_json(status, mensagem, erro="provocado", detalhe=None, req_id="e2e-ux06-ref"):
    corpo = {"erro": erro, "mensagem": mensagem, "req_id": req_id}
    if detalhe is not None:
        corpo["detalhe"] = detalhe
    return {
        "status": status,
        "content_type": "application/json",
        "body": json.dumps(corpo),
        "headers": {"X-Req-Id": req_id},
    }


# ---------------------------------------------------------------- 1. hub


def test_admin_hub_cartoes_eventos_axe_e_capturas(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/admin")
    tela.ir("/admin")
    privilegios = _privilegios(tela)
    assert page.locator("#lateral nav a[href='/admin']").count() == 1
    assert page.locator("#lateral nav a[href='/admin'][aria-current='page']").count() == 1
    page.wait_for_selector("#resumo:not([hidden]) .admin-cartao", timeout=15000)
    cartoes = page.eval_on_selector_all("#resumo .admin-cartao", "els => els.map(e => e.id.replace('cartao-', ''))")
    for esperado in ("usuarios", "grupos", "papeis", "tokens", "armazenamento", "cota-usuarios", "log", "acervo"):
        assert esperado in cartoes, (esperado, cartoes)
    # cada cartão tem número (nunca fica em branco) e um caminho de tela
    for c in cartoes:
        numero = (page.text_content(f"#cartao-{c} .admin-cartao-numero") or "").strip()
        assert numero and numero != "—", (c, numero)
        assert page.get_attribute(f"#cartao-{c}", "href", timeout=1000).startswith("/admin")
    assert page.locator("#resumo .admin-cartao.erro").count() == 0, page.locator(
        "#resumo .admin-cartao.erro"
    ).all_inner_texts()
    page.wait_for_selector("#eventos:not([hidden])")
    page.wait_for_function(ESTADO_PRONTO, arg="#eventos-estado")
    _axe(page, "hub")
    _sem_chave_crua(page, privilegios)
    _capturar(page, "hub")
    # a página inicial lista o atalho da administração com a descrição
    tela.ir("/")
    assert page.locator("#atalhos a[href='/admin']").count() == 1
    tela.verificar()


# ---------------------------------------------------------------- 2. refutação: visualizador


@pytest.fixture
def cookie_visualizador(credenciais_demo):
    """sessão de um visualizador temporário criada direto no banco da trilha (tests/jobs_sessao.py), como em
    test_tarefas; sem PLAT_DSN no ambiente o teste é pulado com a razão escrita."""
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN no ambiente (rode com o .env da trilha carregado)")
    from tests import jobs_sessao

    con = jobs_sessao.conectar(dsn)
    login = f"zt-ux06-vis-{sufixo()}"
    try:
        _, tenant_id, admin_id = jobs_sessao.criar_sessao(con)
        uid = jobs_sessao.criar_usuario_temporario(con, tenant_id, admin_id, login, "visualizador")
        token = jobs_sessao.sessao_de_usuario(con, tenant_id, uid, login)
        con.commit()
        yield token
    finally:
        try:
            jobs_sessao.apagar_usuario_temporario(con, tenant_id, admin_id, login)
            con.commit()
        finally:
            con.close()


def test_visualizador_ve_403_amigavel_nunca_tela_quebrada(page, base_url, cookie_visualizador):
    u = urlparse(base_url)
    page.context.add_cookies(
        [
            {
                "name": COOKIE,
                "value": cookie_visualizador,
                "domain": u.hostname,
                "path": "/",
                "httpOnly": True,
                "secure": u.scheme == "https",
                "sameSite": "Lax",
            }
        ]
    )
    tela = Tela(page, base_url)
    tela.esperar_status(403)
    tela.ir("/admin")
    page.wait_for_selector("#estado[tipo='negado']:not([hidden])")
    assert page.locator("#resumo").is_hidden()
    assert page.locator("#estado button").count() == 2
    assert "privilégio" in (page.text_content("#estado") or "")
    # a barra lateral não oferece a administração a quem não a tem
    assert page.locator("#lateral nav a[href='/admin']").count() == 0
    _axe(page, "admin negado")
    _capturar(page, "admin_negado")
    for caminho in ("/admin/usuarios", "/admin/acervo", "/admin/organizacao"):
        tela.ir(caminho)
        page.wait_for_selector("main.sem-permissao")
        assert page.locator("main.sem-permissao a[href='/']").count() == 1
        assert page.locator("plat-aviso[data-tipo='atencao']").count() == 1
    _capturar(page, "usuarios_negado", larguras=(1280,))
    tela.verificar()


# ---------------------------------------------------------------- 3. acervo


def test_acervo_lista_ficha_e_adicionar_com_confirmacao_lgpd(page, base_url, credenciais_demo, api_auth):
    if "/api/acervo" not in api_auth:
        pytest.skip("backend sem /api/acervo no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    criados = []
    try:
        tela.entrar(slug, login, senha, proximo="/admin/acervo")
        tela.ir("/admin/acervo")
        page.wait_for_function(ESTADO_PRONTO, arg="#estado", timeout=15000)
        r = tela.api("GET", "/api/acervo?limite=1")
        assert r.status == 200, r.text()
        total = r.json()["total"]
        if total == 0:
            page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
            _capturar(page, "acervo_vazio", larguras=(1280,))
            tela.verificar()
            return
        page.wait_for_selector("#tabela tbody tr", timeout=15000)
        assert page.locator("#tabela tbody tr").count() >= 1
        _axe(page, "acervo lista")
        _sem_chave_crua(page, _privilegios(tela))
        _capturar(page, "acervo_lista")
        # busca sem resultado -> estado com limpar filtros
        page.fill("#filtros plat-busca input", "zt-nada-corresponde-ux06")
        page.press("#filtros plat-busca input", "Enter")
        page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
        page.locator("#estado button", has_text="limpar filtros").click()
        page.wait_for_selector("#tabela tbody tr", timeout=15000)
        # ficha
        primeira = page.locator("#tabela tbody tr").first
        nome = primeira.locator("td").first.inner_text().split("·")[0].strip()
        primeira.locator("button", has_text="ficha").click()
        painel = page.locator("#painel dialog[open]")
        painel.wait_for()
        painel.locator(".ficha-acervo").wait_for(timeout=15000)
        assert nome in painel.inner_text()
        assert "licença" in painel.inner_text()
        _axe(page, "ficha")
        _capturar(page, "acervo_ficha", larguras=(1280,))
        painel.locator(".dialogo-botoes button").click()
        painel.wait_for(state="hidden")
        # adicionar com o caminho LGPD: a primeira chamada é interceptada com 409, a confirmação repete de verdade
        chamadas = []

        def intercepta(route):
            corpo = route.request.post_data or ""
            chamadas.append(corpo)
            if "confirma_risco_pii" in corpo:
                route.continue_()
            else:
                route.fulfill(
                    **_erro_json(
                        409,
                        "fonte com risco de dado pessoal (provocado)",
                        "confirmacao_pii_exigida",
                        {"risco_pii_motivo": "contém CPF em coluna livre"},
                    )
                )

        tela.esperar_status(409)
        page.route("**/api/acervo/*/adicionar", intercepta)
        page.locator("#tabela tbody tr").first.locator("button", has_text="adicionar ao catálogo").click()
        dialogo = page.locator("plat-dialogo dialog[open]")
        dialogo.wait_for()
        assert "CPF" in dialogo.inner_text()
        _capturar(page, "acervo_lgpd_confirma", larguras=(1280,))
        dialogo.locator(".dialogo-botoes button.perigo").click()
        page.wait_for_function(
            "() => document.querySelector('#aviso')?.textContent?.includes('item criado')", timeout=20000
        )
        page.unroute("**/api/acervo/*/adicionar")
        assert len(chamadas) == 2 and "confirma_risco_pii" in chamadas[1], chamadas
        href = page.get_attribute("#aviso a", "href")
        criados.append(href.rsplit("/", 1)[-1])
        assert page.locator("#evento-registrado:not([hidden])").count() == 1
        assert "acervo" in (page.text_content("#evento-registrado") or "")
        _capturar(page, "acervo_adicionado", larguras=(1280,))
        tela.verificar()
    finally:
        for iid in criados:
            tela.api("DELETE", f"/api/itens/{iid}")
        if criados:
            tela.api("POST", "/api/lixeira/esvaziar", {"ids": criados})


# ---------------------------------------------------------------- 4. LDAP


def test_ldap_salvar_importar_409_e_evento_registrado(page, base_url, credenciais_demo, api_auth):
    if "/api/org/ldap" not in api_auth:
        pytest.skip("backend sem /api/org/ldap no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    anterior = tela_get = None
    try:
        tela.entrar(slug, login, senha, proximo="/admin/organizacao")
        tela_get = tela.api("GET", "/api/org/ldap")
        anterior = tela_get.json() if tela_get.status == 200 else None
        tela.ir("/admin/organizacao#ldap")
        page.wait_for_selector("#ldap:not([hidden]) #form-ldap form", timeout=15000)
        _axe(page, "ldap")
        _capturar(page, "ldap")
        # habilitar sem endereço: erro no campo, sem chamada
        page.check("#form-ldap input[name=habilitado]")
        page.fill("#form-ldap input[name=url]", "")
        page.click("#form-ldap button[type=submit]")
        assert page.locator("#form-ldap [data-campo='url'] .erro-campo").count() == 1
        # esquema errado
        page.fill("#form-ldap input[name=url]", "http://ldap.exemplo.gov.br")
        page.click("#form-ldap button[type=submit]")
        assert page.locator("#form-ldap [data-campo='url'] .erro-campo").count() == 1
        # mapa com perfil desconhecido
        page.uncheck("#form-ldap input[name=habilitado]")
        page.fill("#form-ldap input[name=url]", "ldaps://ldap.exemplo.gov.br:636")
        page.fill("#form-ldap textarea[name=mapa_grupo_perfil]", "cn=geo,dc=exemplo = chefe")
        page.click("#form-ldap button[type=submit]")
        assert page.locator("#form-ldap [data-campo='mapa_grupo_perfil'] .erro-campo").count() == 1
        # salvar desabilitado com endereço válido: PUT 200, aviso e evento registrado
        page.fill("#form-ldap textarea[name=mapa_grupo_perfil]", "cn=geo,ou=grupos,dc=exemplo,dc=gov,dc=br = editor")
        page.fill("#form-ldap input[name=base_dn]", "dc=exemplo,dc=gov,dc=br")
        page.click("#form-ldap button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector('#aviso')?.textContent?.includes('LDAP salvo')", timeout=15000
        )
        page.wait_for_selector("#evento-registrado:not([hidden])", timeout=10000)
        assert "org/ldap" in (page.text_content("#evento-registrado") or "")
        assert "desabilitado" in (page.text_content("#ldap-estado-texto") or "")
        _capturar(page, "ldap_salvo", larguras=(1280,))
        # importar com provedor desabilitado: 409 nomeado no formulário
        tela.esperar_status(409)
        page.fill("#form-ldap-importar input[name=grupo_dn]", "cn=geo,ou=grupos,dc=exemplo,dc=gov,dc=br")
        page.click("#form-ldap-importar button[type=submit]")
        page.wait_for_function(
            "() => document.querySelector('#form-ldap-importar plat-aviso')?.textContent?.includes('habilite')",
            timeout=15000,
        )
        _capturar(page, "ldap_importar_409", larguras=(1280,))
        tela.verificar()
    finally:
        if tela_get is not None and tela_get.status == 200:
            if anterior:
                corpo = {
                    k: anterior[k]
                    for k in (
                        "habilitado",
                        "url",
                        "base_dn",
                        "start_tls",
                        "bind_dn",
                        "filtro_usuario",
                        "atributo_grupos",
                        "perfil_padrao",
                        "mapa_grupo_perfil",
                    )
                }
            else:
                corpo = {
                    "habilitado": False,
                    "url": None,
                    "base_dn": None,
                    "start_tls": True,
                    "bind_dn": None,
                    "filtro_usuario": "(uid={login})",
                    "atributo_grupos": "memberOf",
                    "perfil_padrao": None,
                    "mapa_grupo_perfil": {},
                }
            tela.api("PUT", "/api/org/ldap", corpo)


# ---------------------------------------------------------------- 5. papéis (PUT) e ficha do membro


def test_papel_editar_put_e_ficha_do_membro(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    s = sufixo()
    tela = Tela(page, base_url)
    pid = None
    try:
        tela.entrar(slug, login, senha, proximo="/admin/papeis")
        r = tela.api(
            "POST",
            "/api/papeis",
            {"nome": f"zt-ux06-papel-{s}", "descricao": "antes", "privilegios": ["conteudo.ver_inquilino"]},
        )
        assert r.status == 201, r.text()
        pid = r.json()["id"]
        tela.ir("/admin/papeis")
        linha = page.locator("#tabela tbody tr", has_text=f"zt-ux06-papel-{s}")
        linha.wait_for(timeout=15000)
        linha.locator("button", has_text="Editar").click()
        painel = page.locator("#painel dialog[open]")
        painel.wait_for()
        painel.locator("input[name='descricao']").fill("depois (editado pela tela)")
        painel.locator("button[type='submit']").click()
        page.wait_for_selector("#aviso[data-tipo='ok']", timeout=15000)
        page.locator("#tabela tbody tr", has_text="depois (editado pela tela)").wait_for(timeout=15000)
        r = tela.api("GET", "/api/papeis")
        assert any(p["id"] == pid and p["descricao"].startswith("depois") for p in r.json()["personalizados"])
        page.wait_for_selector("#evento-registrado:not([hidden])", timeout=10000)
        _capturar(page, "papel_editado", larguras=(1280,))
        # ficha do membro (GET /api/usuarios/{id}) a partir da lista de usuários
        tela.ir("/admin/usuarios")
        page.wait_for_selector("#tabela tbody tr", timeout=15000)
        page.locator("#tabela tbody tr", has_text=login).first.locator("button", has_text="detalhes").click()
        painel = page.locator("#painel dialog[open]")
        painel.wait_for()
        painel.locator(".ficha-acervo").wait_for(timeout=15000)
        texto = painel.inner_text()
        assert login in texto and "origem da conta" in texto
        _axe(page, "ficha do membro")
        _capturar(page, "usuario_detalhes", larguras=(1280,))
        painel.locator(".dialogo-botoes button").click()
        tela.verificar()
    finally:
        if pid is not None:
            tela.api("DELETE", f"/api/papeis/{pid}")


# ---------------------------------------------------------------- 6. estados e link profundo do log


def test_estados_usuarios_tokens_e_log_link_profundo(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha, proximo="/admin/usuarios")
    tela.ir("/admin/usuarios")
    page.wait_for_selector("#tabela tbody tr", timeout=15000)
    page.fill("#filtros plat-busca input", "zt-ninguem-com-este-nome-ux06")
    page.press("#filtros plat-busca input", "Enter")
    page.wait_for_selector("#estado[tipo='vazio']:not([hidden])")
    assert page.locator("#tabela").is_hidden()
    _capturar(page, "usuarios_vazio", larguras=(1280,))
    page.locator("#estado button", has_text="limpar filtros").click()
    page.wait_for_selector("#tabela:not([hidden]) tbody tr", timeout=15000)
    assert page.input_value("#filtros plat-busca input") == ""
    # tokens: rota derrubada pela página -> estado de erro com referência e tentar de novo
    tela.esperar_status(500)
    page.route(
        ROTA_TOKENS,
        lambda r: (
            r.fulfill(**_erro_json(500, "banco indisponível (provocado)"))
            if r.request.method == "GET"
            else r.continue_()
        ),
    )
    tela.ir("/admin/tokens")
    page.wait_for_selector("#estado[tipo='erro']:not([hidden])", timeout=15000)
    assert "e2e-ux06-ref" in (page.text_content("#estado") or "")
    _capturar(page, "tokens_erro", larguras=(1280,))
    page.unroute(ROTA_TOKENS)
    page.locator("#estado button", has_text="tentar de novo").click()
    page.wait_for_function(
        "() => document.querySelector('#estado').hidden "
        "|| document.querySelector('#estado').getAttribute('tipo') === 'vazio'",
        timeout=15000,
    )
    # log: link profundo abre na aba de eventos com o tipo preenchido
    tela.ir("/admin/log?aba=eventos&tipo=org/ldap")
    assert page.get_attribute("#aba-eventos", "aria-selected") == "true"
    assert page.locator("#painel-eventos").is_visible()
    assert page.input_value("#filtros-eventos input[name=tipo]") == "org/ldap"
    page.wait_for_function(
        ESTADO_PRONTO,
        arg="#estado-eventos",
        timeout=15000,
    )
    _capturar(page, "log_eventos_link", larguras=(1280,))
    tela.verificar()
