"""Sessão (ADR 0002 seções 5, 16.5): cookie alterado = 401; ambíguo (cookie + Bearer) = 400; sob cookie, escrita
sem JSON = 415 e Origin estranha = 403; sessão ociosa expira (PLAT_TESTE_OCIOSA_S em dev); pendências fecham as
rotas fora de /api/eu; X-Plat-Inquilino só para superadmin."""

import time

from tests.api.conftest import entrar, novo_cliente


def test_cookie_alterado_em_um_caractere_e_401(cred):
    login, senha = cred["demo"]
    c = novo_cliente()
    assert entrar(c, "demo", login, senha).status_code == 200
    cookie = c.cookies.get("plat_sessao")
    alterado = ("0" if cookie[-1] != "0" else "1") + cookie[1:]
    r = novo_cliente().get("/api/eu", cookies={"plat_sessao": alterado})
    assert r.status_code == 401 and r.json()["erro"] == "sessao_expirada"
    assert novo_cliente().get("/api/eu", cookies={"plat_sessao": "lixo"}).status_code == 401
    assert novo_cliente().get("/api/eu").status_code == 401
    c.post("/api/logout")


def test_cookie_e_bearer_juntos_e_400(sessao_a, token_a):
    r = sessao_a.get("/api/eu", headers={"Authorization": f"Bearer {token_a['token']}"})
    assert r.status_code == 400 and r.json()["erro"] == "autenticacao_ambigua"


def test_escrita_sob_cookie_exige_json_e_origem_da_plataforma(sessao_a):
    r = sessao_a.post("/api/grupos", content="nome=x", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415 and r.json()["erro"] == "tipo_nao_aceito"
    r = sessao_a.post("/api/grupos", json={"nome": "x"}, headers={"Origin": "https://outro.exemplo.invalido"})
    assert r.status_code == 403 and r.json()["erro"] == "origem_invalida"
    from app.settings import settings

    r = sessao_a.get("/api/eu", headers={"Origin": settings.PLAT_URL_PUBLICA})
    assert r.status_code == 200


def test_pendencia_trocar_senha_fecha_o_resto(usuarios_a):
    u, temporaria = usuarios_a.criar("editor")
    c = novo_cliente()
    r = entrar(c, "demo", u["login"], temporaria)
    assert r.status_code == 200 and r.json()["usuario"]["pendencias"] == ["trocar_senha"]
    r = c.get("/api/grupos")
    assert r.status_code == 403 and r.json()["erro"] == "pendencia" and r.json()["detalhe"] == ["trocar_senha"]
    assert c.get("/api/eu").status_code == 200
    # token criado com pendência não funciona (nem a criação: /api/tokens está fora da lista)
    assert c.post("/api/tokens", json={"nome": "x", "escopos": ["catalogo:ler"]}).status_code == 403
    r = c.put("/api/eu/senha", json={"atual": temporaria, "nova": "Senha-nova-2026"})
    assert r.status_code == 204
    assert c.get("/api/eu").json()["pendencias"] == [] and c.get("/api/grupos").status_code == 200


def test_x_plat_inquilino_so_superadmin(sessao_a, sessao_plat):
    r = sessao_a.get("/api/usuarios", headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 403 and r.json()["erro"] == "so_superadmin"
    r = sessao_plat.get("/api/usuarios", headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 200 and all(u["login"] for u in r.json()["itens"])
    r = sessao_plat.get("/api/grupos", headers={"X-Plat-Inquilino": "demo2"})
    assert r.status_code == 400 and r.json()["erro"] == "cabecalho_nao_aceito"
    r = sessao_plat.get("/api/usuarios", headers={"X-Plat-Inquilino": "nao-existe"})
    assert r.status_code == 404


def test_sessoes_listar_e_revogar(usuarios_a):
    """Usuário temporário: ?outras=1 apaga as outras sessões DO MESMO usuário, e a fixture da suíte é o admin."""
    c1, u, senha = usuarios_a.sessao("visualizador")
    c2 = novo_cliente()
    assert entrar(c2, "demo", u["login"], senha).status_code == 200
    lista = c1.get("/api/eu/sessoes").json()
    assert sum(s["atual"] for s in lista) == 1 and len(lista) == 2
    outra = next(s for s in lista if not s["atual"])
    assert len(outra["id"]) == 12
    assert c1.delete(f"/api/eu/sessoes/{outra['id']}").status_code == 204
    assert c1.delete(f"/api/eu/sessoes/{outra['id']}").status_code == 404
    assert c2.get("/api/eu").status_code == 401 and c1.get("/api/eu").status_code == 200
    c3 = novo_cliente()
    assert entrar(c3, "demo", u["login"], senha).status_code == 200
    assert c1.delete("/api/eu/sessoes?outras=1").status_code == 204
    assert c3.get("/api/eu").status_code == 401 and c1.get("/api/eu").status_code == 200
    assert c1.delete("/api/eu/sessoes").status_code == 400


def test_sessao_ociosa_expira(cred, monkeypatch, conexao_plat_app):
    """PLAT_TESTE_OCIOSA_S=2 (dev): sem uso por 2 s a sessão morre; o expurgo a remove do banco."""
    monkeypatch.setenv("PLAT_TESTE_OCIOSA_S", "2")
    login, senha = cred["demo"]
    c = novo_cliente()
    assert entrar(c, "demo", login, senha).status_code == 200
    assert c.get("/api/eu").status_code == 200
    time.sleep(2.5)
    r = c.get("/api/eu")
    assert r.status_code == 401 and r.json()["erro"] == "sessao_expirada"
    monkeypatch.delenv("PLAT_TESTE_OCIOSA_S")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.sessoes_expurgar() AS n")
        assert cur.fetchone()["n"] >= 0
    conexao_plat_app.rollback()


def test_sessao_de_demo_nao_serve_para_demo2(sessao_a, ids):
    r = sessao_a.get("/api/eu?inquilino=demo2")
    assert r.status_code == 200 and r.json()["inquilino"]["slug"] == "demo"
    assert sessao_a.get(f"/api/usuarios/{ids['b']['id']}").status_code == 404
