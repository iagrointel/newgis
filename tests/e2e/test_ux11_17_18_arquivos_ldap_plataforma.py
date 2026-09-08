"""e2e dos itens UX-11-arquivos-sem-controle, UX-17-login-sem-controle e UX-18-plataforma-sem-tela (mesma
trilha, wt/cx3ux11): as últimas rotas de escrita da cobertura que eram da trilha de interface.

UX-11 (/admin/organizacao, seção "Arquivos e objetos"): uso × cota (GET /api/arquivos), varredura de órfãos,
  envio de arquivo (token de serviço criado e REVOGADO em volta do POST /api/arquivos cru), baixar (GET) e apagar
  (DELETE) com confirmação; refutação: classe inválida recusada no navegador; bytes que não batem com o tipo
  declarado = 415 conteudo_recusado nomeado.
UX-17 (/entrar): o provedor LDAP do inquilino aparece como controle quando habilitado; o botão alterna para
  POST /api/login/ldap com os mesmos campos; diretório fora do ar = 503 nomeado com o caminho de volta ao login
  local, que continua funcionando; 403 login_ldap_desabilitado (interceptado) desliga o modo e explica.
UX-18 (/plataforma): só o superadmin do inquilino plataforma vê a lista; criar inquilino mostra a senha
  temporária uma vez; suspender/reativar/apagar com confirmação; refutação: slug inválido no navegador, slug
  repetido = 409 no campo; sessão comum vê "sem permissão" e a barra lateral sem a entrada.
Capturas 390/1280; axe 0 sérias; console limpo; sem chave crua."""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.e2e.apoio import CAPTURAS, RAIZ, Tela, sufixo, totp
from tests.e2e.apoio_axe import resumo, serias
from tests.e2e.test_i18n_cru import _cruas, _texto

pytestmark = [pytest.mark.lento, pytest.mark.e2e]

COOKIE = "plat_sessao"


def _capturar(page, item, nome, larguras=(390, 1280)):
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for largura in larguras:
        page.set_viewport_size({"width": largura, "height": 844 if largura < 500 else 900})
        page.screenshot(path=str(CAPTURAS / f"{item}_{nome}_{largura}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 800})


def _axe(page, onde):
    page.mouse.move(0, 0)  # o axe mede a cor com o estado de hover do último clique; a verificação é da tela em repouso
    graves = serias(page)
    assert graves == [], f"{onde}:\n{resumo(graves)}\n{json.dumps(graves, ensure_ascii=False)[:1500]}"


def _sem_chave_crua(page, extras=frozenset()):
    dic = json.loads((RAIZ / "web" / "js" / "i18n" / "pt-BR.json").read_text(encoding="utf-8"))
    cruas = _cruas(_texto(page), set(dic), {k.split(".")[0] for k in dic}, set(extras))
    assert cruas == [], cruas


def _lista(json_):
    return json_ if isinstance(json_, list) else (json_ or {}).get("itens", [])


def _erro_json(status, erro, mensagem, detalhe=None, req_id="e2e-ux1x-ref"):
    corpo = {"erro": erro, "mensagem": mensagem, "req_id": req_id}
    if detalhe is not None:
        corpo["detalhe"] = detalhe
    return {"status": status, "content_type": "application/json", "body": json.dumps(corpo)}


# ---------------------------------------------------------------- UX-11 arquivos


def test_ux11_arquivos_uso_varredura_envio_baixar_apagar_e_recusas(page, base_url, credenciais_demo, api_auth):
    if "/api/arquivos/{sha256}" not in api_auth:
        pytest.skip("backend sem /api/arquivos no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/admin/organizacao")
    page.wait_for_function(
        "() => !(document.querySelector('#arquivos-uso-texto').textContent || '').includes('…')", timeout=15000,
    )
    assert "MB" in (page.text_content("#arquivos-uso-texto") or "")
    assert page.locator("#arquivo-enviar").is_disabled()
    # varredura de órfãos: números, nunca tela em branco
    page.click("#arquivos-varrer")
    page.wait_for_function(
        "() => (document.querySelector('#arquivos-varredura').textContent || '').length > 0", timeout=30000,
    )
    assert "objetos" in (page.text_content("#arquivos-varredura") or "")
    # refutação: classe inválida é recusada no navegador, sem chamada
    chamadas = []
    page.on("request", lambda r: chamadas.append(r.url) if r.method == "POST" and "/api/arquivos" in r.url else 0)
    s = sufixo()
    page.set_input_files(
        "#arquivo-envio", {"name": f"nota-{s}.txt", "mimeType": "text/plain", "buffer": f"plat e2e {s}\n".encode()},
    )
    page.fill("#arquivo-classe", "Classe Ruim")
    page.click("#arquivo-enviar")
    page.wait_for_selector("#arquivos-estado[tipo='erro']:not([hidden])")
    assert chamadas == []
    # envio real: token cunhado, arquivo guardado, token revogado; linha com baixar e apagar
    page.fill("#arquivo-classe", "objeto")
    antes = {t["id"] for t in _lista(tela.api("GET", "/api/tokens").json())}
    page.click("#arquivo-enviar")
    page.wait_for_selector("#arquivos-corpo tr[data-sha256]", timeout=30000)
    sha = page.get_attribute("#arquivos-corpo tr", "data-sha256")
    assert sha and len(sha) == 64
    tokens = _lista(tela.api("GET", "/api/tokens").json())
    novos = [t for t in tokens if t["id"] not in antes]
    assert novos and all(t.get("revogado_em") for t in novos), novos  # o token do envio não sobrevive ao envio
    r = tela.api("GET", f"/api/arquivos/{sha}?classe=objeto")
    assert r.status == 200 and f"plat e2e {s}" in r.text(), r.status
    _axe(page, "arquivos com linha")
    _sem_chave_crua(page)
    _capturar(page, "UX-11", "arquivos_enviado")
    # 415: bytes de texto declarados como imagem (o servidor varre o conteúdo) — nomeado, com referência
    tela.esperar_status(415)
    page.set_input_files("#arquivo-envio", {"name": "falso.png", "mimeType": "image/png", "buffer": b"isto nao e png"})
    page.click("#arquivo-enviar")
    page.wait_for_selector("#arquivos-estado[tipo='erro']:not([hidden])", timeout=30000)
    assert "recusado" in (page.text_content("#arquivos-estado") or "")
    _capturar(page, "UX-11", "arquivo_recusado", larguras=(1280,))
    # apagar com confirmação → GET vira 404
    page.click(f"#arquivos-corpo tr[data-sha256='{sha}'] button[data-apagar]")
    page.wait_for_selector("plat-dialogo:not([hidden]) button.perigo", timeout=5000)
    page.click("plat-dialogo button.perigo")
    page.wait_for_function(
        "(sha) => !document.querySelector(`#arquivos-corpo tr[data-sha256='${sha}']`)", arg=sha, timeout=15000,
    )
    tela.esperar_status(404)
    assert tela.api("GET", f"/api/arquivos/{sha}?classe=objeto").status == 404
    tela.verificar()


# ---------------------------------------------------------------- UX-17 login por LDAP


def test_ux17_login_ldap_controle_erro_nomeado_e_volta_ao_local(page, base_url, credenciais_demo, api_auth):
    if "/api/login/ldap" not in api_auth:
        pytest.skip("backend sem /api/login/ldap no OpenAPI")
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    anterior = tela.api("GET", "/api/org/ldap")
    if anterior.status == 403:
        pytest.skip("sessão sem org.integracoes para habilitar o LDAP")
    corpo = {"habilitado": True, "url": "ldap://127.0.0.1:1", "base_dn": "dc=e2e,dc=local", "start_tls": False,
             "filtro_usuario": "(uid={login})", "atributo_grupos": "memberOf", "perfil_padrao": "visualizador"}
    assert tela.api("PUT", "/api/org/ldap", corpo).status == 200
    try:
        tela.sair()
        page.goto(f"/entrar?inquilino={slug}", wait_until="domcontentloaded")
        page.wait_for_selector("#entrar-ldap", timeout=15000)
        assert page.get_attribute("#entrar-ldap", "aria-pressed") == "false"
        assert page.locator("#ldap-dica").is_hidden()
        page.click("#entrar-ldap")
        assert page.get_attribute("#entrar-ldap", "aria-pressed") == "true"
        assert page.locator("#ldap-dica").is_visible()
        _axe(page, "entrada com LDAP")
        _sem_chave_crua(page)
        _capturar(page, "UX-17", "entrar_ldap")
        # diretório fora do ar (porta 1): 503 nomeado, o formulário local segue disponível
        tela.esperar_status(503)
        page.fill("#login", "alguem")
        page.fill("#senha", "segredo")
        page.click("#entrar")
        page.wait_for_function(
            "() => (document.querySelector('#aviso').textContent || '').includes('diretório')", timeout=30000,
        )
        assert page.locator("#form-senha").is_visible()
        _capturar(page, "UX-17", "ldap_indisponivel", larguras=(1280,))
        # 403 login_ldap_desabilitado (interceptado): o modo desliga sozinho e explica
        page.route(
            "**/api/login/ldap", lambda r: r.fulfill(**_erro_json(403, "login_ldap_desabilitado", "desabilitado")),
        )
        tela.esperar_status(403)
        page.click("#entrar")
        page.wait_for_function(
            "() => document.querySelector('#entrar-ldap').getAttribute('aria-pressed') === 'false'", timeout=10000,
        )
        assert "habilitado" in (page.text_content("#aviso") or "")
        page.unroute("**/api/login/ldap")
        # volta ao local: entra com a senha de verdade
        page.fill("#login", login)
        page.fill("#senha", senha)
        page.click("#entrar")
        page.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
        page.wait_for_selector("body[data-pronto='1']", timeout=20000)
        tela.verificar()
    finally:
        # sessão recém-aberta (ou reaberta pela API) desliga o LDAP do inquilino demo
        if tela.api("GET", "/api/eu").status != 200:
            page.request.post(f"{base_url}/api/login", data={"inquilino": slug, "login": login, "senha": senha})
        tela.api("PUT", "/api/org/ldap", {**corpo, "habilitado": False})


# ---------------------------------------------------------------- UX-18 plataforma


@pytest.fixture
def cookie_superadmin():
    """sessão do superadmin (inquilino plataforma) criada direto no banco da trilha; o 2FA obrigatório é ligado
    pela API na primeira vez e o segredo vai para o arquivo de TOTP da trilha (o mesmo que tests/api usa)."""
    dsn = os.environ.get("PLAT_DSN")
    if not dsn:
        pytest.skip("sem PLAT_DSN no ambiente (rode com o .env da trilha carregado)")
    from tests import jobs_sessao

    con = jobs_sessao.conectar(dsn)
    try:
        token, _, _ = jobs_sessao.criar_sessao(con, "plataforma", "admin")
    except AssertionError as e:
        pytest.skip(str(e))
    finally:
        con.close()
    return token


def _guardar_totp(slug, login, segredo):
    caminho = Path(os.environ.get("PLAT_CREDENCIAIS_TOTP_ARQUIVO") or (RAIZ / "tests" / "credenciais_totp.txt"))
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    linhas = [li for li in linhas if not li.startswith(slug + " ")]
    linhas.append(f"{slug} {login} {segredo}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    caminho.chmod(0o600)


def _cookie(page, base_url, valor):
    u = urlparse(base_url)
    page.context.add_cookies([{"name": COOKIE, "value": valor, "domain": u.hostname, "path": "/",
                               "httpOnly": True, "secure": u.scheme == "https", "sameSite": "Lax"}])


def test_ux18_plataforma_lista_cria_suspende_reativa_apaga(page, base_url, cookie_superadmin, api_auth):
    if "/api/plataforma/inquilinos" not in api_auth:
        pytest.skip("backend sem /api/plataforma/inquilinos no OpenAPI")
    _cookie(page, base_url, cookie_superadmin)
    tela = Tela(page, base_url)
    eu = tela.api("GET", "/api/eu")
    assert eu.status == 200, eu.status
    if "configurar_2fa" in (eu.json().get("pendencias") or []):
        r = tela.api("POST", "/api/eu/2fa/iniciar", {})
        assert r.status == 200, r.text()
        segredo = r.json()["segredo"]
        r = tela.api("POST", "/api/eu/2fa/confirmar", {"codigo": totp(segredo)})
        assert r.status == 200, r.text()
        _guardar_totp("plataforma", "admin", segredo)
    tela.ir("/plataforma")
    page.wait_for_selector("#inquilinos-tabela tbody tr", timeout=15000)
    assert page.locator("#lateral nav a[href='/plataforma']").count() == 1
    assert page.locator("#inquilinos-tabela tbody tr", has_text="plataforma").locator("button").count() == 0
    _axe(page, "plataforma lista")
    _sem_chave_crua(page)
    _capturar(page, "UX-18", "plataforma_lista")
    # refutação: slug inválido é recusado no navegador
    s = sufixo()
    page.fill("#form-novo input[name='slug']", "AB")
    page.fill("#form-novo input[name='nome']", f"Inquilino e2e {s}")
    page.fill("#form-novo input[name='admin_login']", "admin")
    page.fill("#form-novo input[name='admin_nome']", "Administrador e2e")
    page.click("#form-novo button[type=submit]")
    page.wait_for_selector("#form-novo input[name='slug'][aria-invalid='true']")
    # criação real: senha temporária uma vez, linha nova na lista
    slug = f"zt-ux18-{s}"
    page.fill("#form-novo input[name='slug']", slug)
    page.click("#form-novo button[type=submit]")
    page.wait_for_selector("#criado:not([hidden])", timeout=30000)
    assert len(page.text_content("#criado-senha") or "") >= 8
    assert (page.get_attribute("#criado-entrar", "href") or "").endswith(f"inquilino={slug}")
    linha = page.locator("#inquilinos-tabela tbody tr", has_text=slug)
    linha.wait_for(timeout=15000)
    _capturar(page, "UX-18", "plataforma_criado")
    try:
        # slug repetido: 409 no campo
        page.fill("#form-novo input[name='slug']", slug)
        page.fill("#form-novo input[name='nome']", "repetido")
        page.fill("#form-novo input[name='admin_login']", "admin")
        page.fill("#form-novo input[name='admin_nome']", "x")
        tela.esperar_status(409)
        page.click("#form-novo button[type=submit]")
        page.wait_for_selector("#form-novo input[name='slug'][aria-invalid='true']")
        # suspender → reativar
        linha.locator("button", has_text="suspender").click()
        page.wait_for_selector("plat-dialogo:not([hidden]) button.perigo", timeout=5000)
        page.click("plat-dialogo button.perigo")
        page.wait_for_function(
            "(s) => [...document.querySelectorAll('#inquilinos-tabela tbody tr')]"
            ".some(tr => tr.textContent.includes(s) && tr.textContent.includes('suspenso'))",
            arg=slug, timeout=15000,
        )
        page.locator("#inquilinos-tabela tbody tr", has_text=slug).locator("button", has_text="reativar").click()
        page.wait_for_function(
            "(s) => [...document.querySelectorAll('#inquilinos-tabela tbody tr')].some(tr => tr.textContent.includes(s)"
            " && tr.textContent.includes('ativo') && !tr.textContent.includes('suspenso'))",
            arg=slug, timeout=15000,
        )
        _axe(page, "plataforma com inquilino novo")
    finally:
        # apagar com confirmação (é também a limpeza)
        page.locator("#inquilinos-tabela tbody tr", has_text=slug).locator("button", has_text="Apagar").click()
        page.wait_for_selector("plat-dialogo:not([hidden]) button.perigo", timeout=5000)
        page.click("plat-dialogo button.perigo")
        page.wait_for_function(
            "(s) => ![...document.querySelectorAll('#inquilinos-tabela tbody tr')]"
            ".some(tr => tr.textContent.includes(s))",
            arg=slug, timeout=30000,
        )
    tela.verificar()


def test_ux18_sessao_comum_ve_sem_permissao(page, base_url, credenciais_demo):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    tela.entrar(slug, login, senha)
    tela.ir("/plataforma")
    page.wait_for_selector("#estado[tipo='negado']:not([hidden])", timeout=15000)
    assert page.locator("#corpo").is_hidden()
    assert page.locator("#lateral nav a[href='/plataforma']").count() == 0
    _axe(page, "plataforma negado")
    _capturar(page, "UX-18", "plataforma_negado", larguras=(1280,))
    tela.verificar()
