"""Item L0-08-b-saml contra um IdP real (Keycloak 26 em Docker, realm de teste do L0-08-a): metadado do IdP lido
por URL; SP-initiated (AuthnRequest → login no Keycloak → SAMLResponse assinado no ACS) cai no inquilino e no
perfil certos; IdP-initiated (URL de SSO iniciado pelo IdP do Keycloak) também; asserção cifrada pelo Keycloak
com o certificado do SP; logout propagado (LogoutRequest ao Keycloak e LogoutResponse de volta no /slo); Keycloak
derrubado não impede o login local. Captura de tela: nenhuma (chromium headless quebrado nesta máquina, achado do
L0-08-a); a evidência é o log estruturado de cada etapa mais as asserções abaixo."""

import time
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from app.main import app
from tests.api.saml.conftest import (
    IDP,
    MAPA_GRUPO_PERFIL,
    METADADO_URL,
    USUARIOS,
    dirigir_login_no_idp,
    servidor_oidc,  # noqa: F401
)

pytestmark = pytest.mark.lento
BASE = "http://sp.teste.invalido"


def cliente() -> TestClient:
    return TestClient(app, base_url=BASE)


@pytest.fixture(scope="module")
def provedor_keycloak(servidor_oidc, sessao_a, sessao_b):  # noqa: F811
    """Dois provedores SAML do inquilino demo apontando para o Keycloak (metadado lido por URL; loopback aceito
    fora de produção): `p` assinado e `p_cifrado` (assercao_cifrada). O Keycloak identifica o SP pelo clientId ==
    Issuer do AuthnRequest, então cada cliente do realm recebe como clientId o entityId do provedor correspondente
    (a URL de IdP-initiated fica pelo nome curto em saml_idp_initiated_sso_url_name), e o cliente cifrado ganha o
    certificado do SP gerado agora (nunca há chave no repositório)."""
    import httpx

    from tests.api.saml.conftest import HOST, PORTA, cliente_keycloak, token_admin

    # o cifrado vive no inquilino demo2: UNIQUE (tenant_id, idp_entity_id) não deixa dois provedores do mesmo IdP
    # no mesmo inquilino, e a resposta IdP-initiated cifrada tem de cair no inquilino certo pela Audience
    provedores = {}
    sessoes = {"p": sessao_a, "p_cifrado": sessao_b}
    for s in (sessao_a, sessao_b):  # resto de execução anterior interrompida
        for antigo in s.get("/api/org/saml").json():
            if antigo["rotulo"].startswith("zt saml keycloak"):
                s.delete(f"/api/org/saml/{antigo['id']}")
    for nome, cid, cifrar in (("p", "plat-saml-teste", False), ("p_cifrado", "plat-saml-cifrado", True)):
        r = sessoes[nome].post(
            "/api/org/saml",
            json={
                "rotulo": f"zt saml keycloak {nome}",
                "metadado_url": METADADO_URL,
                "mapa_grupo_perfil": MAPA_GRUPO_PERFIL,
                "assercao_cifrada": cifrar,
                "formato_nameid": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
            },
        )
        assert r.status_code == 201, r.text
        p = r.json()
        c = cliente_keycloak(cid)
        c["clientId"] = f"{BASE}/api/sso/saml/metadata?provedor_id={p['id']}"
        c["attributes"] = {**c["attributes"], "saml_idp_initiated_sso_url_name": cid}
        if cifrar:
            c["attributes"]["saml.encryption.certificate"] = p["sp_certificado"]
        httpx.put(
            f"http://{HOST}:{PORTA}/admin/realms/plataforma-teste-oidc/clients/{c['id']}",
            json=c,
            headers={"Authorization": f"Bearer {token_admin()}"},
            timeout=15,
        ).raise_for_status()
        provedores[nome] = p
    yield provedores["p"] | {"cifrado": provedores["p_cifrado"]}
    for nome, p in provedores.items():
        sessoes[nome].delete(f"/api/org/saml/{p['id']}")
    for s in (sessao_a, sessao_b):
        for u in s.get("/api/usuarios?limite=200").json().get("itens", []):
            if u.get("origem") == "saml":
                s.delete(f"/api/usuarios/{u['id']}")


def _entrar_sp_initiated(p: dict, username: str, proximo: str = "/") -> tuple[TestClient, object]:
    c = cliente()
    r = c.get(f"/api/sso/saml/iniciar?inquilino=demo&provedor_id={p['id']}&proximo={proximo}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(IDP + "/protocol/saml"), r.text
    campos = dirigir_login_no_idp(r.headers["location"], username, USUARIOS[username])
    assert campos["_acao"] == f"{BASE}/api/sso/saml/acs"
    r2 = c.post(
        "/api/sso/saml/acs", data={k: v for k, v in campos.items() if not k.startswith("_")}, follow_redirects=False
    )
    return c, r2


def test_sp_initiated_cai_no_inquilino_e_perfil_certos(provedor_keycloak, medida):
    t0 = time.perf_counter()
    c, r = _entrar_sp_initiated(provedor_keycloak, "ana.oidc", "/mapa")
    assert r.status_code == 303 and r.headers["location"] == "/mapa", r.text
    eu = c.get("/api/eu").json()
    assert eu["login"] == "ana.oidc" and eu["perfil"] == "admin" and eu["origem"] == "saml"
    assert eu["inquilino"]["slug"] == "demo"
    medida("L0-08-b-saml")(
        "latencia_login_saml_ms",
        round((time.perf_counter() - t0) * 1000, 1),
        "ms",
        "SP-initiated contra Keycloak 26 (tests/api/saml/test_login_saml.py)",
    )
    c2, r2 = _entrar_sp_initiated(provedor_keycloak, "bruno.oidc")
    assert r2.status_code == 303 and c2.get("/api/eu").json()["perfil"] == "visualizador"
    c3, r3 = _entrar_sp_initiated(provedor_keycloak, "carla.oidc")
    assert r3.status_code == 403 and r3.json()["erro"] == "sem_grupo_mapeado"


def test_idp_initiated_pelo_keycloak(provedor_keycloak):
    campos = dirigir_login_no_idp(f"{IDP}/protocol/saml/clients/plat-saml-teste", "bruno.oidc", USUARIOS["bruno.oidc"])
    c = cliente()
    r = c.post(
        "/api/sso/saml/acs", data={k: v for k, v in campos.items() if not k.startswith("_")}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    assert c.get("/api/eu").json()["login"] == "bruno.oidc"


def test_assercao_cifrada_pelo_keycloak(provedor_keycloak):
    campos = dirigir_login_no_idp(f"{IDP}/protocol/saml/clients/plat-saml-cifrado", "ana.oidc", USUARIOS["ana.oidc"])
    import base64

    xml = base64.b64decode(campos["SAMLResponse"]).decode("utf-8", errors="replace")
    assert "EncryptedAssertion" in xml and "<saml:Assertion" not in xml
    c = cliente()
    r = c.post(
        "/api/sso/saml/acs", data={k: v for k, v in campos.items() if not k.startswith("_")}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    eu = c.get("/api/eu").json()
    assert eu["login"] == "ana.oidc" and eu["inquilino"]["slug"] == "demo2"  # provedor cifrado é o de demo2


def test_logout_propagado_ao_keycloak_e_de_volta(provedor_keycloak):
    c, r = _entrar_sp_initiated(provedor_keycloak, "ana.oidc")
    assert r.status_code == 303
    r = c.get("/api/sso/saml/logout", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(IDP + "/protocol/saml"), r.headers
    assert c.get("/api/eu").status_code == 401
    # o navegador leva o LogoutRequest ao Keycloak, que devolve a LogoutResponse ao nosso /slo: por POST (auto-post
    # com SAMLResponse) ou por Redirect (302 com SAMLResponse na query) — os dois bindings são aceitos
    import httpx

    k = httpx.Client(timeout=15, follow_redirects=False)
    r2 = k.get(r.headers["location"])
    saltos = 0
    while r2.status_code in (302, 303) and not r2.headers["location"].startswith(BASE) and saltos < 5:
        r2 = k.get(r2.headers["location"])
        saltos += 1
    if r2.status_code in (302, 303):
        destino = r2.headers["location"]
        assert destino.startswith(f"{BASE}/api/sso/saml/slo?"), destino
        r3 = c.get("/api/sso/saml/slo?" + urlsplit(destino).query, follow_redirects=False)
    else:
        assert r2.status_code == 200, r2.text[:300]
        from tests.api.saml.conftest import _formulario

        acao, campos = _formulario(r2.text)
        assert acao == f"{BASE}/api/sso/saml/slo" and "SAMLResponse" in campos
        r3 = c.post("/api/sso/saml/slo", data=campos, follow_redirects=False)
    assert r3.status_code == 302 and r3.headers["location"] == "/", r3.text


def test_keycloak_derrubado_nao_impede_login_local(provedor_keycloak, cred):
    from tests.api.oidc.conftest import derrubar_servidor_oidc, religar_servidor_oidc

    derrubar_servidor_oidc()
    try:
        r = cliente().get(
            f"/api/sso/saml/iniciar?inquilino=demo&provedor_id={provedor_keycloak['id']}", follow_redirects=False
        )
        assert (
            r.status_code == 302
        )  # o AuthnRequest é gerado localmente; o IdP fora do ar só quebra o passo do navegador
        login, senha = cred["demo"]
        c = cliente()
        assert c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha}).status_code == 200
    finally:
        religar_servidor_oidc()
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert "SAMLRequest" in q and "Signature" in q
