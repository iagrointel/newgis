"""HTTP real na URL pública (nginx + TLS): noindex em toda rota, no-store nos módulos, X-Req-Id da API e
**um Cache-Control só** por resposta (correção T2 (3): o nginx acrescentava o dele ao da aplicação e saíam dois).
Exige rede; pulado só se o nome público não resolver."""

import datetime
import json
import re

import httpx
import pytest


@pytest.fixture(scope="module")
def http(base_url, url_publica_resolve):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    with httpx.Client(base_url=base_url, timeout=10, follow_redirects=False) as c:
        yield c


@pytest.mark.parametrize(
    "rota",
    [
        "/",
        "/saude",
        "/api/versao",
        "/static/app.js",
        "/static/js/core.js",
        "/static/vendor/maplibre-gl-4.7.1.js",
        "/api/docs",
        "/api/openapi.json",
    ],
)
def test_noindex_em_toda_rota(http, rota):
    r = http.get(rota)
    assert r.status_code == 200, (rota, r.status_code)
    assert r.headers.get("x-robots-tag") == "noindex, nofollow", rota


@pytest.mark.parametrize("rota", ["/static/app.js", "/static/js/core.js", "/static/style.css"])
def test_no_store_nos_modulos(http, rota):
    r = http.get(rota)
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", ""), rota
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_estatico_vem_do_nginx_sem_passar_pela_api(http):
    r = http.get("/static/app.js")
    assert r.status_code == 200
    assert "x-req-id" not in r.headers
    assert r.headers.get("content-type", "").startswith(("application/javascript", "text/javascript"))


@pytest.mark.parametrize("rota", ["/", "/saude", "/api/versao"])
def test_x_req_id_e_no_store_na_api(http, rota):
    r = http.get(rota)
    assert r.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers.get("x-req-id", "")), rota
    assert "no-store" in r.headers.get("cache-control", "")


def test_saude_publica_tem_json_do_contrato(http):
    j = http.get("/saude").json()
    assert j["banco"] == "ok" and j["migracoes_pendentes"] == 0


def test_http_redireciona_para_https(base_url, url_publica_resolve):
    if not url_publica_resolve:
        pytest.skip("sem rede")
    r = httpx.get(base_url.replace("https://", "http://") + "/saude", timeout=10, follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].startswith("https://")


@pytest.mark.parametrize(
    "rota",
    ["/", "/saude", "/api/versao", "/api/docs", "/entrar", "/static/app.js", "/api/login/provedores?inquilino=demo"],
)
def test_referrer_policy_em_toda_rota(http, rota):
    """Achado do testador do T2: o cabeçalho existia no server{} mas nenhuma location o repetia."""
    r = http.get(rota)
    assert r.status_code == 200, rota
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin", rota


def test_embutir_bloqueado_por_padrao_na_url_publica(http):
    """Item L7-03-e: quem manda no embutir passou a ser `frame-ancestors` (aceita LISTA por inquilino, e os
    navegadores atuais o aplicam com precedência sobre X-Frame-Options). O teste aceita qualquer um dos dois
    porque a instalação pública só troca de mecanismo quando o dono instalar o nginx.conf e a app deste item."""
    cabecalhos_ = http.get("/").headers
    xfo = cabecalhos_.get("x-frame-options")
    csp = cabecalhos_.get("content-security-policy", "")
    assert xfo == "DENY" or "frame-ancestors 'none'" in csp, (xfo, csp)


@pytest.mark.parametrize("rota", ["/", "/saude", "/api/versao", "/api/docs", "/static/app.js", "/static/favicon.svg"])
def test_hsts_em_toda_rota_https(http, rota):
    r = http.get(rota)
    assert r.status_code == 200, rota
    assert r.headers.get("strict-transport-security") == "max-age=31536000", rota


def test_hsts_ausente_no_bloco_http(base_url, url_publica_resolve):
    if not url_publica_resolve:
        pytest.skip("sem rede")
    r = httpx.get(base_url.replace("https://", "http://") + "/saude", timeout=10, follow_redirects=False)
    assert r.status_code == 301
    assert "strict-transport-security" not in r.headers


def test_recursos_da_documentacao_servidos_pelo_nginx(http):
    html = http.get("/api/docs").text
    for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
        r = http.get(ref)
        assert r.status_code == 200 and "x-req-id" not in r.headers, ref


# ---------------------------------------------------------------- Cache-Control com uma origem só (T2)

@pytest.mark.parametrize("rota", ["/", "/saude", "/api/versao", "/tarefas", "/entrar", "/api/openapi.json"])
def test_um_unico_cache_control_nas_rotas_da_aplicacao(http, rota):
    """A origem é a APLICAÇÃO (middleware de app/auth/middleware.py dá o piso; a rota que quiser outro valor
    declara o seu). O nginx não acrescenta o dele em location proxiada — se acrescentar, aparecem dois."""
    r = http.get(rota)
    valores = r.headers.get_list("cache-control")
    assert len(valores) == 1, (rota, valores)
    assert "no-store" in valores[0], (rota, valores)


@pytest.mark.parametrize("rota", ["/static/app.js", "/static/style.css"])
def test_um_unico_cache_control_no_estatico(http, rota):
    """Em /static/ o nginx É a origem do corpo e continua sendo a origem do cabeçalho: um só, também."""
    r = http.get(rota)
    valores = r.headers.get_list("cache-control")
    assert len(valores) == 1, (rota, valores)
    assert "no-store" in valores[0], (rota, valores)


# ------------------------------------------------------------------ item L7-03-e: conjunto completo por rota
# Esta seção NÃO usa a URL pública: ela exercita a aplicação desta árvore (TestClient), porque os cabeçalhos
# que ela prova nascem em app/cabecalhos.py e o nginx de produção só passa a repassá-los depois que o dono
# instalar o deploy/nginx.conf deste item. As rotas vêm do OpenAPI da PRÓPRIA aplicação, uma a uma.

from app import cabecalhos  # noqa: E402
from app.main import app as aplicacao  # noqa: E402
from tests.api.conftest import novo_cliente  # noqa: E402

CABECALHOS_OBRIGATORIOS = (
    "content-security-policy",
    "referrer-policy",
    "x-content-type-options",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
)
# rotas fora do OpenAPI (include_in_schema=False) que também têm de sair com o conjunto
ROTAS_SEM_ESQUEMA = ("/", "/api/docs", "/api/openapi.json", "/.well-known/security.txt", "/entrar", "/mapa")


def _rotas_do_openapi() -> list[tuple[str, str]]:
    """(método, caminho) de TODAS as rotas do esquema, com um valor no lugar de cada parâmetro de caminho."""
    saida = []
    for caminho, metodos in aplicacao.openapi()["paths"].items():
        concreto = re.sub(r"\{[^}]+\}", "1", caminho)
        for metodo in metodos:
            if metodo.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                saida.append((metodo.upper(), concreto))
    return sorted(set(saida))


ROTAS_OPENAPI = _rotas_do_openapi()


@pytest.fixture(scope="module")
def local(env):
    """Cliente da aplicação desta árvore, sem sessão: o que se prova aqui vale para 401/403/422 também."""
    return novo_cliente()


def test_o_openapi_tem_rota_para_parametrizar():
    assert len(ROTAS_OPENAPI) > 50, len(ROTAS_OPENAPI)


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_OPENAPI, ids=lambda v: str(v))
def test_conjunto_de_seguranca_em_toda_rota_do_openapi(local, metodo, caminho):
    r = local.request(metodo, caminho)
    faltam = [c for c in CABECALHOS_OBRIGATORIOS if c not in r.headers]
    assert not faltam, (metodo, caminho, r.status_code, faltam)
    assert len(r.headers.get_list("cache-control")) == 1, (metodo, caminho)


@pytest.mark.parametrize("caminho", ROTAS_SEM_ESQUEMA)
def test_conjunto_de_seguranca_nas_rotas_fora_do_esquema(local, caminho):
    r = local.get(caminho)
    assert r.status_code == 200, (caminho, r.status_code)
    faltam = [c for c in CABECALHOS_OBRIGATORIOS if c not in r.headers]
    assert not faltam, (caminho, faltam)


def test_nenhuma_resposta_sem_csp_nem_no_erro(local):
    """404, 405, 422 e 401 nascem em camadas diferentes (roteador, validação, sessão): todas passam pelo
    middleware mais externo, então nenhuma sai sem política."""
    for resposta in (
        local.get("/rota-que-nao-existe"),
        local.request("DELETE", "/saude"),
        local.post("/api/login", json={}),
        local.get("/api/eu"),
    ):
        assert resposta.headers.get("content-security-policy"), resposta.status_code


def test_documento_tem_nonce_e_dado_tem_default_src_none(local):
    csp_pagina = local.get("/entrar").headers["content-security-policy"]
    assert "script-src 'self' 'nonce-" in csp_pagina
    assert "'unsafe-inline'" not in csp_pagina and "'unsafe-eval'" not in csp_pagina
    assert "object-src 'none'" in csp_pagina and "base-uri 'none'" in csp_pagina
    csp_dado = local.get("/api/versao").headers["content-security-policy"]
    assert csp_dado.startswith("default-src 'none'")


def test_nonce_muda_a_cada_resposta(local):
    achados = {re.search(r"'nonce-([^']+)'", local.get("/entrar").headers["content-security-policy"])[1]
               for _ in range(8)}
    assert len(achados) == 8, achados


def test_swagger_ui_usa_o_nonce_da_propria_resposta(local):
    """O único <script> em linha da casa. Se ele não casar com o nonce do cabeçalho, a documentação
    fica em branco com CSP ativa — e é exatamente isso que este teste impede de voltar."""
    r = local.get("/api/docs")
    nonce = re.search(r"'nonce-([^']+)'", r.headers["content-security-policy"])[1]
    em_linha = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", r.text)
    assert em_linha, "a Swagger UI deixou de ter script em linha; reveja este teste"
    for atributos in em_linha:
        assert f'nonce="{nonce}"' in atributos, atributos


def test_security_txt_no_contrato_da_rfc_9116(local):
    r = local.get("/.well-known/security.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    campos = dict(li.split(": ", 1) for li in r.text.splitlines() if ": " in li)
    assert campos["Contact"].startswith(("mailto:", "https://")), campos
    expira = datetime.datetime.strptime(campos["Expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    agora = datetime.datetime.now(datetime.UTC)
    assert agora < expira < agora + datetime.timedelta(days=366), campos["Expires"]


# ------------------------------------------------------------------ frame-ancestors por inquilino
def _gravar_origens(conexao, slug: str, origens: list[str] | None) -> None:
    """A configuração é do inquilino, logo a gravação vai pela role da aplicação COM contexto (RLS), como
    faz PUT /api/org. O id do slug vem da mesma função SECURITY DEFINER que tests/api/test_rls.py usa."""
    from tests.api.test_rls import ids_por_slug

    with conexao.cursor() as cur:
        cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(ids_por_slug(conexao)[slug]),))
        if origens is None:
            cur.execute("UPDATE plat.tenant SET config = config - 'origens_embutidas' WHERE slug = %s", (slug,))
        else:
            cur.execute(
                "UPDATE plat.tenant SET config = config || jsonb_build_object('origens_embutidas', %s::jsonb) "
                "WHERE slug = %s",
                (json.dumps(origens), slug),
            )
    conexao.commit()
    cabecalhos.esquecer_origens()


@pytest.fixture
def origens_de_demo(conexao_plat_app):
    yield lambda origens: _gravar_origens(conexao_plat_app, "demo", origens)
    _gravar_origens(conexao_plat_app, "demo", None)


def test_frame_ancestors_fecha_por_padrao(local):
    assert "frame-ancestors 'none'" in local.get("/mapa").headers["content-security-policy"]


def test_frame_ancestors_lista_as_origens_do_inquilino(local, origens_de_demo):
    origens_de_demo(["https://sig.exemplo.gov.br"])
    csp = local.get("/mapa?inquilino=demo").headers["content-security-policy"]
    assert "frame-ancestors 'self' https://sig.exemplo.gov.br" in csp
    # outro inquilino não herda a lista
    assert "frame-ancestors 'none'" in local.get("/mapa?inquilino=demo2").headers["content-security-policy"]
