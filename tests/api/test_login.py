"""Login (ADR 0002 seções 5-7, 16.3): todos os códigos da linha /login e /login/2fa; força bruta de senha
(5 erradas → 6ª CERTA = 423; desbloqueio pelo admin libera na hora), de TOTP (5 códigos errados = 423; replay = 401;
passo +10 = 401; recuperação usada 2× = 401); journal e log_acesso sem a senha/cookie/desafio; latencia_login_ms."""

import statistics
import time

import pytest

from app.auth import totp
from tests.api.conftest import entrar, ligar_2fa, novo_cliente


def test_provedores_publico_e_404_para_inexistente(cliente):
    r = cliente.get("/api/login/provedores?inquilino=demo")
    assert r.status_code == 200 and r.json() == {
        "inquilino": {"slug": "demo", "nome": "Inquilino de demonstração"},
        "provedores": [],
        "login_local": True,
    }
    assert cliente.get("/api/login/provedores?inquilino=nao-existe").status_code == 404
    assert cliente.get("/api/login/provedores").status_code == 422


def test_credenciais_invalidas_mesma_mensagem_para_usuario_e_inquilino_inexistentes(cliente, cred):
    login, senha = cred["demo"]
    respostas = [
        cliente.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha + "x"}),
        cliente.post("/api/login", json={"inquilino": "demo", "login": "nao-existe", "senha": senha}),
        cliente.post("/api/login", json={"inquilino": "nao-existe", "login": login, "senha": senha}),
    ]
    for r in respostas:
        assert r.status_code == 401 and r.json()["erro"] == "credenciais_invalidas", r.text
        assert "set-cookie" not in r.headers
    assert len({r.json()["mensagem"] for r in respostas}) == 1


def test_tempo_constante_usuario_inexistente_vs_senha_errada(cliente, usuarios_a, medida):
    """Sem HASH_FANTASMA o ramo 'inexistente' responderia em ~1 ms e o 'senha errada' em ~120 ms.
    Usa um usuário temporário (4 erros, abaixo do bloqueio) para não bloquear o admin de demonstração."""
    u, senha = usuarios_a.criar("visualizador")
    t_inex, t_err = [], []
    for _ in range(4):
        t0 = time.perf_counter()
        cliente.post("/api/login", json={"inquilino": "demo", "login": "zz-nao-existe", "senha": "Errada123"})
        t_inex.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        cliente.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha + "x"})
        t_err.append(time.perf_counter() - t0)
    m_inex, m_err = statistics.median(t_inex) * 1000, statistics.median(t_err) * 1000
    assert m_inex > 0.5 * m_err, (m_inex, m_err)
    medida("L0-02-tenant-auth")(
        "login_inexistente_vs_senha_errada_ms",
        [round(m_inex, 1), round(m_err, 1)],
        "ms",
        "mediana de 4 POST /api/login: usuário inexistente × senha errada (tempo constante)",
    )


def test_login_ok_cookie_e_objeto_usuario(cliente, cred, medida):
    login, senha = cred["demo"]
    c = novo_cliente()
    tempos = []
    for _ in range(3):
        t0 = time.perf_counter()
        r = c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha})
        tempos.append((time.perf_counter() - t0) * 1000)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True and j["usuario"]["login"] == login and j["usuario"]["perfil"] == "admin"
    assert j["usuario"]["inquilino"]["slug"] == "demo" and j["usuario"]["pendencias"] == []
    assert "membros.gerir" in j["usuario"]["privilegios"] and "senha_hash" not in r.text
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("plat_sessao=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=604800" in cookie
    assert statistics.median(tempos) < 400
    medida("L0-02-tenant-auth")(
        "latencia_login_ms",
        round(statistics.median(tempos), 1),
        "ms",
        "mediana de 3 POST /api/login com senha certa pelo TestClient (inclui pbkdf2 600k)",
    )
    c.post("/api/logout")


def test_cookie_secure_quando_https(cliente, cred):
    login, senha = cred["demo"]
    r = cliente.post(
        "/api/login", json={"inquilino": "demo", "login": login, "senha": senha}, headers={"X-Forwarded-Proto": "https"}
    )
    assert r.status_code == 200 and "Secure" in r.headers["set-cookie"]
    cliente.cookies.clear()


def test_inquilino_ou_login_com_caixa_e_espacos(cliente, cred):
    login, senha = cred["demo"]
    r = cliente.post("/api/login", json={"inquilino": " Demo ", "login": login.upper(), "senha": senha})
    assert r.status_code == 200 and r.json()["ok"] is True
    cliente.post("/api/logout")


def test_forca_bruta_de_senha_6a_certa_bloqueia_e_admin_desbloqueia(sessao_a, usuarios_a):
    c, u, senha = usuarios_a.sessao("visualizador")
    outro = novo_cliente()
    for i in range(5):
        r = outro.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": "Errada00" + str(i)})
        assert r.status_code == 401, (i, r.text)
    r = outro.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 423 and r.json()["erro"] == "bloqueado" and r.json()["detalhe"]["bloqueado_ate"], r.text
    assert "bloqueado até" in r.json()["mensagem"]
    # o evento de bloqueio existe; o usuário aparece bloqueado para o admin
    ev = sessao_a.get("/api/eventos?tipo=usuarios/falha_login&limite=5").json()["itens"]
    assert any(e["alvo_id"] == str(u["id"]) for e in ev)
    assert sessao_a.get(f"/api/usuarios/{u['id']}").json()["bloqueado_ate"] is not None
    assert sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear").status_code == 204
    r = outro.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 200 and r.json()["ok"] is True
    outro.post("/api/logout")


def test_usuario_desabilitado_e_inquilino_suspenso(sessao_a, sessao_plat, usuarios_a, cred):
    c, u, senha = usuarios_a.sessao("visualizador")
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"ativo": False}).status_code == 200
    assert c.get("/api/eu").status_code == 401  # sessões apagadas ao desabilitar
    r = novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 401 and r.json()["erro"] == "credenciais_invalidas"
    assert sessao_a.put(f"/api/usuarios/{u['id']}", json={"ativo": True}).status_code == 200
    # suspensão do inquilino demo2 pelo superadmin: login 503, sessão viva 401; reativação restaura
    inq = {t["slug"]: t for t in sessao_plat.get("/api/plataforma/inquilinos").json()}
    b = novo_cliente()
    assert entrar(b, "demo2", *cred["demo2"]).status_code == 200
    assert sessao_plat.post(f"/api/plataforma/inquilinos/{inq['demo2']['id']}/suspender").status_code == 204
    try:
        r = novo_cliente().post(
            "/api/login", json={"inquilino": "demo2", "login": cred["demo2"][0], "senha": cred["demo2"][1]}
        )
        assert r.status_code == 503 and r.json()["erro"] == "inquilino_suspenso"
        assert b.get("/api/eu").status_code == 401
    finally:
        assert sessao_plat.post(f"/api/plataforma/inquilinos/{inq['demo2']['id']}/reativar").status_code == 204
    assert b.get("/api/eu").status_code == 200
    b.post("/api/logout")


def test_2fa_fluxo_completo_replay_janela_recuperacao_e_forca_bruta(sessao_a, usuarios_a):
    c, u, senha = usuarios_a.sessao("editor")
    segredo, codigos = ligar_2fa(c)
    assert len(codigos) == 8
    assert sessao_a.get(f"/api/usuarios/{u['id']}").json()["totp_ativo"] is True
    # login agora exige o segundo passo; sem cookie no primeiro passo
    n = novo_cliente()
    r = n.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 200 and r.json() == {
        "ok": False,
        "exige_2fa": True,
        "desafio": r.json()["desafio"],
        "recuperacao_disponivel": True,
    }
    assert "set-cookie" not in r.headers
    desafio = r.json()["desafio"]
    # passo +10 fora da janela; desafio forjado = 410; código certo entra
    passo = totp.passo_atual()
    r = n.post("/api/login/2fa", json={"desafio": desafio, "codigo": totp.codigo(segredo, passo=passo + 10)})
    assert r.status_code == 401 and r.json()["erro"] == "codigo_invalido"
    assert n.post("/api/login/2fa", json={"desafio": "x" * 64, "codigo": "000000"}).status_code == 410
    certo = totp.codigo(segredo, passo=passo + 1)  # o passo atual foi gasto no confirmar; +1 está na janela
    r = n.post("/api/login/2fa", json={"desafio": desafio, "codigo": certo})
    assert r.status_code == 200 and r.json()["ok"] is True and "set-cookie" in r.headers, r.text
    assert n.get("/api/eu").status_code == 200
    # replay do mesmo código em novo login = 401; o desafio anterior foi zerado = 410
    n2 = novo_cliente()
    d2 = n2.post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha}).json()["desafio"]
    r = n2.post("/api/login/2fa", json={"desafio": d2, "codigo": certo})
    assert r.status_code == 401 and r.json()["erro"] == "codigo_invalido"
    assert n2.post("/api/login/2fa", json={"desafio": desafio, "codigo": certo}).status_code == 410
    # recuperação: vale uma vez
    r = n2.post("/api/login/2fa", json={"desafio": d2, "codigo_recuperacao": codigos[0]})
    assert r.status_code == 200 and r.json()["ok"] is True
    corpo = {"inquilino": "demo", "login": u["login"], "senha": senha}
    d3 = novo_cliente().post("/api/login", json=corpo).json()["desafio"]
    r = novo_cliente().post("/api/login/2fa", json={"desafio": d3, "codigo_recuperacao": codigos[0]})
    assert r.status_code == 401
    assert c.get("/api/eu").json()["codigos_recuperacao_restantes"] == 7
    # força bruta de TOTP: mais 4 erros no mesmo contador (já há 3: passo+10, replay, recuperação repetida) → 423
    # cada login com sucesso (por código e por recuperação) zerou o contador (auth_ok): depois do último sobra só a
    # recuperação repetida = 1 falha; mais 4 códigos errados = 5 = bloqueio; a 6ª tentativa é 423 mesmo com código certo
    for _ in range(4):
        novo_cliente().post("/api/login/2fa", json={"desafio": d3, "codigo": "000000"})
    r = novo_cliente().post("/api/login/2fa", json={"desafio": d3, "codigo": totp.codigo(segredo)})
    assert r.status_code == 423 and r.json()["erro"] == "bloqueado", r.text
    assert sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear").status_code == 204
    # admin desliga o 2FA: sessões caem; login volta a ser só senha
    assert sessao_a.post(f"/api/usuarios/{u['id']}/2fa/desativar").status_code == 204
    assert c.get("/api/eu").status_code == 401
    r = novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_2fa_precisa_de_codigo_ou_recuperacao(cliente):
    r = cliente.post("/api/login/2fa", json={"desafio": "abc"})
    assert r.status_code == 422


def test_logout_idempotente_e_cookie_morto(cred):
    login, senha = cred["demo"]
    c = novo_cliente()
    assert entrar(c, "demo", login, senha).status_code == 200
    cookie = c.cookies.get("plat_sessao")
    assert c.post("/api/logout").status_code == 204
    assert c.post("/api/logout").status_code == 204
    assert novo_cliente().post("/api/logout").status_code == 204
    r = novo_cliente().get("/api/eu", cookies={"plat_sessao": cookie})
    assert r.status_code == 401 and r.json()["erro"] == "sessao_expirada"


def test_segredos_nunca_no_log_de_acesso_nem_no_journal(sessao_a, cred, conexao_plat_app, capsys):
    from tests.api.test_rls import contexto, ids_por_slug

    login, senha = cred["demo"]
    c = novo_cliente()
    for _ in range(3):
        r = c.post(
            "/api/login?senha=colada&token=plat_" + "z" * 43, json={"inquilino": "demo", "login": login, "senha": senha}
        )
        assert r.status_code == 200
    cookie = c.cookies.get("plat_sessao")
    desafio_valor = "desafio-de-teste"
    c.get(f"/api/eu?desafio={desafio_valor}&codigo=123456")
    saida = capsys.readouterr().out
    for segredo in (senha, cookie, "plat_" + "z" * 43, desafio_valor, "123456"):
        assert segredo not in saida, segredo
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT rota FROM plat.log_acesso WHERE em > now() - interval '5 minutes'")
        rotas = " ".join(r["rota"] for r in cur.fetchall())
    for segredo in (senha, cookie, "plat_" + "z" * 43, desafio_valor, "123456", "colada"):
        assert segredo not in rotas, segredo
    assert "senha=%3Credigido%3E" in rotas
    conexao_plat_app.rollback()
    c.post("/api/logout")


@pytest.mark.lento
def test_bloqueio_expira_com_o_tempo(sessao_a, usuarios_a, monkeypatch):
    """PLAT_TESTE_BLOQUEIO_MIN=1 só em dev: a 7ª tentativa certa entra depois de 60 s."""
    monkeypatch.setenv("PLAT_TESTE_BLOQUEIO_MIN", "1")
    from app.auth import rotas_login

    original = rotas_login._falhou

    def falha_curta(request, ctx, usuario_id, politica, resultado):
        from dataclasses import replace

        return original(request, ctx, usuario_id, replace(politica, bloqueio_minutos=1), resultado)

    monkeypatch.setattr(rotas_login, "_falhou", falha_curta)
    c, u, senha = usuarios_a.sessao("visualizador")
    for i in range(5):
        novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": "Errada00" + str(i)})
    corpo = {"inquilino": "demo", "login": u["login"], "senha": senha}
    assert novo_cliente().post("/api/login", json=corpo).status_code == 423
    time.sleep(61)
    r = novo_cliente().post("/api/login", json={"inquilino": "demo", "login": u["login"], "senha": senha})
    assert r.status_code == 200 and r.json()["ok"] is True
