"""/api/eu (ADR 0002 seções 6.1, 6.3, 7.3, 14): objeto completo; PUT com campo não editável = 400; e-mail fora do
domínio = 422; troca de senha com histórico (5 últimas = 422 historico) e 12 senhas fracas com detalhe.regra;
2FA: iniciar/confirmar/desativar/códigos; segredo TOTP nunca em claro no banco (SELECT direto na coluna); token
não mexe em nada disso (403 so_sessao).

Item L0-02-g-perfil-usuario (auto-atendimento — distinto do L0-02-f-tela-usuarios, que é o ADMIN editando OUTRO
usuário): preferências próprias (idioma, unidades, formato de data, visibilidade) por PUT /api/eu, e foto de
perfil por POST/DELETE /api/eu/foto (mesmo adaptador de arquivo do L0-11, mesmo padrão de POST /api/org/logo).
Refutação do item: SVG com script como foto (tem de ser recodificada — na prática, recusada porque o Pillow
nunca abre SVG), e-mail de domínio fora da lista do PRÓPRIO inquilino, login/perfil/papel/ativo continuam fora
da whitelist do PUT."""

import base64
import io

import pytest
from PIL import Image

from app.auth import totp
from tests.api.conftest import com_token, ligar_2fa, novo_cliente


def _png(largura=64, altura=64, cor=(30, 90, 200)) -> bytes:
    im = Image.new("RGB", (largura, altura), cor)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()

# os exemplos de COMPOSIÇÃO têm 10 caracteres desde que o padrão da plataforma virou 10 (achado G1-b1): com 8
# reprovariam por `minimo` e a falta de letra ou de dígito nunca seria avaliada.
SENHAS_FRACAS = [
    ("", "minimo"),
    ("a1", "minimo"),
    ("abcdef1", "minimo"),
    ("1234567890", "composicao"),
    ("abcdefghij", "composicao"),
    ("          ", "composicao"),
    ("x" * 129 + "1", "maximo"),
    ("ãéíõú", "minimo"),
    ("1234567", "minimo"),
    ("abc def", "minimo"),
    ("AAAAAAAAAA", "composicao"),
    ("!!!!!!!!!!", "composicao"),
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
    assert j["inquilino"]["config_publica"]["auth"]["senha_min"] == 10  # padrão da plataforma (piso 8)
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


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("login", "outro-login"), ("perfil", "admin"), ("papel_id", 1), ("ativo", False), ("superadmin", True),
        ("foto_sha256", "0" * 64),  # tenta apontar a própria foto p/ um sha256 alheio sem passar pelo recorte
    ],
)
def test_put_eu_nunca_escala_acesso_nem_troca_login(usuarios_a, campo, valor):
    """Refutação do item L0-02-g: 'login novo no PUT' e qualquer campo de acesso próprio — a whitelist de
    `campos_json` (`_CAMPOS_EU`) recusa ANTES de tocar o banco (400), então não existe caminho de 'aceito e
    ignorado silenciosamente': o pedido inteiro é rejeitado e nada muda. `foto_sha256` também fica de fora da
    whitelist: a única forma de a coluna mudar é `POST /api/eu/foto`, que sempre recorta a imagem pelo Pillow —
    nunca um sha256 escrito à mão apontando para um objeto que o usuário não enviou."""
    c, u, _senha = usuarios_a.sessao("editor")
    r = c.put("/api/eu", json={"nome": u["nome"], campo: valor})
    assert r.status_code == 400 and r.json()["erro"] == "campo_nao_editavel" and campo in r.json()["detalhe"]
    depois = c.get("/api/eu").json()
    assert depois["login"] == u["login"] and depois["perfil"] == u["perfil"] and depois["ativo"] == u["ativo"]
    assert depois["superadmin"] == u["superadmin"] and depois["foto_url"] is None


def test_put_eu_email_fora_do_dominio_do_proprio_inquilino(sessao_a):
    """Portão do item: 'e-mail com domínio fora da lista recusado com mensagem'. Restringe os domínios do
    PRÓPRIO inquilino (demo) e confirma que a mensagem nomeia a lista — não é só o teste unitário de
    `email_permitido` (tests/unit/test_politica.py), é o caminho HTTP inteiro."""
    original = sessao_a.get("/api/org").json()
    from tests.api.test_org import _corpo

    try:
        corpo = _corpo(original)
        corpo["auth"] = {**original["auth"], "dominios_email": ["exemplo-permitido.com.br"]}
        assert sessao_a.put("/api/org", json=corpo).status_code == 200
        antes = sessao_a.get("/api/eu").json()["email"]
        r = sessao_a.put("/api/eu", json={"email": "gente@fora-da-lista.com"})
        assert r.status_code == 422 and r.json()["erro"] == "email_dominio", r.text
        assert r.json()["detalhe"]["dominios"] == ["exemplo-permitido.com.br"]
        assert sessao_a.get("/api/eu").json()["email"] == antes  # nada mudou
    finally:
        sessao_a.put("/api/org", json=_corpo(original))


def test_put_eu_preferencias_idioma_unidades_formato_visibilidade(usuarios_a):
    c, u, _senha = usuarios_a.sessao("editor")
    original = c.get("/api/eu").json()
    assert original["idioma_preferido"] == "pt-BR" and original["unidades"] == "metrico"
    assert original["formato_data"] == "dd/mm/aaaa" and original["visibilidade_perfil"] == "inquilino"
    novo = {
        "idioma_preferido": "en", "unidades": "imperial",
        "formato_data": "mm/dd/aaaa", "visibilidade_perfil": "privado",
    }
    r = c.put("/api/eu", json=novo)
    assert r.status_code == 200, r.text
    assert r.json()["idioma_preferido"] == "en" and r.json()["unidades"] == "imperial"
    assert r.json()["formato_data"] == "mm/dd/aaaa" and r.json()["visibilidade_perfil"] == "privado"
    relido = c.get("/api/eu").json()  # persistiu (nova requisição, novo Auth resolvido do zero)
    assert relido["idioma_preferido"] == "en" and relido["visibilidade_perfil"] == "privado"
    # nome não enviado neste PUT: continua o mesmo (não foi zerado)
    assert relido["nome"] == original["nome"]


@pytest.mark.parametrize(
    "campo,invalido",
    [
        ("idioma_preferido", "klingon"), ("unidades", "jarda"),
        ("formato_data", "dd-mm"), ("visibilidade_perfil", "publico"),
    ],
)
def test_put_eu_preferencias_invalidas_422(usuarios_a, campo, invalido):
    c, u, _senha = usuarios_a.sessao("visualizador")
    r = c.put("/api/eu", json={campo: invalido})
    assert r.status_code == 422 and r.json()["erro"] == "validacao" and r.json()["detalhe"]["campo"] == campo


def test_foto_enviar_ler_e_remover(usuarios_a):
    c, u, _senha = usuarios_a.sessao("editor")
    assert c.get("/api/eu").json()["foto_url"] is None
    r = c.post("/api/eu/foto", json={"conteudo": _b64(_png())})
    assert r.status_code == 200, r.text
    url = r.json()["foto_url"]
    assert url == c.get("/api/eu").json()["foto_url"]
    sha = url.split("/api/arquivos/", 1)[1].split("?", 1)[0]
    assert len(sha) == 64
    r_obj = c.get(url)
    assert r_obj.status_code == 200 and r_obj.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r_obj.content))
    assert im.size == (200, 200) and im.format == "PNG"
    r_del = c.delete("/api/eu/foto")
    assert r_del.status_code == 200 and r_del.json()["foto_url"] is None
    assert c.get("/api/eu").json()["foto_url"] is None


def test_foto_svg_com_script_e_recusada(usuarios_a):
    """Refutação do item: 'adversário envia SVG com script como foto'. O Pillow não sabe abrir SVG (não é um
    formato raster) — a rota recusa com 415 ANTES de qualquer gravação no Garage; não existe caminho em que o
    conteúdo do SVG chegue a ser servido de volta como se fosse uma imagem."""
    c, u, _senha = usuarios_a.sessao("visualizador")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script></svg>'
    r = c.post("/api/eu/foto", json={"conteudo": _b64(svg)})
    assert r.status_code == 415 and r.json()["erro"] == "formato_nao_aceito", r.text
    assert c.get("/api/eu").json()["foto_url"] is None


def test_foto_acima_de_1mb_recusada(usuarios_a):
    c, u, _senha = usuarios_a.sessao("visualizador")
    grande = b"\x00" * (1024 * 1024 + 1024)
    r = c.post("/api/eu/foto", json={"conteudo": _b64(grande)})
    assert r.status_code in (413, 422), r.status_code
    if r.status_code == 413:
        assert r.json()["erro"] == "foto_grande"
    assert c.get("/api/eu").json()["foto_url"] is None


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
        ("POST", "/api/eu/foto"),
        ("DELETE", "/api/eu/foto"),
        ("GET", "/api/tokens"),
        ("POST", "/api/tokens"),
    ):
        r = com_token(cliente, token_a["token"], metodo, url, json={})
        assert r.status_code == 403 and r.json()["erro"] == "so_sessao", (metodo, url, r.text)


def test_convites_lista_vazia_para_conta_nova(usuarios_a):
    c, u, _ = usuarios_a.sessao("visualizador")
    assert c.get("/api/eu/convites").json() == []
