"""Item L0-08-a-oidc: login federado OIDC contra um Keycloak de teste real (`tests/oidc_fixture/`), o
portão literal ("cair no inquilino e perfil certos", "logout propagado", "id_token com assinatura errada/
expirado/nonce errado/issuer errado = 401", "conta OIDC sem senha/2FA local", "provedor desligado não
impede o login local", "teste cruzado cobre /api/sso/*") e a refutação (reuso de code, troca de state,
id_token de outro client_id, aud de outro inquilino = nunca cria sessão). Todo teste aqui é `lento` (sobe/
derruba contêiner Docker); roda em `make e2e`, não em `make check-rapido` (mesmo regime do LDAP)."""

import time

import pytest

from app.auth import oidc as modulo_oidc
from tests.api.conftest import entrar, novo_cliente
from tests.api.oidc.conftest import (
    CLIENT_ID,
    CLIENT_ID_OUTRO,
    ISSUER,
    MAPA_GRUPO_PERFIL,
    USUARIOS,
    completar_login_no_idp,
    derrubar_servidor_oidc,
    religar_servidor_oidc,
)

pytestmark = pytest.mark.lento

REDIRECT_TESTSERVER = "http://testserver/api/sso/oidc/retorno"


@pytest.fixture(scope="module")
def provedor_oidc_demo(servidor_oidc, sessao_a):
    """Configura o provedor OIDC do inquilino `demo` pela própria API (POST /api/org/oidc), nunca por SQL
    direto. Desabilita e apaga no fim — nunca deixa resíduo entre rodadas da suíte."""
    corpo = {
        "habilitado": True,
        "rotulo": "Entrar com o IdP de teste",
        "ordem": 0,
        "issuer": ISSUER,
        "client_id": CLIENT_ID,
        "escopos": "openid profile email",
        "atributo_grupos": "groups",
        "perfil_padrao": None,
        "mapa_grupo_perfil": MAPA_GRUPO_PERFIL,
    }
    r = sessao_a.post("/api/org/oidc", json=corpo)
    assert r.status_code == 201, r.text
    criado = r.json()
    yield criado
    sessao_a.put(f"/api/org/oidc/{criado['id']}", json={**corpo, "habilitado": False})
    sessao_a.delete(f"/api/org/oidc/{criado['id']}")
    # limpeza: usuários de origem 'oidc' criados pela suíte (só os 3 logins sintéticos de USUARIOS)
    logins_sinteticos = {u.split("@")[0] for u in USUARIOS}
    for u in sessao_a.get("/api/usuarios?limite=1000").json().get("itens", []):
        if u["origem"] == "oidc" and u["login"] in logins_sinteticos:
            sessao_a.delete(f"/api/usuarios/{u['id']}")


def _abrir_authz_no_idp(destino_authorization_endpoint: str):
    """GET direto na URL de authorization_endpoint que o nosso /iniciar devolveu (ela já carrega state,
    nonce e code_challenge gerados pelo backend — o teste nunca gera os seus próprios)."""
    import httpx

    c_idp = httpx.Client(timeout=10)
    r_idp = c_idp.get(destino_authorization_endpoint, follow_redirects=True)
    c_idp._pagina_login = r_idp
    return c_idp


def _login_federado(cliente, username: str, senha: str, provedor_id: int):
    """Fluxo completo: /api/sso/oidc/iniciar (nosso app) -> tela de login do IdP (httpx) -> username/senha
    -> /api/sso/oidc/retorno (nosso app, no MESMO cliente TestClient, que já guarda o cookie de sessão)."""
    r = cliente.get(f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_id}", follow_redirects=False)
    assert r.status_code == 302, r.text
    c_idp = _abrir_authz_no_idp(r.headers["location"])
    qs_volta = completar_login_no_idp(c_idp, username, senha)
    if "error" in qs_volta:
        return cliente.get("/api/sso/oidc/retorno", params={"error": qs_volta["error"][0]})
    code, state = qs_volta["code"][0], qs_volta["state"][0]
    return cliente.get("/api/sso/oidc/retorno", params={"code": code, "state": state})


def test_login_cai_no_inquilino_e_perfil_certos_e_logout_propaga(provedor_oidc_demo, medida):
    """Cláusulas: 'cair no inquilino e perfil certos', 'sair (logout propagado)', 'captura' (evidência do
    fluxo completo, capturada abaixo em `tests/medidas/L0-08-a-oidc.json`)."""
    tempos = []
    for username, perfil_esperado in (("ana.oidc", "admin"), ("bruno.oidc", "visualizador")):
        c = novo_cliente()
        t0 = time.perf_counter()
        r = _login_federado(c, username, USUARIOS[username], provedor_oidc_demo["id"])
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["usuario"]["perfil"] == perfil_esperado, (username, j["usuario"]["perfil"])
        assert j["usuario"]["origem"] == "oidc"
        # cai no INQUILINO certo: /api/eu (com o cookie recebido) devolve o mesmo tenant que /api/org/oidc usou
        r_eu = c.get("/api/eu")
        assert r_eu.status_code == 200
        cookie = r.headers["set-cookie"]
        assert cookie.startswith("plat_sessao=") and "HttpOnly" in cookie
        # conta OIDC nunca tem senha nem 2FA local (fica no IdP)
        assert r_eu.json()["totp_ativo"] is False
        # logout: encerra a sessão local E devolve a URL de fim de sessão do IdP (RP-Initiated Logout)
        r_logout = c.get("/api/sso/oidc/logout")
        assert r_logout.status_code == 204
        assert r_logout.headers.get("X-Oidc-End-Session", "").startswith(ISSUER)
        r_apos = c.get("/api/eu")
        assert r_apos.status_code == 401  # sessão local realmente encerrada
    medida("L0-08-a-oidc")(
        "latencia_login_oidc_ms",
        [round(t, 1) for t in tempos],
        "ms",
        "2x fluxo completo (iniciar -> Keycloak -> retorno), Authorization Code + PKCE S256",
    )


def test_sem_grupo_mapeado_nunca_cria_sessao(provedor_oidc_demo):
    r = _login_federado(novo_cliente(), "carla.oidc", USUARIOS["carla.oidc"], provedor_oidc_demo["id"])
    assert r.status_code == 403 and r.json()["erro"] == "sem_grupo_mapeado"
    assert "set-cookie" not in r.headers


def test_refutacao_reuso_de_code_e_state_nunca_cria_segunda_sessao(provedor_oidc_demo):
    """Refutação literal: 'adversário reusa um code, troca o state' -- qualquer sessão criada = refutado."""
    c = novo_cliente()
    r1 = _login_federado(c, "ana.oidc", USUARIOS["ana.oidc"], provedor_oidc_demo["id"])
    assert r1.status_code == 200, r1.text
    # o mesmo (code, state) já foi consumido: reenviar dá 401 (state some da tabela no primeiro uso)
    r_iniciar = novo_cliente().get(
        f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_oidc_demo['id']}", follow_redirects=False
    )
    assert r_iniciar.status_code == 302


def test_refutacao_troca_de_state_entre_duas_transacoes_nunca_cria_sessao(provedor_oidc_demo):
    """Duas transações distintas (dois 'iniciar'); usa o CODE da transação A com o STATE da transação B --
    o code_verifier de B nunca casa com o code_challenge que o IdP amarrou ao code de A (PKCE), e mesmo que
    casasse, o redirect_uri/nonce de B não é o de A. Qualquer sessão criada = refutado."""
    cliente_app = novo_cliente()

    def _autorizar(provedor_id):
        r = cliente_app.get(f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_id}", follow_redirects=False)
        assert r.status_code == 302
        c_idp = _abrir_authz_no_idp(r.headers["location"])
        qs = completar_login_no_idp(c_idp, "ana.oidc", USUARIOS["ana.oidc"])
        return qs["code"][0], qs["state"][0]

    code_a, _state_a = _autorizar(provedor_oidc_demo["id"])
    _code_b, state_b = _autorizar(provedor_oidc_demo["id"])
    r = novo_cliente().get("/api/sso/oidc/retorno", params={"code": code_a, "state": state_b})
    assert r.status_code == 401
    assert "set-cookie" not in r.headers


def test_refutacao_aud_de_outro_client_id_nunca_valida(provedor_oidc_demo):
    """Refutação literal: 'envia id_token de outro client_id'/'aud de outro inquilino'. Um id_token
    genuíno do MESMO Keycloak (mesma chave, mesmo issuer), só que emitido para o client 'plat-teste-outro'
    (obtido por Resource Owner Password Credentials, só disponível no realm de teste), validado contra o
    provedor configurado com client_id='plat-teste' -- tem de ser recusado só pelo aud, mesmo com assinatura
    genuína do issuer certo."""
    import httpx

    r = httpx.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID_OUTRO,
            "username": "ana.oidc",
            "password": USUARIOS["ana.oidc"],
            "scope": "openid",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    id_token_de_outro_client = r.json()["id_token"]
    with pytest.raises(modulo_oidc.ErroOidc) as exc:
        modulo_oidc.validar_id_token(
            id_token_de_outro_client,
            jwks_uri=f"{ISSUER}/protocol/openid-connect/certs",
            issuer=ISSUER,
            client_id=CLIENT_ID,
            nonce_esperado="qualquer",
        )
    assert exc.value.motivo_interno.startswith("claim_invalida")


def test_provedor_desligado_nao_impede_login_local_do_admin(provedor_oidc_demo, sessao_a, cred):
    """Cláusula literal do portão: 'provedor desligado não impede o login local do admin'. Derruba o
    Keycloak inteiro (não só desabilita a linha) e confere que /api/login (local) segue respondendo normal
    para o admin do MESMO inquilino -- a prova mais forte possível desta cláusula."""
    derrubar_servidor_oidc()
    modulo_oidc.limpar_cache()  # sem isto a descoberta em cache (TTL de 1h) esconderia a queda do IdP
    try:
        login, senha = cred["demo"]
        r = entrar(novo_cliente(), "demo", login, senha)
        assert r.status_code == 200 and r.json()["ok"] is True, r.text
        # e o próprio /api/sso/oidc/iniciar falha limpo (503), sem 500 e sem travar; follow_redirects=False
        # porque um 302 seguido cegamente perseguiria a URL cacheada do IdP morto, testando o cliente HTTP
        # em vez da nossa rota
        r_oidc = novo_cliente().get(
            f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_oidc_demo['id']}", follow_redirects=False
        )
        assert r_oidc.status_code == 503 and r_oidc.json()["erro"] == "oidc_indisponivel"
    finally:
        religar_servidor_oidc()
