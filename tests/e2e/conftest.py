"""Fixtures dos e2e do L0-02: contexto pt-BR 1280x800; rotas do OpenAPI da URL interna; salto limpo enquanto o
backend não publica /api/login (o frontend foi escrito contra o ADR 0002 antes das rotas existirem)."""

import os

import httpx
import pytest

from tests.e2e.apoio import credenciais


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    args = {**browser_context_args, "locale": "pt-BR", "viewport": {"width": 1280, "height": 800}}
    # item L7-11-b (appliance sem internet): com PLAT_E2E_PROXY todo pedido do navegador passa pelo proxy de
    # captura (tests/operacao/proxy_captura.py), que repassa só a própria instalação e conta o que tentou sair
    proxy = os.environ.get("PLAT_E2E_PROXY")
    if proxy:
        args["proxy"] = {"server": proxy}
    return args


@pytest.fixture(scope="session")
def rotas_api(base_url, url_publica_resolve) -> set[str]:
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    try:
        r = httpx.get(f"{base_url}/api/openapi.json", timeout=15)
    except httpx.HTTPError as e:
        pytest.skip(f"{base_url}/api/openapi.json inacessível: {e}")
    if r.status_code != 200:
        pytest.skip(f"{base_url}/api/openapi.json devolveu {r.status_code}")
    return set(r.json().get("paths", {}))


@pytest.fixture(scope="session")
def api_auth(rotas_api) -> set[str]:
    """as rotas de identidade do ADR 0002 existem no OpenAPI da URL interna; senão os e2e do item são saltados."""
    faltam = [r for r in ("/api/login", "/api/eu", "/api/usuarios") if r not in rotas_api]
    if faltam:
        pytest.skip(f"backend ainda sem {faltam} no OpenAPI (rotas do ADR 0002)")
    return rotas_api


@pytest.fixture(scope="session")
def credenciais_demo(api_auth) -> tuple[str, str, str]:
    """(slug, login, senha) do admin de demonstração, de tests/credenciais.txt."""
    c = credenciais()
    if "demo" not in c:
        pytest.skip("tests/credenciais.txt sem a linha do inquilino demo (rode install.sh)")
    return ("demo", *c["demo"])


@pytest.fixture
def admin_api(playwright, base_url, credenciais_demo):
    """contexto de API já autenticado como admin de demo (cookie), para preparar e limpar dados dos e2e."""
    slug, login, senha = credenciais_demo
    ctx = playwright.request.new_context(base_url=base_url)
    r = ctx.post("/api/login", data={"inquilino": slug, "login": login, "senha": senha})
    assert r.status == 200 and r.json().get("ok") is True, (r.status, r.text())
    yield ctx
    ctx.post("/api/logout", data={})
    ctx.dispose()
