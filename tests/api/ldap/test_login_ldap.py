"""Item L0-08-d-ldap: bind LDAP/AD contra o diretório de teste (glauth, `tests/ldap_fixture/`), mapeamento de
grupo -> perfil, provisionamento automático, e o portão duro "diretório fora do ar não derruba o login local".
Todo teste aqui é `lento` (sobe/derruba contêiner Docker); roda em `make e2e`, não em `make check-rapido`."""

import statistics
import time

import pytest

from tests.api.conftest import entrar, novo_cliente
from tests.api.ldap.conftest import USUARIOS, derrubar_servidor_ldap, religar_servidor_ldap

pytestmark = pytest.mark.lento


def _login_ldap(cliente, login, senha, inquilino="demo"):
    return cliente.post("/api/login/ldap", json={"inquilino": inquilino, "login": login, "senha": senha})


def test_bind_ok_cai_no_perfil_mapeado_pelo_grupo(provedor_ldap_demo, medida):
    casos = {"ana.silva": "admin", "bruno.souza": "editor", "carla.dias": "visualizador"}
    tempos = []
    for login, perfil_esperado in casos.items():
        c = novo_cliente()
        t0 = time.perf_counter()
        r = _login_ldap(c, login, USUARIOS[login])
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["usuario"]["login"] == login
        assert j["usuario"]["origem"] == "ldap"
        assert j["usuario"]["perfil"] == perfil_esperado, (login, j["usuario"]["perfil"])
        assert "senha_hash" not in r.text and USUARIOS[login] not in r.text
        cookie = r.headers["set-cookie"]
        assert cookie.startswith("plat_sessao=") and "HttpOnly" in cookie
        # cookie funciona de verdade: /api/eu com o mesmo cliente devolve o mesmo usuário
        r2 = c.get("/api/eu")
        assert r2.status_code == 200 and r2.json()["login"] == login
    medida("L0-08-d-ldap")(
        "latencia_login_ldap_ms", [round(t, 1) for t in tempos], "ms",
        "3x POST /api/login/ldap (bind de serviço + busca + bind do usuário + provisionamento + sessão)",
    )


def test_senha_errada_e_recusada_sem_derrubar_a_sessao_local(provedor_ldap_demo):
    r = _login_ldap(novo_cliente(), "ana.silva", "senha-completamente-errada")
    assert r.status_code == 401 and r.json()["erro"] == "credenciais_invalidas"
    assert "set-cookie" not in r.headers


def test_senha_vazia_nunca_tenta_bind_anonimo(provedor_ldap_demo):
    """Um LDAP mal configurado pode tratar bind com senha vazia como 'unauthenticated bind' (RFC 4513 §5.1.2)
    e aceitá-lo como se fosse êxito — a defesa é NUNCA tentar. `senha` teria de ter min_length>=1 no corpo;
    aqui manda só espaços, que passam o pydantic mas são rejeitados pela checagem própria do módulo."""
    r = _login_ldap(novo_cliente(), "ana.silva", "   ")
    assert r.status_code == 401 and r.json()["erro"] == "credenciais_invalidas"


def test_injecao_de_filtro_ldap_nao_autentica_ninguem(provedor_ldap_demo):
    """`*)(cn=*` sem escapar viraria um filtro sempre-verdadeiro (RFC 4515); escapado, não casa ninguém."""
    r = _login_ldap(novo_cliente(), "*)(cn=*", "qualquer-coisa")
    assert r.status_code == 401 and r.json()["erro"] == "credenciais_invalidas"


def test_grupo_nao_mapeado_recusa_com_mensagem_clara(provedor_ldap_demo, sessao_a):
    """Zera o mapa por um instante (perfil_padrao também None) e confere que o bind OK não vira sessão."""
    r = sessao_a.put("/api/org/ldap", json={**provedor_ldap_demo, "mapa_grupo_perfil": {}, "perfil_padrao": None})
    assert r.status_code == 200, r.text
    try:
        resposta = _login_ldap(novo_cliente(), "bruno.souza", USUARIOS["bruno.souza"])
        assert resposta.status_code == 403 and resposta.json()["erro"] == "sem_grupo_mapeado"
    finally:
        assert sessao_a.put("/api/org/ldap", json=provedor_ldap_demo).status_code == 200


def test_login_em_uso_local_nunca_e_sequestrado_pelo_ldap(provedor_ldap_demo, sessao_a):
    """Cria localmente um usuário com o MESMO login de um usuário do diretório de teste ('dora.lima' — conta
    reservada só para este teste, nunca logada via LDAP em outro teste deste arquivo) e confere que o bind
    LDAP (mesmo com a senha certa) nunca vira essa conta local. Usar um login já consumido por outro teste
    (ex. 'carla.dias', que vira ORIGEM='ldap' já no primeiro teste do arquivo) testaria a UNIQUE genérica de
    login, não a regra `login_em_uso_local` que é o ponto deste teste — por isso a conta dedicada."""
    # limpeza defensiva: uma rodada anterior que morreu entre criar e apagar não pode derrubar esta (idempotente)
    for u in sessao_a.get("/api/usuarios?limite=1000").json()["itens"]:
        if u["login"] == "dora.lima" and u["origem"] == "local":
            assert sessao_a.delete(f"/api/usuarios/{u['id']}").status_code == 204
    r = sessao_a.post(
        "/api/usuarios", json={"login": "dora.lima", "nome": "Conta local homônima", "perfil": "visualizador"}
    )
    assert r.status_code == 201, r.text
    usuario_local_id = r.json()["usuario"]["id"]
    try:
        resposta = _login_ldap(novo_cliente(), "dora.lima", USUARIOS["dora.lima"])
        assert resposta.status_code == 409 and resposta.json()["erro"] == "login_em_uso_local"
    finally:
        assert sessao_a.delete(f"/api/usuarios/{usuario_local_id}").status_code == 204


def test_diretorio_fora_do_ar_nao_derruba_o_login_local(provedor_ldap_demo, cred):
    derrubar_servidor_ldap()
    try:
        r = _login_ldap(novo_cliente(), "ana.silva", USUARIOS["ana.silva"])
        assert r.status_code == 503 and r.json()["erro"] == "ldap_indisponivel"
        # o login LOCAL (outra rota, outro caminho) segue respondendo normalmente
        login, senha = cred["demo"]
        r2 = entrar(novo_cliente(), "demo", login, senha)
        assert r2.status_code == 200 and r2.json()["ok"] is True, r2.text
    finally:
        religar_servidor_ldap()


def test_bind_repetido_com_senha_errada_bloqueia_como_o_login_local(provedor_ldap_demo):
    """Reaproveita bloqueio_tentativas/bloqueio_minutos do inquilino (padrão 5/15); a 6ª tentativa vira 423."""
    resultados = []
    for _ in range(6):
        r = _login_ldap(novo_cliente(), "bruno.souza", "errada-de-proposito")
        resultados.append(r.status_code)
    assert resultados[:5] == [401] * 5, resultados
    assert resultados[5] == 423, resultados


def test_importacao_em_massa_cria_desabilitado_e_ativa_no_primeiro_login(provedor_ldap_demo, sessao_a):
    grupo_dn = "ou=gg-plataforma-leitura,ou=groups," + provedor_ldap_demo["base_dn"]
    r = sessao_a.post(
        "/api/org/ldap/importar",
        json={"grupo_dn": grupo_dn, "atributo_membro": "memberOf", "atributo_login": "cn", "perfil": "visualizador"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["encontrados"] == 1  # só carla.dias está em gg-plataforma-leitura
    assert j["criados"] + j["ja_existentes"] == 1

    lista = sessao_a.get("/api/usuarios?limite=1000").json()["itens"]
    carla = next(u for u in lista if u["login"] == "carla.dias")
    assert carla["origem"] == "ldap"
    if j["criados"] == 1:
        assert carla["ativo"] is False, "importado deve nascer desabilitado até o primeiro login"

    resposta = _login_ldap(novo_cliente(), "carla.dias", USUARIOS["carla.dias"])
    assert resposta.status_code == 200, resposta.text

    lista2 = sessao_a.get("/api/usuarios?limite=1000").json()["itens"]
    carla2 = next(u for u in lista2 if u["login"] == "carla.dias")
    assert carla2["ativo"] is True, "o primeiro login bem-sucedido tem de ativar a conta importada"


def test_admin_config_nunca_devolve_a_senha_de_bind(sessao_a, provedor_ldap_demo):
    r = sessao_a.get("/api/org/ldap")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "bind_senha" not in j and "bind_senha_cifrada" not in j
    assert j["tem_bind_senha"] is True
    assert "Servico-ldap-0" not in r.text


def test_perfil_padrao_invalido_e_recusado(sessao_a, provedor_ldap_demo):
    r = sessao_a.put("/api/org/ldap", json={**provedor_ldap_demo, "perfil_padrao": "super-admin-que-nao-existe"})
    assert r.status_code == 422 and r.json()["erro"] == "validacao"


def test_organizacao_alheia_nao_configura_ldap_da_outra(sessao_b, sessao_a, provedor_ldap_demo):
    """Teste cruzado A/B do L0-02: `demo2` (B) nunca vê nem herda o provedor configurado para `demo` (A)."""
    r_b = sessao_b.get("/api/org/ldap")
    assert r_b.status_code == 200 and r_b.json() is None
    r_a = sessao_a.get("/api/org/ldap")
    assert r_a.status_code == 200 and r_a.json() is not None


def test_sem_privilegio_org_integracoes_toma_403(usuarios_a):
    c, _usuario, senha = usuarios_a.sessao("visualizador")
    r = c.get("/api/org/ldap")
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"


def test_mediana_login_ldap_abaixo_de_800ms(provedor_ldap_demo, medida):
    """Bind de serviço + busca + bind do usuário + upsert + auth_login + sessão, tudo contra um contêiner
    LOCAL (sem rede real): folga generosa (800 ms) porque o teste também mede o próprio glauth, não só o
    plat; serve para flagrar regressão grosseira (timeout mal configurado etc.), não para benchmark fino."""
    tempos = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = _login_ldap(novo_cliente(), "ana.silva", USUARIOS["ana.silva"])
        tempos.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    mediana = statistics.median(tempos)
    medida("L0-08-d-ldap")("mediana_5_logins_ldap_ms", round(mediana, 1), "ms", "mediana de 5x POST /api/login/ldap")
    assert mediana < 800, tempos
