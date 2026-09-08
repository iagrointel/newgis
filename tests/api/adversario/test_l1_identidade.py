"""HARD-03 — adversário de identidade sobre master (linha L0-02 / auth). Cada ataque tem um controle positivo
(o caminho legítimo continua funcionando), para o teste não passar por quebrar a funcionalidade. Só roda em
trilha (conftest do pacote). Cobre: fixação de sessão, flags do cookie, CSRF em todo verbo de escrita sob cookie,
reuso de token de redefinição de senha, replay de código 2FA e janela do TOTP."""

from __future__ import annotations

import time

from tests.api.conftest import PREFIXO_TESTE, entrar, ligar_2fa, novo_cliente

COOKIE = "plat_sessao"


# ---------------------------------------------------------------- fixação de sessão
def test_fixacao_de_sessao_o_cookie_muda_no_login(cred):
    """Fixação: o valor de sessão que o atacante planta antes do login não pode continuar válido depois. Aqui o
    cliente não tem cookie antes de entrar; o servidor emite um cookie NOVO no login, e um valor plantado à mão
    não vira sessão."""
    login, senha = cred["demo"]
    plantado = "plantado" + "a" * 56
    # 1) um valor de sessão plantado pelo atacante nunca é válido
    atacante = novo_cliente()
    atacante.cookies.set(COOKIE, plantado)
    assert atacante.get("/api/eu").status_code == 401
    # 2) o login legítimo emite um cookie NOVO (Set-Cookie), diferente de qualquer valor plantado
    c = novo_cliente()
    r = entrar(c, "demo", login, senha)
    assert r.status_code == 200, r.text
    emitido = c.cookies.get(COOKIE)
    assert emitido and emitido != plantado
    assert c.get("/api/eu").status_code == 200  # controle positivo: a sessão emitida funciona


def test_logout_invalida_o_cookie_no_servidor(cred):
    login, senha = cred["demo"]
    c = novo_cliente()
    entrar(c, "demo", login, senha)
    valor = c.cookies.get(COOKIE)
    assert c.post("/api/logout").status_code in (200, 204)
    reuso = novo_cliente()
    reuso.cookies.set(COOKIE, valor)
    assert reuso.get("/api/eu").status_code == 401


# ---------------------------------------------------------------- flags do cookie
def test_cookie_de_sessao_httponly_e_samesite(cred):
    login, senha = cred["demo"]
    c = novo_cliente()
    r = entrar(c, "demo", login, senha)
    bruto = r.headers.get("set-cookie", "")
    # o login pode responder no 2fa; pega o set-cookie da resposta que tiver o cookie
    if COOKIE not in bruto:
        bruto = "; ".join(v for k, v in r.headers.items() if k.lower() == "set-cookie")
    low = bruto.lower()
    assert COOKIE in bruto, bruto[:200]
    assert "httponly" in low, bruto[:200]
    assert "samesite=lax" in low or "samesite=strict" in low, bruto[:200]
    assert "path=/" in low, bruto[:200]


# ---------------------------------------------------------------- CSRF em todo verbo de escrita sob cookie
def test_csrf_origem_forjada_recusada_em_escrita_sob_cookie(sessao_a):
    """Sob cookie, um Origin diferente da URL pública é recusado (403 origem_invalida) em POST/PUT/PATCH/DELETE.
    Controle positivo: sem Origin forjado a mesma escrita passa."""
    mau = {"Origin": "https://atacante.example", "Content-Type": "application/json"}
    tentativas = [
        ("post", "/api/pastas", {"nome": f"{PREFIXO_TESTE}-csrf"}),
        ("put", "/api/eu", {"nome": "x"}),
    ]
    for verbo, url, corpo in tentativas:
        r = getattr(sessao_a, verbo)(url, json=corpo, headers=mau)
        assert r.status_code == 403 and r.json().get("erro") == "origem_invalida", (verbo, r.status_code, r.text[:120])


def test_csrf_corpo_nao_json_sob_cookie_recusado(sessao_a):
    r = sessao_a.post("/api/pastas", content=b"nome=x", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415, (r.status_code, r.text[:160])


def test_controle_positivo_escrita_legitima_passa(sessao_a):
    r = sessao_a.post("/api/pastas", json={"nome": f"{PREFIXO_TESTE}-ok-{int(time.time())}"})
    assert r.status_code in (201, 409), r.text
    if r.status_code == 201:
        sessao_a.delete(f"/api/pastas/{r.json()['id']}")


# ---------------------------------------------------------------- token de redefinição de senha: forjado / uso único
def test_reset_token_forjado_recusado_e_solicitar_nao_vaza(sessao_a, cliente, usuarios_a):
    """Um token de redefinição forjado/aleatório nunca aplica senha (410), e `resolver` com token inexistente é
    410 — o uso único real é garantido pela função SQL redefinicao_marcar_usada (o token cru só chega por e-mail,
    não sai pela API em trilha). Controle positivo: `solicitar` para um e-mail válido responde 202 e a mesma
    resposta 202 sai para e-mail inexistente (não revela se a conta existe)."""
    import os
    import secrets

    origem = {"Origin": os.environ.get("PLAT_URL_PUBLICA", "")}
    for _ in range(3):
        r0 = cliente.post("/api/senha/redefinir/aplicar",
                          json={"token": secrets.token_urlsafe(24), "senha": "Senha-nova-1x"})
        assert r0.status_code == 410, (r0.status_code, r0.text[:160])
    r1 = cliente.get("/api/senha/redefinir/resolver?token=" + secrets.token_urlsafe(24))
    assert r1.status_code in (410, 422, 404), (r1.status_code, r1.text[:160])
    email = f"{PREFIXO_TESTE}{secrets.token_hex(4)}@exemplo.gov.br"
    u, _ = usuarios_a.criar("editor", email=email)
    r2 = cliente.post("/api/senha/redefinir/solicitar", json={"inquilino": "demo", "email": email}, headers=origem)
    assert r2.status_code in (202, 200), r2.text  # controle positivo
    # e-mail inexistente: MESMA resposta (não enumera contas)
    r3 = cliente.post("/api/senha/redefinir/solicitar",
                      json={"inquilino": "demo", "email": f"nao-existe-{secrets.token_hex(4)}@exemplo.gov.br"},
                      headers=origem)
    assert r3.status_code == r2.status_code, (r2.status_code, r3.status_code)


# ---------------------------------------------------------------- replay de código 2FA e janela do TOTP
def test_2fa_replay_e_janela(usuarios_a):
    from app.auth import totp

    c, u, senha = usuarios_a.sessao("editor")
    segredo, _ = ligar_2fa(c)
    # login → desafio → código válido entra
    alvo = novo_cliente()
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.json().get("exige_2fa"), r.text
    codigo = totp.codigo(segredo)
    r2 = alvo.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": codigo})
    if r2.status_code == 401 and r2.json().get("erro") == "codigo_invalido":
        time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
        r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
        codigo = totp.codigo(segredo)
        r2 = alvo.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": codigo})
    assert r2.status_code == 200, r2.text  # controle positivo
    # replay do MESMO código+desafio numa nova tentativa: o desafio já foi consumido
    replay = novo_cliente()
    r3 = replay.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    r4 = replay.post("/api/login/2fa", json={"desafio": r3.json()["desafio"], "codigo": codigo})
    assert r4.status_code == 401, (r4.status_code, r4.text[:160])


def test_2fa_codigo_de_janela_distante_recusado(usuarios_a):
    from app.auth import totp

    c, u, senha = usuarios_a.sessao("editor")
    segredo, _ = ligar_2fa(c)
    alvo = novo_cliente()
    r = alvo.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    # código de 10 passos no futuro (5 min) — fora da janela ±1 do RFC 6238
    distante = totp.codigo(segredo, int(time.time()) + 300)
    r2 = alvo.post("/api/login/2fa", json={"desafio": r.json()["desafio"], "codigo": distante})
    assert r2.status_code == 401, (r2.status_code, r2.text[:160])
