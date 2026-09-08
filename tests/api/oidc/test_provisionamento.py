"""Item L0-08-e-mapeamento-provisionamento contra o Keycloak de teste do L0-08-a (`tests/oidc_fixture/`): usuário
novo com grupo 'gis-editores' vira editor no grupo interno certo; sem grupo cai no padrão (perfil, papel, grupos,
pasta); com 'só por convite' o desconhecido recebe 403 convite_necessario ('peça convite') e o convidado entra com
o perfil do convite; mudança de grupo no IdP muda o papel no próximo login; desligamento quando o IdP deixa de
mandar grupo mapeado; 'desregistrar'; refutação: 500 grupos na asserção, grupo chamado 'administrador' sem regra,
conta desligada no IdP com sessão local viva. Grupos e usuários do IdP são criados pela API de administração do
Keycloak dentro do teste (o realm.json versionado não muda). Todo teste é `lento` (contêiner Docker)."""

import secrets
import uuid

import httpx
import pytest

from tests.api.conftest import novo_cliente
from tests.api.oidc.conftest import CLIENT_ID, HOST, ISSUER, PORTA, completar_login_no_idp

pytestmark = pytest.mark.lento

REALM = "plataforma-teste-oidc"
ADMIN = ("admin", "admin-teste-oidc")
ITEM = "L0-08-e-mapeamento-provisionamento"


# ---------------------------------------------------------------- Keycloak: API de administração
def _token_admin() -> str:
    r = httpx.post(
        f"http://{HOST}:{PORTA}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": ADMIN[0], "password": ADMIN[1]},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


class Keycloak:
    def __init__(self):
        self.base = f"http://{HOST}:{PORTA}/admin/realms/{REALM}"
        self.h = {"Authorization": f"Bearer {_token_admin()}"}
        self.criados_usuarios: list[str] = []
        self.criados_grupos: list[str] = []

    def _get(self, caminho: str, **params):
        r = httpx.get(self.base + caminho, headers=self.h, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def grupo(self, nome: str) -> str:
        for g in self._get("/groups", search=nome):
            if g["name"] == nome:
                return g["id"]
        r = httpx.post(self.base + "/groups", json={"name": nome}, headers=self.h, timeout=15)
        assert r.status_code in (201, 409), r.text
        gid = self.grupo(nome) if r.status_code == 409 else r.headers["Location"].rsplit("/", 1)[-1]
        self.criados_grupos.append(gid)
        return gid

    def usuario(self, username: str, senha: str, email: str, grupos: list[str]) -> str:
        corpo = {
            "username": username, "enabled": True, "email": email, "emailVerified": True,
            "firstName": "Teste", "lastName": username, "groups": [f"/{g}" for g in grupos],
            "credentials": [{"type": "password", "value": senha, "temporary": False}],
        }
        r = httpx.post(self.base + "/users", json=corpo, headers=self.h, timeout=15)
        assert r.status_code == 201, r.text
        uid = r.headers["Location"].rsplit("/", 1)[-1]
        self.criados_usuarios.append(uid)
        return uid

    def id_usuario(self, username: str) -> str:
        return next(u["id"] for u in self._get("/users", username=username, exact="true"))

    def trocar_grupos(self, username: str, sair: list[str], entrar: list[str]) -> None:
        uid = self.id_usuario(username)
        for g in sair:
            r = httpx.delete(f"{self.base}/users/{uid}/groups/{self.grupo(g)}", headers=self.h, timeout=15)
            r.raise_for_status()
        for g in entrar:
            httpx.put(f"{self.base}/users/{uid}/groups/{self.grupo(g)}", headers=self.h, timeout=15).raise_for_status()

    def habilitar(self, username: str, ligado: bool) -> None:
        uid = self.id_usuario(username)
        r = httpx.put(f"{self.base}/users/{uid}", json={"enabled": ligado}, headers=self.h, timeout=15)
        r.raise_for_status()

    def limpar(self) -> None:
        for uid in self.criados_usuarios:
            httpx.delete(f"{self.base}/users/{uid}", headers=self.h, timeout=15)
        for gid in self.criados_grupos:
            httpx.delete(f"{self.base}/groups/{gid}", headers=self.h, timeout=15)


# ---------------------------------------------------------------- fixtures do inquilino demo
@pytest.fixture(scope="module")
def kc(servidor_oidc):
    k = Keycloak()
    yield k
    k.limpar()


@pytest.fixture(scope="module")
def grupos_internos(sessao_a):
    s = secrets.token_hex(2)
    criados = {}
    for nome in ("editores", "leitores", "novatos"):
        r = sessao_a.post("/api/grupos", json={"nome": f"zt-prov-{nome}-{s}"})
        assert r.status_code == 201, r.text
        criados[nome] = r.json()["id"]
    r = sessao_a.post("/api/papeis", json={"nome": f"zt-prov-papel-{s}", "privilegios": ["conteudo.criar"]})
    assert r.status_code == 201, r.text
    criados["papel_id"] = r.json()["id"]
    yield criados
    for nome in ("editores", "leitores", "novatos"):
        sessao_a.delete(f"/api/grupos/{criados[nome]}")
    sessao_a.delete(f"/api/papeis/{criados['papel_id']}")


@pytest.fixture(scope="module")
def provedor(servidor_oidc, sessao_a, grupos_internos):
    """Provedor OIDC de demo com as regras do item; apagado no fim, junto com as contas oidc que a suíte criou."""
    corpo = {
        "habilitado": True, "rotulo": "Entrar com o IdP de provisionamento", "ordem": 1, "issuer": ISSUER,
        "client_id": CLIENT_ID, "escopos": "openid profile email", "atributo_grupos": "groups",
        "perfil_padrao": "visualizador", "mapa_grupo_perfil": {},
    }
    r = sessao_a.post("/api/org/oidc", json=corpo)
    assert r.status_code == 201, r.text
    criado = r.json()
    regras = {
        "criacao": "automatica",
        "atualizar_a_cada_login": True,
        "desligar_sem_grupo": False,
        "padrao": {"papel_id": None, "grupos": [grupos_internos["novatos"]]},
        "pasta": "Pessoal de {login}",
        "mapa": {
            "gis-editores": {
                "perfil": "editor", "papel_id": grupos_internos["papel_id"], "grupos": [grupos_internos["editores"]],
            },
            "gis-admins": {"perfil": "admin", "grupos": [grupos_internos["editores"], grupos_internos["leitores"]]},
        },
    }
    r = sessao_a.put(f"/api/org/logins/oidc/{criado['id']}", json={"provisionamento": regras})
    assert r.status_code == 200, r.text
    assert r.json()["provisionamento"]["mapa"]["gis-editores"]["perfil"] == "editor"
    yield {**criado, "regras": regras}
    for u in sessao_a.get("/api/usuarios?limite=1000").json().get("itens", []):
        if u["origem"] == "oidc" and u["login"].startswith("prov"):
            sessao_a.delete(f"/api/usuarios/{u['id']}")
    sessao_a.put(f"/api/org/oidc/{criado['id']}", json={**corpo, "habilitado": False})
    sessao_a.delete(f"/api/org/oidc/{criado['id']}")


def _regras(sessao_a, provedor, **sobre):
    corpo = {"provisionamento": {**provedor["regras"], **sobre}}
    r = sessao_a.put(f"/api/org/logins/oidc/{provedor['id']}", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _login_federado(cliente, username: str, senha: str, provedor_id: int):
    r = cliente.get(f"/api/sso/oidc/iniciar?inquilino=demo&provedor_id={provedor_id}", follow_redirects=False)
    assert r.status_code == 302, r.text
    c_idp = httpx.Client(timeout=10)
    r_idp = c_idp.get(r.headers["location"], follow_redirects=True)
    c_idp._pagina_login = r_idp
    qs = completar_login_no_idp(c_idp, username, senha)
    if "error" in qs:
        return cliente.get("/api/sso/oidc/retorno", params={"error": qs["error"][0]})
    return cliente.get("/api/sso/oidc/retorno", params={"code": qs["code"][0], "state": qs["state"][0]})


def _usuario(sessao_a, login: str) -> dict:
    itens = sessao_a.get(f"/api/usuarios?q={login}&limite=50").json()["itens"]
    return next(u for u in itens if u["login"] == login)


def _grupos_de(sessao_a, usuario_id: int) -> set[str]:
    r = sessao_a.get(f"/api/usuarios/{usuario_id}")
    assert r.status_code == 200, r.text
    r = sessao_a.get(f"/api/grupos?limite=200&membro={usuario_id}")
    if r.status_code == 200 and "itens" in r.json():
        return {g["id"] for g in r.json()["itens"] if any(m for m in [True])}
    return set()


def _membros(sessao_a, grupo_id: str) -> set[str]:
    r = sessao_a.get(f"/api/grupos/{grupo_id}/membros?limite=200")
    assert r.status_code == 200, r.text
    itens = r.json()["itens"] if isinstance(r.json(), dict) else r.json()
    return {m["login"] if "login" in m else m["usuario"]["login"] for m in itens}


# ---------------------------------------------------------------- portão
def test_novo_com_grupo_gis_editores_vira_editor_no_grupo_certo(kc, sessao_a, grupos_internos, provedor, medida):
    s = secrets.token_hex(2)
    kc.grupo("gis-editores")
    kc.usuario(f"prov-ed-{s}", "Teste-prov-1", f"prov-ed-{s}@exemplo.test", ["gis-editores"])
    c = novo_cliente()
    r = _login_federado(c, f"prov-ed-{s}", "Teste-prov-1", provedor["id"])
    assert r.status_code == 200, r.text
    eu = c.get("/api/eu").json()
    assert eu["perfil"] == "editor" and eu["origem"] == "oidc" and eu["papel"]["id"] == grupos_internos["papel_id"]
    assert f"prov-ed-{s}" in _membros(sessao_a, grupos_internos["editores"])
    assert f"prov-ed-{s}" not in _membros(sessao_a, grupos_internos["novatos"])
    ev = [e for e in sessao_a.get("/api/eventos?tipo=usuarios/regras_aplicadas&limite=20").json()["itens"]
          if e["alvo_id"] == str(eu["id"])]
    assert ev and ev[0]["propriedades"]["grupos_entrou"] == [grupos_internos["editores"]]
    assert ev[0]["propriedades"]["pasta_criada"] is True and ev[0]["propriedades"]["valores"] == ["gis-editores"]
    medida(ITEM)("login_gis_editores_vira_editor", 1, "caso", "tests/api/oidc/test_provisionamento.py: Keycloak real")


def test_sem_grupo_cai_no_padrao(kc, sessao_a, grupos_internos, provedor):
    s = secrets.token_hex(2)
    kc.usuario(f"prov-sem-{s}", "Teste-prov-2", f"prov-sem-{s}@exemplo.test", [])
    c = novo_cliente()
    r = _login_federado(c, f"prov-sem-{s}", "Teste-prov-2", provedor["id"])
    assert r.status_code == 200, r.text
    eu = c.get("/api/eu").json()
    assert eu["perfil"] == "visualizador" and eu["papel"] is None
    assert f"prov-sem-{s}" in _membros(sessao_a, grupos_internos["novatos"])
    pastas = sessao_a.get("/api/pastas?limite=200").json()
    nomes = {p["nome"] for p in (pastas["itens"] if isinstance(pastas, dict) else pastas)}
    assert f"Pessoal de prov-sem-{s}" in nomes


def test_grupo_chamado_administrador_sem_regra_nao_vira_admin_e_500_grupos(kc, sessao_a, provedor):
    s = secrets.token_hex(2)
    for nome in ("administrador", "admin"):
        kc.grupo(nome)
    muitos = [f"g500-{i}" for i in range(500)]
    for nome in muitos:
        kc.grupo(nome)
    kc.usuario(f"prov-adv-{s}", "Teste-prov-3", f"prov-adv-{s}@exemplo.test", ["administrador", "admin", *muitos])
    c = novo_cliente()
    r = _login_federado(c, f"prov-adv-{s}", "Teste-prov-3", provedor["id"])
    assert r.status_code == 200, r.text
    eu = c.get("/api/eu").json()
    assert eu["perfil"] == "visualizador" and eu["papel"] is None  # padrão, nunca admin por nome parecido


def test_mudanca_de_grupo_no_idp_muda_o_papel_no_proximo_login(kc, sessao_a, grupos_internos, provedor):
    s = secrets.token_hex(2)
    kc.grupo("gis-admins")
    kc.usuario(f"prov-mud-{s}", "Teste-prov-4", f"prov-mud-{s}@exemplo.test", ["gis-editores"])
    c = novo_cliente()
    assert _login_federado(c, f"prov-mud-{s}", "Teste-prov-4", provedor["id"]).status_code == 200
    assert c.get("/api/eu").json()["perfil"] == "editor"
    kc.trocar_grupos(f"prov-mud-{s}", sair=["gis-editores"], entrar=["gis-admins"])
    c2 = novo_cliente()
    assert _login_federado(c2, f"prov-mud-{s}", "Teste-prov-4", provedor["id"]).status_code == 200
    eu = c2.get("/api/eu").json()
    assert eu["perfil"] == "admin" and eu["papel"] is None  # a regra de gis-admins não tem papel
    assert f"prov-mud-{s}" in _membros(sessao_a, grupos_internos["leitores"])
    # atualizar_a_cada_login desligado: o próximo login NÃO rebaixa
    _regras(sessao_a, provedor, atualizar_a_cada_login=False)
    try:
        kc.trocar_grupos(f"prov-mud-{s}", sair=["gis-admins"], entrar=["gis-editores"])
        c3 = novo_cliente()
        assert _login_federado(c3, f"prov-mud-{s}", "Teste-prov-4", provedor["id"]).status_code == 200
        assert c3.get("/api/eu").json()["perfil"] == "admin"
    finally:
        _regras(sessao_a, provedor)
    c4 = novo_cliente()
    assert _login_federado(c4, f"prov-mud-{s}", "Teste-prov-4", provedor["id"]).status_code == 200
    assert c4.get("/api/eu").json()["perfil"] == "editor"
    assert f"prov-mud-{s}" not in _membros(sessao_a, grupos_internos["leitores"])  # saiu do grupo regido


def test_so_por_convite_desconhecido_recebe_peca_convite_e_convidado_entra(kc, sessao_a, provedor):
    s = secrets.token_hex(2)
    kc.usuario(f"prov-conv-{s}", "Teste-prov-5", f"prov-conv-{s}@exemplo.test", [])
    _regras(sessao_a, provedor, criacao="convite")
    try:
        c = novo_cliente()
        r = _login_federado(c, f"prov-conv-{s}", "Teste-prov-5", provedor["id"])
        assert r.status_code == 403 and r.json()["erro"] == "convite_necessario", r.text
        assert "convite" in r.json()["mensagem"]
        assert c.get("/api/eu").status_code == 401
        r = sessao_a.post("/api/convites", json={"email": f"prov-conv-{s}@exemplo.test", "perfil": "editor"})
        assert r.status_code == 201, r.text
        convite_id, link = r.json()["id"], r.json().get("link") or ""
        assert convite_id in {x["id"] for x in sessao_a.get("/api/convites?limite=100").json()}
        c = novo_cliente()
        r = _login_federado(c, f"prov-conv-{s}", "Teste-prov-5", provedor["id"])
        assert r.status_code == 200, r.text
        assert c.get("/api/eu").json()["perfil"] == "editor"  # perfil do convite (o IdP não mandou grupo)
        # o convite foi consumido pelo login federado: some da lista de pendentes e o token não resolve mais
        assert convite_id not in {x["id"] for x in sessao_a.get("/api/convites?limite=100").json()}
        if "token=" in link:
            token = link.split("token=", 1)[1].split("&", 1)[0]
            assert sessao_a.get(f"/api/convites/resolver?token={token}").status_code == 410
    finally:
        _regras(sessao_a, provedor)


def test_desligar_sem_grupo_e_conta_desligada_no_idp_com_sessao_local(kc, sessao_a, provedor):
    s = secrets.token_hex(2)
    kc.usuario(f"prov-des-{s}", "Teste-prov-6", f"prov-des-{s}@exemplo.test", ["gis-editores"])
    c = novo_cliente()
    assert _login_federado(c, f"prov-des-{s}", "Teste-prov-6", provedor["id"]).status_code == 200
    # o IdP deixa de mandar o grupo e a regra manda desligar (sem perfil padrão): 403 e conta desativada
    r = sessao_a.put(f"/api/org/oidc/{provedor['id']}", json={
        "habilitado": True, "rotulo": "Entrar com o IdP de provisionamento", "ordem": 1, "issuer": ISSUER,
        "client_id": CLIENT_ID, "escopos": "openid profile email", "atributo_grupos": "groups",
        "perfil_padrao": None, "mapa_grupo_perfil": {},
    })
    assert r.status_code == 200, r.text
    _regras(sessao_a, provedor, desligar_sem_grupo=True)
    try:
        kc.trocar_grupos(f"prov-des-{s}", sair=["gis-editores"], entrar=[])
        c2 = novo_cliente()
        r = _login_federado(c2, f"prov-des-{s}", "Teste-prov-6", provedor["id"])
        assert r.status_code == 403 and r.json()["erro"] == "conta_desligada", r.text
        u = _usuario(sessao_a, f"prov-des-{s}")
        assert u["ativo"] is False
        assert c.get("/api/eu").status_code == 401  # a sessão anterior caiu junto
        tipos = {e["tipo"] for e in sessao_a.get("/api/eventos?limite=20").json()["itens"]}
        assert "usuarios/desligar_federado" in tipos
    finally:
        _regras(sessao_a, provedor)
        sessao_a.put(f"/api/org/oidc/{provedor['id']}", json={
            "habilitado": True, "rotulo": "Entrar com o IdP de provisionamento", "ordem": 1, "issuer": ISSUER,
            "client_id": CLIENT_ID, "escopos": "openid profile email", "atributo_grupos": "groups",
            "perfil_padrao": "visualizador", "mapa_grupo_perfil": {},
        })
        _regras(sessao_a, provedor)
    # conta desligada NO IdP com sessão local viva: a sessão continua até expirar; o próximo login é recusado
    kc.usuario(f"prov-idp-{s}", "Teste-prov-7", f"prov-idp-{s}@exemplo.test", ["gis-editores"])
    c3 = novo_cliente()
    assert _login_federado(c3, f"prov-idp-{s}", "Teste-prov-7", provedor["id"]).status_code == 200
    kc.habilitar(f"prov-idp-{s}", False)
    assert c3.get("/api/eu").status_code == 200  # expira no próximo login (política de sessão), não na hora
    c4 = novo_cliente()
    try:
        r = _login_federado(c4, f"prov-idp-{s}", "Teste-prov-7", provedor["id"])
        recusado = r.status_code == 401
    except AssertionError:
        recusado = True  # o Keycloak nem redireciona: devolve a própria tela com "conta desabilitada"
    assert recusado and c4.get("/api/eu").status_code == 401  # nunca nasce sessão nova


def test_desregistrar_conta_federada(kc, sessao_a, provedor):
    s = secrets.token_hex(2)
    kc.usuario(f"prov-desr-{s}", "Teste-prov-8", f"prov-desr-{s}@exemplo.test", ["gis-editores"])
    c = novo_cliente()
    assert _login_federado(c, f"prov-desr-{s}", "Teste-prov-8", provedor["id"]).status_code == 200
    u = _usuario(sessao_a, f"prov-desr-{s}")
    r = sessao_a.post(f"/api/usuarios/{u['id']}/desregistrar")
    assert r.status_code == 204, r.text
    assert c.get("/api/eu").status_code == 401
    assert _usuario(sessao_a, f"prov-desr-{s}")["ativo"] is False
    # conta local não se desregistra; a própria também não
    eu = sessao_a.get("/api/eu").json()
    assert sessao_a.post(f"/api/usuarios/{eu['id']}/desregistrar").status_code == 409
    # modo automático: o próximo login religa o vínculo e reativa
    c2 = novo_cliente()
    assert _login_federado(c2, f"prov-desr-{s}", "Teste-prov-8", provedor["id"]).status_code == 200
    assert _usuario(sessao_a, f"prov-desr-{s}")["ativo"] is True
    # modo convite: desregistrada volta a ser desconhecida -> peça convite
    sessao_a.post(f"/api/usuarios/{u['id']}/desregistrar")
    _regras(sessao_a, provedor, criacao="convite")
    try:
        c3 = novo_cliente()
        r = _login_federado(c3, f"prov-desr-{s}", "Teste-prov-8", provedor["id"])
        assert r.status_code == 403 and r.json()["erro"] == "convite_necessario"
    finally:
        _regras(sessao_a, provedor)


def test_botoes_rotulo_e_ordem_na_tela_de_entrada(sessao_a, provedor, cliente):
    r = sessao_a.put(f"/api/org/logins/oidc/{provedor['id']}", json={"rotulo": "Entrar pelo órgão", "ordem": 0})
    assert r.status_code == 200 and r.json()["rotulo"] == "Entrar pelo órgão", r.text
    lista = cliente.get("/api/login/provedores?inquilino=demo").json()["provedores"]
    assert any(p["id"] == provedor["id"] and p["rotulo"] == "Entrar pelo órgão" for p in lista)
    volta = {"rotulo": "Entrar com o IdP de provisionamento", "ordem": 1}
    assert sessao_a.put(f"/api/org/logins/oidc/{provedor['id']}", json=volta).status_code == 200
    assert sessao_a.put("/api/org/logins/oidc/999999", json={"ordem": 1}).status_code == 404
    assert sessao_a.put(f"/api/org/logins/oidc/{provedor['id']}", json={}).status_code == 422
    assert sessao_a.put("/api/org/logins/ldap/0", json={"rotulo": "x"}).status_code in (404, 422)
    inexistente = {"provisionamento": {"mapa": {"g": {"grupos": [str(uuid.uuid4())]}}}}
    r = sessao_a.put(f"/api/org/logins/oidc/{provedor['id']}", json=inexistente)
    assert r.status_code == 422 and r.json()["detalhe"]["campo"] == "grupos"
    lista = sessao_a.get("/api/org/logins").json()
    assert any(p["tipo"] == "oidc" and p["id"] == provedor["id"] for p in lista["provedores"])
