"""/api/eu (ADR 0002 seções 6.1, 6.3, 7.3, 14): objeto completo; PUT com campo não editável = 400; e-mail fora do
domínio = 422; troca de senha com histórico (5 últimas = 422 historico) e 12 senhas fracas com detalhe.regra;
2FA: iniciar/confirmar/desativar/códigos; segredo TOTP nunca em claro no banco (SELECT direto na coluna); token
não mexe em nada disso (403 so_sessao)."""

import pytest

from app.auth import totp
from tests.api.conftest import com_token, ligar_2fa, novo_cliente

SENHAS_FRACAS = [
    ("", "minimo"),
    ("a1", "minimo"),
    ("abcdef1", "minimo"),
    ("12345678", "composicao"),
    ("abcdefgh", "composicao"),
    ("        ", "composicao"),
    ("x" * 129 + "1", "maximo"),
    ("ãéíõú", "minimo"),
    ("1234567", "minimo"),
    ("abc def", "minimo"),
    ("AAAAAAAA", "composicao"),
    ("!!!!!!!!", "composicao"),
]


def test_objeto_eu_sob_cookie(sessao_a):
    j = sessao_a.get("/api/eu").json()
    assert {
        "id",
        "login",
        "nome",
        "perfil",
        "papel",
        "privilegios",
        "superadmin",
        "ativo",
        "origem",
        "totp_ativo",
        "trocar_senha",
        "inquilino",
        "pendencias",
        "sessao",
    } <= set(j)
    assert j["superadmin"] is False and j["origem"] == "local" and "token" not in j
    assert j["inquilino"]["config_publica"]["auth"]["senha_min"] == 8
    assert set(j["sessao"]) == {"criado_em", "expira_em", "ociosa_ate", "ip"}
    assert "senha_hash" not in j and "totp_secret" not in j


def test_objeto_eu_sob_token(cliente, token_a):
    j = com_token(cliente, token_a["token"], "GET", "/api/eu").json()
    assert j["token"]["id"] == token_a["id"] and j["token"]["escopos"] == ["admin:inquilino"] and "sessao" not in j


def test_put_eu_campo_nao_editavel_e_dominio(sessao_a):
    r = sessao_a.put("/api/eu", json={"perfil": "editor"})
    assert r.status_code == 400 and r.json()["erro"] == "campo_nao_editavel"
    r = sessao_a.put("/api/eu", json={"nome": "Administrador demo", "email": "admin@demo.exemplo"})
    assert r.status_code == 200 and r.json()["email"] == "admin@demo.exemplo"


@pytest.fixture(scope="module")
def conta_fraca(usuarios_a):
    c, u, atual = usuarios_a.sessao("visualizador")
    return c, atual


@pytest.mark.parametrize("senha,regra", SENHAS_FRACAS)
def test_12_senhas_fracas_nomeiam_a_regra(conta_fraca, senha, regra):
    c, atual = conta_fraca
    r = c.put("/api/eu/senha", json={"atual": atual, "nova": senha})
    assert r.status_code == 422 and r.json()["erro"] == "senha_fraca" and r.json()["detalhe"]["regra"] == regra, r.text


def test_troca_de_senha_historico_e_sessoes(usuarios_a, cred):
    c, u, s0 = usuarios_a.sessao("editor")
    assert c.put("/api/eu/senha", json={"atual": "errada", "nova": "Nova-senha-1"}).status_code == 401
    assert c.put("/api/eu/senha", json={"atual": s0, "nova": u["login"]}).json()["detalhe"]["regra"] == "igual_login"
    # segunda sessão cai na troca; a atual continua
    from tests.api.conftest import entrar

    c2 = novo_cliente()
    assert entrar(c2, "demo", u["login"], s0).status_code == 200
    senhas = [s0] + [f"Senha-historico-{i}" for i in range(1, 6)]
    for anterior, nova in zip(senhas, senhas[1:], strict=False):
        assert c.put("/api/eu/senha", json={"atual": anterior, "nova": nova}).status_code == 204
    assert c2.get("/api/eu").status_code == 401 and c.get("/api/eu").status_code == 200
    atual = senhas[-1]
    for repetida in senhas[1:]:  # as 5 últimas (inclusive a atual) não voltam
        r = c.put("/api/eu/senha", json={"atual": atual, "nova": repetida})
        assert r.status_code == 422 and r.json()["detalhe"]["regra"] == "historico", repetida
    assert c.put("/api/eu/senha", json={"atual": atual, "nova": s0}).status_code == 204  # a 6ª para trás já pode
    ev = [e["tipo"] for e in usuarios_a.admin.get(f"/api/eventos?ator_id={u['id']}&limite=50").json()["itens"]]
    assert "usuarios/trocar_senha" in ev


def test_2fa_pela_conta(usuarios_a):
    c, u, senha = usuarios_a.sessao("editor")
    assert c.post("/api/eu/2fa/confirmar", json={"codigo": "000000"}).json()["erro"] == "nao_iniciado"
    r = c.post("/api/eu/2fa/iniciar", json={})
    assert r.status_code == 200 and set(r.json()) == {"segredo", "uri", "qr_svg"}
    segredo = r.json()["segredo"]
    assert r.json()["uri"].startswith(f"otpauth://totp/plat:demo/{u['login']}?secret=")
    assert r.json()["qr_svg"].startswith("<svg")
    assert c.post("/api/eu/2fa/confirmar", json={"codigo": "000000"}).status_code == 401
    r = c.post("/api/eu/2fa/confirmar", json={"codigo": totp.codigo(segredo)})
    assert r.status_code == 200 and len(r.json()["codigos_recuperacao"]) == 8
    assert c.post("/api/eu/2fa/iniciar", json={}).json()["erro"] == "ja_ativo"
    assert c.get("/api/eu").json()["totp_ativo"] is True
    assert c.post("/api/eu/2fa/codigos", json={"senha": "errada"}).status_code == 401
    r = c.post("/api/eu/2fa/codigos", json={"senha": senha})
    assert r.status_code == 200 and len(r.json()["codigos_recuperacao"]) == 8
    assert c.post("/api/eu/2fa/desativar", json={"senha": senha, "codigo": "000000"}).status_code == 401
    assert c.post("/api/eu/2fa/desativar", json={"senha": "errada", "codigo": totp.codigo(segredo)}).status_code == 401


def test_2fa_desativar_com_segredo_conhecido(usuarios_a):
    c, u, senha = usuarios_a.sessao("editor")
    segredo, codigos = ligar_2fa(c)
    passo = totp.passo_atual() + 1  # passo seguinte: nunca usado, dentro da janela ±1
    r = c.post("/api/eu/2fa/desativar", json={"senha": senha, "codigo": totp.codigo(segredo, passo=passo)})
    assert r.status_code == 204, r.text
    assert c.get("/api/eu").json()["totp_ativo"] is False
    assert c.post("/api/eu/2fa/desativar", json={"senha": senha, "codigo": "000000"}).json()["erro"] == "nao_ativo"


def test_totp_secret_nunca_em_claro_no_banco(usuarios_a, conexao_plat_app):
    """Portão L0-02-c: 'segredo nunca em claro no banco (SELECT mostra prefixo enc:)' — prova direta na coluna,
    não só na função de cifra (ADR 0002 seção 7)."""
    from tests.api.test_rls import contexto, ids_por_slug

    c, u, _senha = usuarios_a.sessao("visualizador")
    segredo, _codigos = ligar_2fa(c)
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT totp_secret FROM plat.usuario WHERE id = %s", (u["id"],))
        armazenado = cur.fetchone()["totp_secret"]
    conexao_plat_app.rollback()
    assert armazenado.startswith("enc:")
    assert segredo not in armazenado


def test_2fa_obrigatorio_na_plataforma_nao_se_desliga(sessao_plat, cred):
    from tests.api.conftest import totp_guardado

    segredo = totp_guardado("plataforma")
    r = sessao_plat.post("/api/eu/2fa/desativar", json={"senha": cred["plataforma"][1], "codigo": totp.codigo(segredo)})
    assert r.status_code == 409 and r.json()["erro"] == "2fa_obrigatorio"


def test_token_nao_mexe_em_conta(cliente, token_a):
    for metodo, url in (
        ("PUT", "/api/eu"),
        ("PUT", "/api/eu/senha"),
        ("GET", "/api/eu/sessoes"),
        ("POST", "/api/eu/2fa/iniciar"),
        ("GET", "/api/eu/convites"),
        ("GET", "/api/tokens"),
        ("POST", "/api/tokens"),
    ):
        r = com_token(cliente, token_a["token"], metodo, url, json={})
        assert r.status_code == 403 and r.json()["erro"] == "so_sessao", (metodo, url, r.text)


def test_convites_lista_vazia_para_conta_nova(usuarios_a):
    c, u, _ = usuarios_a.sessao("visualizador")
    assert c.get("/api/eu/convites").json() == []
