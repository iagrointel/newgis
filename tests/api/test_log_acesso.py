"""Middleware de log_acesso (ADR 0002 seção 9.1): GET /api/eu com cookie e com token geram linha com usuario_id/
token_id, ip, bytes > 0; /saude, /api/versao e / não geram; 401/403/404 em /api/ geram; resultado do login;
medida custo_log_acesso_ms."""

import statistics
import time

from tests.api.conftest import com_token
from tests.api.test_rls import contexto, ids_por_slug


def _linhas(con, slug, **filtros):
    con.rollback()
    ids = ids_por_slug(con)
    contexto(con, ids[slug])
    onde = " AND ".join(f"{k} IS NULL" if v is None else f"{k} = %s" for k, v in filtros.items()) or "true"
    with con.cursor() as cur:
        cur.execute(
            f"SELECT * FROM plat.log_acesso WHERE em > now() - interval '2 minutes' AND {onde} ORDER BY em DESC",
            [v for v in filtros.values() if v is not None],
        )
        linhas = cur.fetchall()
    con.rollback()
    return linhas


def test_cookie_e_token_geram_linha_com_ip_rota_bytes(sessao_a, token_a, cliente, conexao_plat_app, ids):
    assert sessao_a.get("/api/eu").status_code == 200
    assert com_token(cliente, token_a["token"], "GET", "/api/eu").status_code == 200
    por_cookie = _linhas(conexao_plat_app, "demo", usuario_id=ids["a"]["id"], rota="/api/eu", token_id=None)
    assert por_cookie and por_cookie[0]["token_id"] is None and por_cookie[0]["bytes"] > 0 and por_cookie[0]["ip"]
    assert por_cookie[0]["metodo"] == "GET" and por_cookie[0]["status"] == 200 and por_cookie[0]["tempo_ms"] >= 0
    por_token = _linhas(conexao_plat_app, "demo", token_id=token_a["id"])
    assert por_token and por_token[0]["usuario_id"] == ids["a"]["id"] and por_token[0]["bytes"] > 0


def test_rotas_excluidas_nao_geram_linha(cliente, sessao_a, conexao_plat_app):
    antes = len(_linhas(conexao_plat_app, "demo"))
    for rota in ("/saude", "/api/versao", "/", "/api/docs", "/api/openapi.json", "/entrar"):
        assert sessao_a.get(rota).status_code == 200, rota
    assert len(_linhas(conexao_plat_app, "demo")) == antes


def test_401_403_404_em_api_geram_linha(sessao_a, cliente, conexao_plat_app, ids):
    assert cliente.get("/api/usuarios").status_code == 401
    assert sessao_a.get("/api/plataforma/inquilinos").status_code == 404
    assert sessao_a.get("/api/usuarios/999999").status_code == 404
    linhas = _linhas(conexao_plat_app, "demo", rota="/api/usuarios/999999")
    assert linhas and linhas[0]["status"] == 404 and linhas[0]["usuario_id"] == ids["a"]["id"]
    linhas = _linhas(conexao_plat_app, "demo", rota="/api/plataforma/inquilinos")
    assert linhas and linhas[0]["status"] == 404


def test_resultado_do_login_e_logout(cred, conexao_plat_app):
    from tests.api.conftest import novo_cliente

    login, senha = cred["demo"]
    c = novo_cliente()
    assert c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha + "x"}).status_code == 401
    assert c.post("/api/login", json={"inquilino": "demo", "login": login, "senha": senha}).status_code == 200
    assert c.post("/api/logout").status_code == 204
    assert c.post("/api/login", json={"inquilino": "nao-existe", "login": "x", "senha": "y"}).status_code == 401
    resultados = [x["resultado"] for x in _linhas(conexao_plat_app, "demo", rota="/api/login")[:2]]
    assert resultados == ["ok", "senha"]
    assert _linhas(conexao_plat_app, "demo", rota="/api/logout")[0]["resultado"] == "logout"


def test_custo_do_log_acesso(sessao_a, medida, monkeypatch):
    """Diferença entre GET /api/eu com o log ligado e com a gravação desligada (mesma rota, mesma sessão)."""
    from app.auth import middleware

    def mediana():
        tempos = []
        for _ in range(30):
            t0 = time.perf_counter()
            assert sessao_a.get("/api/eu").status_code == 200
            tempos.append((time.perf_counter() - t0) * 1000)
        return statistics.median(tempos)

    com = mediana()
    monkeypatch.setattr(middleware, "gravar_log_acesso", lambda *a, **k: None)
    sem = mediana()
    monkeypatch.undo()
    custo = round(max(com - sem, 0), 2)
    medida("L0-02-tenant-auth")(
        "custo_log_acesso_ms",
        custo,
        "ms",
        "mediana de 30 GET /api/eu com log_registrar menos mediana de 30 sem (TestClient)",
    )
    assert custo < 20, custo
