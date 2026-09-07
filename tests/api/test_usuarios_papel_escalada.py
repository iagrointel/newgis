"""Os seis caminhos de escalada de privilégio do ALERTA-1 (item L0-02-g-checagem-privilegio-papel-id).

O laudo de 07/09/2026 mediu, contra master, seis chamadas em que um administrador de perfil restrito por um
papel personalizado concedia — a outro ou a si mesmo — privilégios que ele próprio não tinha. As seis
respondiam 2xx. Este arquivo repete as seis ao pé da letra e exige 403 com o erro nomeado
`privilegio_proprio_insuficiente`, mais o controle positivo: o administrador pleno continua fazendo tudo.

Montagem do laudo: papel R1 = {membros.gerir, membros.papel, conteudo.criar}; R2 = R1 + {papeis.gerir}. O ator
é um administrador de perfil com R1, e por isso passa pelo portão de privilégio (`membros.papel`) — o que o
barra é a conferência de conjunto, não o portão.
"""

import secrets

import pytest

from tests.api.conftest import InquilinoTemporario, entrar, novo_cliente

R1 = ["membros.gerir", "membros.papel", "conteudo.criar"]
R2 = [*R1, "papeis.gerir"]  # UM privilégio a mais que o ator tem


def _login() -> str:
    return f"zt{secrets.token_hex(4)}"


def _erro(resposta) -> str:
    return resposta.json().get("erro", "")


def _criar_usuario(admin, perfil, papel_id):
    r = admin.post(
        "/api/usuarios", json={"login": _login(), "nome": "Alvo do laudo", "perfil": perfil, "papel_id": papel_id}
    )
    assert r.status_code == 201, r.text
    return r.json()["usuario"], r.json()["senha_temporaria"]


@pytest.fixture(scope="module")
def alerta(sessao_plat):
    """Inquilino descartável com os papéis R1/R2, o ator (admin restrito por R1) e os alvos do laudo."""
    inq = InquilinoTemporario(sessao_plat)
    try:
        papeis = {}
        for nome, privs in (("r1", R1), ("r2", R2)):
            r = inq.admin.post("/api/papeis", json={"nome": f"zt-{nome}-{secrets.token_hex(2)}", "privilegios": privs})
            assert r.status_code == 201, r.text
            papeis[nome] = r.json()["id"]

        ator_u, temporaria = _criar_usuario(inq.admin, "admin", papeis["r1"])
        ator = novo_cliente()
        assert entrar(ator, inq.slug, ator_u["login"], temporaria).status_code == 200
        assert ator.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-do-ator-1x"}).status_code == 204

        alvo_admin, _ = _criar_usuario(inq.admin, "admin", papeis["r1"])
        alvo_editor, _ = _criar_usuario(inq.admin, "editor", None)
        yield {
            "inq": inq,
            "ator": ator,
            "ator_id": ator_u["id"],
            "alvo_admin": alvo_admin["id"],
            "alvo_editor": alvo_editor["id"],
            "papeis": papeis,
        }
    finally:
        inq.apagar()


def _nega(resposta):
    assert resposta.status_code == 403, (resposta.status_code, resposta.text[:300])
    assert _erro(resposta) == "privilegio_proprio_insuficiente", resposta.text[:300]
    assert "papeis.gerir" in resposta.json()["detalhe"], resposta.text[:300]


# ------------------------------------------------------- os seis caminhos, na ordem da tabela do ALERTA-1
def test_caminho_1_put_papel_mais_amplo_em_outro(alerta):
    """1. PUT /api/usuarios/<alvo> {"papel_id": R2} — no laudo, 200 e o alvo ganhava papeis.gerir."""
    _nega(alerta["ator"].put(f"/api/usuarios/{alerta['alvo_admin']}", json={"papel_id": alerta["papeis"]["r2"]}))


def test_caminho_2_post_usuario_com_papel_mais_amplo(alerta):
    """2. POST /api/usuarios {perfil: admin, papel_id: R2} — no laudo, 201."""
    _nega(
        alerta["ator"].post(
            "/api/usuarios",
            json={"login": _login(), "nome": "Novo", "perfil": "admin", "papel_id": alerta["papeis"]["r2"]},
        )
    )


def test_caminho_3_lote_com_papel_mais_amplo(alerta):
    """3. POST /api/usuarios/lote {acao: papel, papel_id: R2} — no laudo, 200 {"alterados": 1}.

    Agora o lote confere antes de alterar qualquer alvo e recusa o pedido inteiro; nada é alterado."""
    _nega(
        alerta["ator"].post(
            "/api/usuarios/lote",
            json={"ids": [alerta["alvo_admin"]], "acao": "papel", "papel_id": alerta["papeis"]["r2"]},
        )
    )
    depois = alerta["inq"].admin.get(f"/api/usuarios/{alerta['alvo_admin']}").json()
    assert depois["papel_id"] == alerta["papeis"]["r1"], depois


def test_caminho_4_put_papel_mais_amplo_em_si_mesmo(alerta):
    """4. PUT /api/usuarios/<eu> {"papel_id": R2} — no laudo, 200."""
    _nega(alerta["ator"].put(f"/api/usuarios/{alerta['ator_id']}", json={"papel_id": alerta["papeis"]["r2"]}))
    assert "papeis.gerir" not in alerta["ator"].get("/api/eu").json()["privilegios"]


def test_caminho_5_ator_zera_o_proprio_papel(alerta):
    """5. PUT /api/usuarios/<eu> {"papel_id": null} — no laudo, 200 e o ator virava admin pleno."""
    r = alerta["ator"].put(f"/api/usuarios/{alerta['ator_id']}", json={"papel_id": None})
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text[:300]
    privilegios = alerta["ator"].get("/api/eu").json()["privilegios"]
    assert sorted(privilegios) == sorted(R1), privilegios


def test_caminho_6_promove_editor_a_admin_pleno(alerta):
    """6. PUT /api/usuarios/<editor> {perfil: admin, papel_id: null} — no laudo, 200."""
    r = alerta["ator"].put(f"/api/usuarios/{alerta['alvo_editor']}", json={"perfil": "admin", "papel_id": None})
    assert r.status_code == 403 and _erro(r) == "privilegio_proprio_insuficiente", r.text[:300]
    depois = alerta["inq"].admin.get(f"/api/usuarios/{alerta['alvo_editor']}").json()
    assert depois["perfil"] == "editor", depois


# ------------------------------------------------------- controle positivo: a regra é teto, não proibição
def test_ator_restrito_ainda_concede_o_que_tem(alerta):
    """Conceder o PRÓPRIO papel continua permitido — sem isso a regra teria matado a delegação."""
    r = alerta["ator"].post(
        "/api/usuarios",
        json={"login": _login(), "nome": "Delegado", "perfil": "admin", "papel_id": alerta["papeis"]["r1"]},
    )
    assert r.status_code == 201, r.text
    novo = r.json()["usuario"]["id"]
    assert alerta["ator"].put(f"/api/usuarios/{novo}", json={"papel_id": alerta["papeis"]["r1"]}).status_code == 200
    lote = alerta["ator"].post(
        "/api/usuarios/lote", json={"ids": [novo], "acao": "papel", "papel_id": alerta["papeis"]["r1"]}
    )
    assert lote.status_code == 200 and lote.json()["alterados"] == 1, lote.text
    assert alerta["inq"].admin.delete(f"/api/usuarios/{novo}").status_code == 204


def test_administrador_pleno_continua_fazendo_os_seis(alerta):
    """O admin pleno do inquilino (sem papel) percorre os seis caminhos e nenhum é barrado."""
    admin = alerta["inq"].admin
    alvo, _ = _criar_usuario(admin, "admin", alerta["papeis"]["r1"])
    editor, _ = _criar_usuario(admin, "editor", None)
    try:
        assert admin.put(f"/api/usuarios/{alvo['id']}", json={"papel_id": alerta["papeis"]["r2"]}).status_code == 200
        r = admin.post(
            "/api/usuarios",
            json={"login": _login(), "nome": "Pleno cria", "perfil": "admin", "papel_id": alerta["papeis"]["r2"]},
        )
        assert r.status_code == 201, r.text
        criado = r.json()["usuario"]["id"]
        lote = admin.post(
            "/api/usuarios/lote", json={"ids": [alvo["id"]], "acao": "papel", "papel_id": alerta["papeis"]["r2"]}
        )
        assert lote.status_code == 200 and lote.json()["alterados"] == 1, lote.text
        assert admin.put(f"/api/usuarios/{alvo['id']}", json={"papel_id": None}).status_code == 200
        assert admin.put(f"/api/usuarios/{editor['id']}", json={"perfil": "admin", "papel_id": None}).status_code == 200
        assert admin.delete(f"/api/usuarios/{criado}").status_code == 204
    finally:
        for uid in (alvo["id"], editor["id"]):
            admin.delete(f"/api/usuarios/{uid}")
