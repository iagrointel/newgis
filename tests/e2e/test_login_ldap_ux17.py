"""e2e do item UX-17-login-sem-controle: as rotas POST /api/login/ldap, PUT /api/org/ldap e POST /api/org/ldap/importar
ganham controle em tela, com os quatro estados do sistema de design (UX-01):
1. /admin/organizacao, seção Diretório: carregando → conteúdo (vazio = "nenhum diretório configurado" com o
   formulário para preencher); erro forjado (500) com "tentar de novo" e referência; negado forjado (403) vira
   estado negado; 422 REAL (perfil fora do vocabulário) nomeado no campo; configuração REAL gravada contra o
   glauth de teste (tests/ldap_fixture) e resumo "habilitado";
2. importar grupo REAL (gg-plataforma-leitura: 1 encontrado) com resultado nomeado; 409 forjado (sem configuração)
   e 503 forjado (diretório indisponível) nomeados no formulário; 403 forjado vira negado;
3. /entrar: com o LDAP habilitado aparece "entrar com o diretório (LDAP)"; alternar muda o botão e a linha de
   ajuda; login REAL de ana.silva pela rede entra e cai na tela inicial; senha errada = 401 nomeado no campo;
   503 forjado (ldap_indisponivel) nomeado; sem o LDAP habilitado o controle não aparece;
4. axe 0 violações sérias nas duas telas; 0 erro de console; capturas 390/1280; medidas em
   tests/medidas/UX-17-login-sem-controle.json.
Exige Docker (glauth); sem ele a suíte é pulada com a razão."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.e2e.apoio import CAPTURAS, Tela
from tests.e2e.apoio_axe import resumo, serias

ITEM = "UX-17-login-sem-controle"
LARGURAS = (390, 1280)
pytestmark = [pytest.mark.lento, pytest.mark.e2e]
DIR_LDAP = Path(__file__).resolve().parents[1] / "ldap_fixture"
BASE_DN = "dc=plataforma-teste,dc=local"
BIND_DN = f"cn=svc-plataforma,ou=gg-servico,{BASE_DN}"
BIND_SENHA = "Servico-ldap-0"
GRUPO_LEITURA = f"ou=gg-plataforma-leitura,ou=groups,{BASE_DN}"
USUARIA, SENHA_USUARIA = "ana.silva", "Teste-ldap-1"


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


@pytest.fixture(scope="module")
def glauth():
    if not shutil.which("docker"):
        pytest.skip("docker ausente nesta máquina (glauth do tests/ldap_fixture)")
    r = subprocess.run(["bash", str(DIR_LDAP / "subir.sh")], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"glauth não subiu: {r.stderr[-300:]}")
    yield {"url": "ldap://127.0.0.1:3893", "base_dn": BASE_DN}


@pytest.fixture
def ldap_limpo(admin_api, glauth):
    """Começa sem provedor habilitado e sem a usuária importada; ao fim desliga o provedor e apaga a usuária."""
    admin_api.put("/api/org/ldap", data={"habilitado": False, "mapa_grupo_perfil": {}})

    def apagar_usuaria():
        r = admin_api.get("/api/usuarios?limite=200")
        for u in (r.json().get("itens") or []) if r.status == 200 else []:
            if u.get("login") in (USUARIA, "carla.dias"):
                admin_api.delete(f"/api/usuarios/{u['id']}")

    apagar_usuaria()
    yield glauth
    admin_api.put("/api/org/ldap", data={"habilitado": False, "mapa_grupo_perfil": {}})
    apagar_usuaria()


def _preencher(page, form, valores):
    for nome, valor in valores.items():
        alvo = page.locator(f"{form} [name='{nome}']")
        tipo = alvo.get_attribute("type")
        if tipo == "checkbox":
            if alvo.is_checked() != bool(valor):
                alvo.click()
        elif alvo.evaluate("e => e.tagName") == "SELECT":
            alvo.select_option(str(valor))
        else:
            alvo.fill(str(valor))


def test_secao_diretorio_estados_configuracao_e_importacao_reais(page, base_url, credenciais_demo, ldap_limpo, medida):
    slug, login, senha = credenciais_demo
    tela = Tela(page, base_url)
    axe: dict = {}
    tela.entrar(slug, login, senha, proximo="/admin/organizacao")
    # estado negado (403 forjado no GET) e erro (500 forjado) antes do conteúdo
    tela.esperar_status(403, 500)
    parar = _forjar(page, "**/api/org/ldap", "GET", 403, {"erro": "sem_privilegio", "mensagem": "sem org.integracoes"})
    tela.ir("/admin/organizacao")
    page.wait_for_selector("#ldap-estado[tipo='negado']", timeout=10000)
    assert "integrações" in page.text_content("#ldap-estado")
    assert page.is_hidden("#form-ldap-importar")
    _capturar(page, "negado", (1280,))
    parar()
    parar = _forjar(page, "**/api/org/ldap", "GET", 500, {"erro": "interno", "mensagem": "falhou", "req_id": "abc123"})
    tela.ir("/admin/organizacao")
    page.wait_for_selector("#ldap-estado[tipo='erro']", timeout=10000)
    assert "abc123" in page.text_content("#ldap-estado")
    parar()
    page.locator("#ldap-estado button", has_text="tentar de novo").click()  # tentar de novo -> conteúdo
    page.wait_for_selector("#form-ldap:not([hidden])", timeout=10000)
    # vazio: nenhum provedor -> texto de vazio e formulário com padrões
    resumo_txt = page.text_content("#ldap-resumo")
    assert page.get_attribute("#ldap-resumo", "data-estado") in ("vazio", "desabilitado"), resumo_txt
    _axe(page, "organizacao", axe)
    _capturar(page, "organizacao")
    # 422 REAL: mapa com perfil fora do vocabulário é recusado no campo, nada gravado
    _preencher(page, "#form-ldap", {"mapa": "gg-x = chefe"})
    page.click("#form-ldap button[type='submit']")
    page.wait_for_selector("#form-ldap [name='mapa'][aria-invalid='true']", timeout=5000)
    # configuração REAL contra o glauth
    _preencher(page, "#form-ldap", {
        "habilitado": True, "url": ldap_limpo["url"], "base_dn": ldap_limpo["base_dn"], "start_tls": False,
        "bind_dn": BIND_DN, "bind_senha": BIND_SENHA, "filtro_usuario": "(cn={login})", "atributo_grupos": "memberOf",
        "perfil_padrao": "",
        "mapa": "gg-plataforma-admin = admin\ngg-plataforma-editor = editor\ngg-plataforma-leitura = visualizador",
    })
    t0 = time.perf_counter()
    page.click("#form-ldap button[type='submit']")
    page.wait_for_selector("#ldap-resumo[data-estado='habilitado']", timeout=10000)
    salvar_ms = round((time.perf_counter() - t0) * 1000, 1)
    assert "habilitado" in page.text_content("#ldap-resumo")
    assert tela.api("GET", "/api/org/ldap").json()["habilitado"] is True
    # importar grupo REAL: gg-plataforma-leitura tem 1 membro (carla.dias)
    _preencher(page, "#form-ldap-importar", {"grupo_dn": GRUPO_LEITURA, "atributo_membro": "memberOf",
                                             "atributo_login": "cn", "perfil": "visualizador"})
    page.click("#form-ldap-importar button[type='submit']")
    page.wait_for_function(
        "() => (document.querySelector('#form-ldap-importar')?.textContent || '').includes('encontrado')", timeout=15000
    )
    texto = page.text_content("#form-ldap-importar")
    assert "1 encontrado" in texto and ("1 criado" in texto or "1 já existia" in texto), texto
    _capturar(page, "importado", (1280,))
    # erros forjados no importar, nomeados no formulário
    forjados = ((409, "ldap_sem_configuracao", "configure e habilite"), (503, "ldap_indisponivel", "não respondeu"),
                (403, "sem_privilegio", "privilégio de integrações"))
    for status, erro, trecho in forjados:
        tela.esperar_status(status)
        corpo_erro = {"erro": erro, "mensagem": f"forjado {status}"}
        parar = _forjar(page, "**/api/org/ldap/importar", "POST", status, corpo_erro)
        page.click("#form-ldap-importar button[type='submit']")
        page.wait_for_function(
            "(tr) => (document.querySelector('#form-ldap-importar')?.textContent || '').includes(tr)",
            arg=trecho, timeout=5000,
        )
        parar()
    _axe(page, "organizacao_configurada", axe)
    tela.verificar()
    m = medida(ITEM)
    m("gravar_ldap_ms", salvar_ms, "ms", "PUT /api/org/ldap pela tela até o resumo 'habilitado'")
    for k, v in axe.items():
        m(f"axe_serias_{k}", v, "violacoes", "axe-core 4.10.3 wcag2a/aa/21a/21aa, impactos serious+critical")


def test_entrar_pelo_diretorio_real_e_erros_nomeados(page, base_url, credenciais_demo, ldap_limpo, admin_api, medida):
    slug, login, senha = credenciais_demo
    # sem LDAP habilitado: o controle NÃO aparece
    tela = Tela(page, base_url)
    tela.ir(f"/entrar?inquilino={slug}")
    assert page.locator("#modo-ldap").count() == 0
    # habilita pela API (a tela de configuração é o teste anterior)
    r = admin_api.put("/api/org/ldap", data={
        "habilitado": True, "url": ldap_limpo["url"], "base_dn": ldap_limpo["base_dn"], "start_tls": False,
        "bind_dn": BIND_DN, "bind_senha": BIND_SENHA, "filtro_usuario": "(cn={login})", "atributo_grupos": "memberOf",
        "mapa_grupo_perfil": {"gg-plataforma-admin": "admin", "gg-plataforma-editor": "editor",
                              "gg-plataforma-leitura": "visualizador"},
    })
    assert r.status == 200, r.text()
    axe: dict = {}
    tela.ir(f"/entrar?inquilino={slug}")
    page.wait_for_selector("#modo-ldap", timeout=10000)
    assert page.get_attribute("#modo-ldap", "aria-pressed") == "false" and page.is_hidden("#modo-ldap-ativo")
    page.click("#modo-ldap")
    assert page.get_attribute("#modo-ldap", "aria-pressed") == "true" and page.is_visible("#modo-ldap-ativo")
    assert page.text_content("#entrar").strip() == "Entrar pelo diretório"
    _axe(page, "entrar_ldap", axe)
    _capturar(page, "entrar_ldap")
    # 503 forjado: mensagem nomeada, nunca 503 cru
    tela.esperar_status(503, 401)
    parar = _forjar(page, "**/api/login/ldap", "POST", 503, {"erro": "ldap_indisponivel", "mensagem": "não conectou"})
    page.fill("#login", USUARIA)
    page.fill("#senha", "qualquer")
    page.click("#entrar")
    page.wait_for_function(
        "() => (document.getElementById('aviso')?.textContent || '').includes('não respondeu')", timeout=5000
    )
    parar()
    # senha errada REAL no diretório: 401 nomeado no campo
    page.fill("#senha", "errada-mesmo")
    page.click("#entrar")
    page.wait_for_selector("#senha[aria-invalid='true']", timeout=10000)
    # login REAL pela rede: entra e sai de /entrar
    t0 = time.perf_counter()
    page.fill("#senha", SENHA_USUARIA)
    page.click("#entrar")
    page.wait_for_url(lambda u: "/entrar" not in u, timeout=20000)
    page.wait_for_selector("body[data-pronto='1']", timeout=20000)
    login_ms = round((time.perf_counter() - t0) * 1000, 1)
    eu = tela.api("GET", "/api/eu").json()
    assert eu["login"] == USUARIA and eu["perfil"] == "admin"  # ana.silva está em gg-plataforma-admin
    tela.verificar()
    m = medida(ITEM)
    m("login_ldap_ms", login_ms, "ms",
      "POST /api/login/ldap pela tela /entrar até a tela inicial pronta (glauth local)")
    for k, v in axe.items():
        m(f"axe_serias_{k}", v, "violacoes", "axe-core 4.10.3 wcag2a/aa/21a/21aa, impactos serious+critical")
