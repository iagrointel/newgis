"""Conexão TCP como plat_app: prova a linha no pg_hba.conf, a identidade da role e a ausência de posse e de
BYPASSRLS (ADR 0001 seção 3.1)."""


def test_conexao_tcp_como_plat_app(conexao_plat_app, env):
    assert "127.0.0.1" in env["PLAT_DSN"], "o DSN precisa ser TCP para provar o pg_hba"
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT current_user AS u, host(inet_server_addr()) AS addr")
        r = cur.fetchone()
    assert r["u"] == "plat_app"
    assert r["addr"] == "127.0.0.1"


def test_plat_app_nao_e_dona_de_tabela_do_schema(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname = 'plat'")
        total = cur.fetchone()["n"]
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'plat' AND tableowner = 'plat_app'")
        proprias = [r["tablename"] for r in cur.fetchall()]
    assert total >= 6
    assert proprias == []


def test_plat_app_sem_bypassrls_nem_superusuario(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT rolbypassrls, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles "
                    "WHERE rolname = 'plat_app'")
        r = cur.fetchone()
    assert r is not None
    assert r["rolbypassrls"] is False
    assert r["rolsuper"] is False
    assert r["rolcreaterole"] is False and r["rolcreatedb"] is False


def test_extensoes_postgis_e_pgcrypto(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'pgcrypto') ORDER BY 1")
        assert [r["extname"] for r in cur.fetchall()] == ["pgcrypto", "postgis"]


def test_versao_migracao_e_so_leitura_para_plat_app(conexao_plat_app):
    import psycopg2

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.versao_migracao")
        assert cur.fetchone()["n"] >= 2
        try:
            cur.execute("INSERT INTO plat.versao_migracao(nome, sha256, duracao_ms) VALUES ('999_teste', 'x', 0)")
        except psycopg2.errors.InsufficientPrivilege:
            conexao_plat_app.rollback()
        else:
            conexao_plat_app.rollback()
            raise AssertionError("plat_app conseguiu escrever em versao_migracao")
