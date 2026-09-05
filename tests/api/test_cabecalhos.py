"""HTTP real na URL pública (nginx + TLS): noindex em toda rota, no-store nos módulos, X-Req-Id da API.
Exige rede; pulado só se o nome público não resolver."""

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


def test_x_frame_options_deny(http):
    assert http.get("/").headers.get("x-frame-options") == "DENY"


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
