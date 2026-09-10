"""Fixtures do item L0-08-b-saml contra o Keycloak de teste do L0-08-a (`tests/oidc_fixture/`, mesmo contêiner e
realm; clientes `plat-saml-teste` e `plat-saml-cifrado` acrescentados ao realm.json). O fluxo do navegador é
dirigido por `httpx` puro (formulário de login do Keycloak e auto-post do SAMLResponse), como no OIDC. O
certificado do SP é gerado em tempo de execução, então o cliente cifrado recebe o certificado pela API de
administração do Keycloak dentro do teste (nunca há chave no repositório)."""

import re
from html import unescape

import httpx

from tests.api.oidc.conftest import HOST, PORTA, _cookies_da_resposta, servidor_oidc  # noqa: F401 (fixture reexportada)

REALM = "plataforma-teste-oidc"
IDP = f"http://{HOST}:{PORTA}/realms/{REALM}"
METADADO_URL = f"{IDP}/protocol/saml/descriptor"
ADMIN = ("admin", "admin-teste-oidc")
MAPA_GRUPO_PERFIL = {"gg-oidc-admin": "admin", "gg-oidc-leitura": "visualizador"}
USUARIOS = {"ana.oidc": "Teste-oidc-1", "bruno.oidc": "Teste-oidc-2", "carla.oidc": "Teste-oidc-3"}


def token_admin() -> str:
    r = httpx.post(
        f"http://{HOST}:{PORTA}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": ADMIN[0], "password": ADMIN[1]},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def cliente_keycloak(client_id: str) -> dict:
    tok = token_admin()
    r = httpx.get(
        f"http://{HOST}:{PORTA}/admin/realms/{REALM}/clients",
        params={"clientId": client_id},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()[0]


def configurar_cliente_keycloak(client_id: str, atributos: dict) -> None:
    """Altera atributos do cliente SAML no Keycloak (ex.: certificado de cifra do SP, URLs do SP)."""
    tok = token_admin()
    c = cliente_keycloak(client_id)
    c["attributes"] = {**(c.get("attributes") or {}), **atributos}
    r = httpx.put(
        f"http://{HOST}:{PORTA}/admin/realms/{REALM}/clients/{c['id']}",
        json=c,
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    r.raise_for_status()


def _formulario(html: str) -> tuple[str, dict[str, str]]:
    m = re.search(r'<form[^>]+action="([^"]+)"', html)
    assert m, f"formulário não encontrado: {html[:300]}"
    campos = {n: unescape(v) for n, v in re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html)}
    return unescape(m.group(1)), campos


def dirigir_login_no_idp(url_inicial: str, username: str, senha: str) -> dict[str, str]:
    """Abre a URL (redirect ao SSO do Keycloak), preenche o login e devolve os campos do auto-post final
    ({SAMLResponse, RelayState}) que o navegador mandaria ao ACS."""
    c = httpx.Client(timeout=15, follow_redirects=True)
    r = c.get(url_inicial)
    acao, _ = _formulario(r.text)
    r2 = c.post(
        acao,
        data={"username": username, "password": senha},
        headers={"Cookie": _cookies_da_resposta(c, r)},
        follow_redirects=True,
    )
    assert r2.status_code == 200, r2.text[:300]
    acao2, campos = _formulario(r2.text)
    assert "SAMLResponse" in campos, r2.text[:500]
    campos["_acao"] = acao2
    return campos
