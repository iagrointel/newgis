"""HARD-03 — adversário independente sobre master, linha L0 (identidade e acesso): itens L0-02-a, L0-02-b,
L0-02-c, L0-02-d e L0-02-g. Cada teste reproduz a refutação escrita em laco/estado.json ou um ataque próprio
(cruzamento de inquilino, escalada de privilégio, segredo em log). Um 2xx indevido é "confirmado" no laudo
(laco/handoffs/T4/ADVERSARIO-L0.md); o teste que passa registra "não reproduzido". Só roda em base de trilha
(tests/api/adversario/conftest.py recusa PLAT_SCHEMA=plat)."""

from __future__ import annotations

import logging
import secrets
import time

import pytest

from tests.api.catalogo.conftest import DADOS_POR_TIPO
from tests.api.conftest import PREFIXO_TESTE, com_token, entrar, ligar_2fa, novo_cliente

COOKIE = "plat_sessao"


def _como_inquilino(con, slug: str):
    """Cursor da conexão plat_app com o GUC de inquilino da transação corrente (RLS): o id vem da função
    SECURITY DEFINER plat.auth_login, a única que enxerga além do inquilino."""
    cur = con.cursor()
    cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
    tid = cur.fetchone()["tenant_id"]
    cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(tid),))
    return cur


def _cookie(cliente) -> str:
    valor = cliente.cookies.get(COOKIE)
    assert valor, "sessão sem cookie plat_sessao"
    return valor


def _cliente_com_cookie(valor: str):
    c = novo_cliente()
    c.cookies.set(COOKIE, valor)
    return c


# ---------------------------------------------------------------- L0-02-a login/sessão
def test_l0_02a_cookie_reusado_apos_logout_e_401(cred):
    login, senha = cred["demo"]
    c = novo_cliente()
    assert entrar(c, "demo", login, senha).status_code == 200
    valor = _cookie(c)
    assert c.post("/api/logout").status_code in (200, 204)
    r = _cliente_com_cookie(valor).get("/api/eu")
    assert r.status_code == 401, (r.status_code, r.text[:200])


def test_l0_02a_cookie_com_um_caractere_trocado_e_401(sessao_a):
    valor = _cookie(sessao_a)
    meio = len(valor) // 2
    trocado = valor[:meio] + ("0" if valor[meio] != "0" else "1") + valor[meio + 1:]
    assert trocado != valor
    r = _cliente_com_cookie(trocado).get("/api/eu")
    assert r.status_code == 401, (r.status_code, r.text[:200])
    # e o cookie certo continua valendo (a tentativa errada não derrubou a sessão legítima)
    assert sessao_a.get("/api/eu").status_code == 200


def test_l0_02a_cookie_de_demo_nao_abre_nada_de_demo2(sessao_a, sessao_b, ids):
    """Não há inquilino na URL nas rotas atuais (o inquilino vem da sessão); o cruzamento possível é por id de
    objeto: item, usuário e grupo de demo2 pedidos pela sessão de demo têm de sumir (404/403), nunca 200."""
    r = sessao_b.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO_TESTE} adv b", "dados": DADOS_POR_TIPO["mapa"]})
    assert r.status_code == 201, r.text
    item_b = r.json()["id"]
    try:
        for url in (f"/api/itens/{item_b}", f"/api/usuarios/{ids['b']['id']}"):
            r = sessao_a.get(url)
            assert r.status_code in (403, 404), (url, r.status_code, r.text[:200])
            r = sessao_a.put(url, json={"titulo": "x"} if "itens" in url else {"nome": "x"})
            assert r.status_code in (403, 404, 422), (url, r.status_code, r.text[:200])
            r = sessao_a.delete(url)
            assert r.status_code in (403, 404), (url, r.status_code, r.text[:200])
    finally:
        sessao_b.delete(f"/api/itens/{item_b}")


def test_l0_02a_200_logins_em_60s_nao_vazam_hash_nem_senha_no_log(cred, caplog, conexao_plat_app):
    """A refutação do item: 200 logins seguidos; nenhuma linha de log (o mesmo canal que vai ao journal) traz o
    hash pbkdf2 nem a senha em claro; e plat.log_acesso.rota também não."""
    login, senha = cred["demo"]
    caplog.set_level(logging.DEBUG)
    t0 = time.time()
    c = novo_cliente()
    for i in range(200):
        r = c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha if i % 2 else "errada-" + senha})
        assert r.status_code in (200, 401, 423, 429), r.text[:200]
    assert time.time() - t0 < 60, "200 logins levaram mais de 60 s (não é o que a refutação mede)"
    texto = "\n".join(rec.getMessage() for rec in caplog.records)
    assert senha not in texto
    assert "pbkdf2_sha256$" not in texto
    with _como_inquilino(conexao_plat_app, "demo") as cur:
        cur.execute("SELECT count(*) AS n FROM plat.log_acesso WHERE rota LIKE %s OR rota LIKE %s",
                    (f"%{senha}%", "%pbkdf2%"))
        assert cur.fetchone()["n"] == 0


# ---------------------------------------------------------------- L0-02-b política de senha e bloqueio
def test_l0_02b_bloqueio_por_usuario_nao_derruba_o_admin(usuarios_a, cred):
    _c, u, senha = usuarios_a.sessao("editor")
    slug = "demo"
    alvo = novo_cliente()
    codigos = []
    for _ in range(6):
        codigos.append(alvo.post("/api/login", json={"inquilino": slug, "login": u["login"], "senha": "errada-" + senha}).status_code)
    assert 423 in codigos, codigos
    r = alvo.post("/api/login", json={"inquilino": slug, "login": u["login"], "senha": senha})
    assert r.status_code == 423, (r.status_code, r.text[:200])
    assert "bloqueado" in r.text
    # o admin do MESMO inquilino continua entrando: bloqueio é por usuário, não por inquilino
    login, senha_adm = cred["demo"]
    assert entrar(novo_cliente(), slug, login, senha_adm).status_code == 200


def test_l0_02b_1000_senhas_em_200_logins_diferentes_nao_bloqueiam_o_inquilino(cred):
    """200 logins INEXISTENTES × 5 senhas: o contador é por usuário; o admin real entra ao fim."""
    c = novo_cliente()
    t0 = time.time()
    for i in range(200):
        for j in range(5):
            r = c.post("/api/login", json={"inquilino": "demo", "login": f"{PREFIXO_TESTE}nao{i}", "senha": f"x{j}"})
            assert r.status_code in (401, 429), r.text[:100]
    login, senha = cred["demo"]
    assert entrar(novo_cliente(), "demo", login, senha).status_code == 200
    assert time.time() - t0 < 180


def test_l0_02b_reutilizar_senha_anterior_e_recusado(usuarios_a):
    c, u, senha0 = usuarios_a.sessao("editor")
    senhas = [senha0]
    for i in range(3):
        nova = f"Senha-nova-{i}-" + secrets.token_hex(3)
        r = c.put("/api/eu/senha", json={"atual": senhas[-1], "nova": nova})
        assert r.status_code == 204, r.text
        senhas.append(nova)
    # volta para a 3ª anterior: histórico de 5 tem de recusar
    r = c.put("/api/eu/senha", json={"atual": senhas[-1], "nova": senhas[0]})
    assert r.status_code == 422, (r.status_code, r.text[:200])


def test_l0_02b_senha_igual_ao_login_e_curta_sao_recusadas(usuarios_a):
    c, u, senha = usuarios_a.sessao("editor")
    for nova in (u["login"], "Ab1", "a" * 200):
        r = c.put("/api/eu/senha", json={"atual": senha, "nova": nova})
        assert r.status_code == 422, (nova[:20], r.status_code, r.text[:200])


# ---------------------------------------------------------------- L0-02-c 2FA TOTP
def test_l0_02c_forca_bruta_de_codigo_bloqueia_e_replay_e_recusado(usuarios_a):
    from app.auth import totp

    c, u, senha = usuarios_a.sessao("editor")
    segredo, recuperacao = ligar_2fa(c)
    alvo = novo_cliente()
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 200 and r.json().get("exige_2fa"), r.text
    desafio = r.json()["desafio"]
    codigos = []
    for i in range(8):
        r2 = alvo.post("/api/login/2fa", json={"desafio": desafio, "codigo": f"{i:06d}"})
        codigos.append(r2.status_code)
        if r2.status_code in (423, 410):
            break
    assert 423 in codigos or 410 in codigos, f"8 códigos errados sem bloqueio: {codigos}"
    # depois do bloqueio, nem o código certo entra
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 423, (r.status_code, r.text[:200])
    # desbloqueia pelo admin para testar o replay
    assert usuarios_a.admin.post(f"/api/usuarios/{u['id']}/desbloquear").status_code in (200, 204)
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    desafio = r.json()["desafio"]
    codigo = totp.codigo(segredo)
    r_ok = alvo.post("/api/login/2fa", json={"desafio": desafio, "codigo": codigo})
    if r_ok.status_code == 401 and r_ok.json().get("erro") == "codigo_invalido":
        time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
        r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
        desafio = r.json()["desafio"]
        codigo = totp.codigo(segredo)
        r_ok = alvo.post("/api/login/2fa", json={"desafio": desafio, "codigo": codigo})
    assert r_ok.status_code == 200, r_ok.text[:200]
    # replay do MESMO código numa segunda sessão dentro dos 30 s
    outro = novo_cliente()
    r = outro.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    r2 = outro.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": codigo})
    assert r2.status_code == 401, (r2.status_code, r2.text[:200])


def test_l0_02c_codigo_com_relogio_5_min_adiantado_e_recusado(usuarios_a):
    from app.auth import totp

    c, u, senha = usuarios_a.sessao("editor")
    segredo, _ = ligar_2fa(c)
    alvo = novo_cliente()
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    desafio = r.json()["desafio"]
    adiantado = totp.codigo(segredo, int(time.time()) + 300) if _aceita_instante(totp) else None
    if adiantado is None:
        pytest.skip("app.auth.totp.codigo não aceita instante — refutação do relógio não reproduzível por aqui")
    r2 = alvo.post("/api/login/2fa", json={"desafio": desafio, "codigo": adiantado})
    assert r2.status_code == 401, (r2.status_code, r2.text[:200])


def _aceita_instante(totp) -> bool:
    import inspect

    return len(inspect.signature(totp.codigo).parameters) >= 2


def test_l0_02c_segredo_totp_nunca_em_claro_no_banco(usuarios_a, conexao_plat_app):
    c, u, _ = usuarios_a.sessao("editor")
    segredo, _ = ligar_2fa(c)
    with _como_inquilino(conexao_plat_app, "demo") as cur:
        cur.execute("SELECT totp_secret FROM plat.usuario WHERE id = %s", (u["id"],))
        guardado = cur.fetchone()["totp_secret"]
    assert guardado and segredo not in guardado and guardado.startswith("enc:"), guardado[:12]


# ---------------------------------------------------------------- L0-02-d token de serviço
def _token(sessao, **kw) -> dict:
    r = sessao.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-adv", "escopos": ["catalogo:ler"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_l0_02d_token_de_demo_nao_le_item_de_demo2(sessao_a, sessao_b, cliente):
    tok = _token(sessao_a)
    r = sessao_b.post("/api/itens", json={"tipo": "mapa", "titulo": f"{PREFIXO_TESTE} adv tok b", "dados": DADOS_POR_TIPO["mapa"]})
    item_b = r.json()["id"]
    try:
        r = com_token(cliente, tok["token"], "GET", f"/api/itens/{item_b}")
        assert r.status_code in (403, 404), (r.status_code, r.text[:200])
        r = com_token(cliente, tok["token"], "GET", "/api/itens?limite=200")
        assert r.status_code == 200
        assert item_b not in {i["id"] for i in r.json()["itens"]}
    finally:
        sessao_b.delete(f"/api/itens/{item_b}")
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_l0_02d_token_so_leitura_nao_escreve_e_hash_nunca_aparece_na_lista(sessao_a, cliente, conexao_plat_app):
    tok = _token(sessao_a)
    try:
        corpo = {"tipo": "mapa", "titulo": "x", "dados": DADOS_POR_TIPO["mapa"]}
        r = com_token(cliente, tok["token"], "POST", "/api/itens", json=corpo)
        assert r.status_code == 403, (r.status_code, r.text[:200])
        r = com_token(cliente, tok["token"], "DELETE", f"/api/tokens/{tok['id']}")
        assert r.status_code in (401, 403), (r.status_code, r.text[:200])
        lista = sessao_a.get("/api/tokens").text
        assert tok["token"] not in lista
        with _como_inquilino(conexao_plat_app, "demo") as cur:
            cur.execute("SELECT token_hash FROM plat.token_servico WHERE id = %s", (tok["id"],))
            h = cur.fetchone()["token_hash"]
        assert h not in lista and h != tok["token"]
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_l0_02d_token_expirado_e_revogado_sao_401(sessao_a, cliente):
    tok = _token(sessao_a, validade_dias=0)
    r = com_token(cliente, tok["token"], "GET", "/api/eu")
    assert r.status_code == 401, (r.status_code, r.text[:200])
    tok2 = _token(sessao_a)
    assert com_token(cliente, tok2["token"], "GET", "/api/eu").status_code == 200
    assert sessao_a.delete(f"/api/tokens/{tok2['id']}").status_code in (200, 204)
    r = com_token(cliente, tok2["token"], "GET", "/api/eu")
    assert r.status_code == 401 and "revogado" in r.text, (r.status_code, r.text[:200])


def test_l0_02d_referer_alterado_e_recusado(sessao_a, cliente):
    tok = _token(sessao_a, restricao={"referer": ["https://*.exemplo.gov.br"]})
    try:
        for ref in ("https://exemplo.gov.br.atacante.com/", "https://atacante.com/https://sig.exemplo.gov.br",
                    "https://sig.exemplo.gov.br.evil/", "http://sig.exemplo.gov.br/"):
            r = com_token(cliente, tok["token"], "GET", "/api/eu", headers={"Referer": ref})
            assert r.status_code == 401, (ref, r.status_code, r.text[:120])
        r = com_token(cliente, tok["token"], "GET", "/api/eu", headers={"Referer": "https://sig.exemplo.gov.br/mapa"})
        assert r.status_code == 200
    finally:
        sessao_a.delete(f"/api/tokens/{tok['id']}")


def test_l0_02d_token_pedido_por_editor_nao_ganha_escopo_admin(usuarios_a):
    c, _u, _s = usuarios_a.sessao("editor")
    r = c.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-esc", "escopos": ["admin:inquilino"]})
    assert r.status_code in (403, 422), (r.status_code, r.text[:200])


# ---------------------------------------------------------------- L0-02-g checagem de privilégio do papel
def test_l0_02g_ator_nao_atribui_papel_com_um_privilegio_a_mais_que_o_seu(sessao_a, usuarios_a):
    """Refutação do item, ao pé da letra: R2 = R1 + UM privilégio que o ator não tem. Como todo privilégio de
    gerir membros é administrativo (docs/PRIVILEGIOS.md), o ator é um admin de perfil com o papel R1 (subconjunto
    do teto admin) — R2 acrescenta papeis.gerir. O ator tenta dar R2 a outro usuário, a um usuário novo, em
    lote e a si mesmo; qualquer 2xx = refutado."""
    r1 = sessao_a.post("/api/papeis", json={"nome": f"{PREFIXO_TESTE}-r1",
                                             "privilegios": ["membros.gerir", "membros.papel", "conteudo.criar"]})
    assert r1.status_code == 201, r1.text
    r2 = sessao_a.post("/api/papeis", json={"nome": f"{PREFIXO_TESTE}-r2", "privilegios": [
        "membros.gerir", "membros.papel", "conteudo.criar", "papeis.gerir"]})
    assert r2.status_code == 201, r2.text
    try:
        c1, u1, _s1 = usuarios_a.sessao("admin", papel_id=r1.json()["id"])
        u2, _ = usuarios_a.criar("admin", papel_id=r1.json()["id"])
        r = c1.put(f"/api/usuarios/{u2['id']}", json={"papel_id": r2.json()["id"]})
        assert r.status_code == 403, (r.status_code, r.text[:200])
        r = c1.post("/api/usuarios", json={"login": f"{PREFIXO_TESTE}x{secrets.token_hex(3)}", "nome": "x",
                                         "perfil": "admin", "papel_id": r2.json()["id"]})
        assert r.status_code == 403, (r.status_code, r.text[:200])
        r = c1.post("/api/usuarios/lote", json={"ids": [u2["id"]], "acao": "papel", "papel_id": r2.json()["id"]})
        assert r.status_code in (403, 422), (r.status_code, r.text[:200])
        r = c1.put(f"/api/usuarios/{u1['id']}", json={"papel_id": r2.json()["id"]})
        assert r.status_code == 403, (r.status_code, r.text[:200])
        # e o caminho reverso: tirar o próprio papel (virar admin pleno) também não pode
        r = c1.put(f"/api/usuarios/{u1['id']}", json={"papel_id": None})
        assert r.status_code == 403, (r.status_code, r.text[:200])
    finally:
        for rid in (r2.json()["id"], r1.json()["id"]):
            sessao_a.delete(f"/api/papeis/{rid}")


def test_l0_02g_visualizador_nao_cria_usuario_nem_papel(usuarios_a):
    c, _u, _s = usuarios_a.sessao("visualizador")
    r = c.post("/api/usuarios", json={"login": f"{PREFIXO_TESTE}v{secrets.token_hex(3)}", "nome": "x",
                                     "perfil": "admin"})
    assert r.status_code == 403, (r.status_code, r.text[:200])
    r = c.post("/api/papeis", json={"nome": f"{PREFIXO_TESTE}-v", "privilegios": ["conteudo.criar"]})
    assert r.status_code == 403, (r.status_code, r.text[:200])
    eu = c.get("/api/eu").json()
    r = c.put(f"/api/usuarios/{eu['id']}", json={"perfil": "admin"})
    assert r.status_code == 403, (r.status_code, r.text[:200])
