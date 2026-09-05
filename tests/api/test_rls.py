"""RLS como plat_app (ADR 0001 seção 3.3): sem contexto 0 linhas; com contexto só o próprio inquilino;
INSERT com tenant_id de outro inquilino falha no WITH CHECK. Nunca conecta como postgres."""

import psycopg2
import pytest


def contexto(con, tenant_id, usuario_id=0, login="teste"):
    with con.cursor() as cur:
        cur.execute("SET search_path = plat, public")
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(tenant_id), str(usuario_id), login),
        )


def ids_por_slug(con):
    """Os ids dos inquilinos de demonstração vêm pela função SECURITY DEFINER (única que vê além do inquilino)."""
    ids = {}
    with con.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            assert r is not None, f"admin de {slug} não semeado (rode install.sh)"
            ids[slug] = r["tenant_id"]
    return ids


def test_sem_contexto_ve_zero_linhas(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        for tabela in ("tenant", "usuario", "sessao", "token_servico", "log_acesso"):
            cur.execute(f"SELECT count(*) AS n FROM plat.{tabela}")
            assert cur.fetchone()["n"] == 0, tabela


@pytest.mark.parametrize("slug", ["demo", "demo2"])
def test_com_contexto_ve_so_o_proprio_inquilino(conexao_plat_app, slug):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids[slug])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT slug FROM plat.tenant ORDER BY slug")
        assert [r["slug"] for r in cur.fetchall()] == [slug]
        cur.execute("SELECT DISTINCT tenant_id FROM plat.usuario")
        assert [r["tenant_id"] for r in cur.fetchall()] == [ids[slug]]


def test_insert_em_outro_inquilino_falha_no_with_check(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="row-level security"):
            cur.execute(
                "INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil) "
                "VALUES (%s, 'intruso', 'Intruso', 'x', 'visualizador')",
                (ids["demo2"],),
            )
    conexao_plat_app.rollback()


def test_insert_no_proprio_inquilino_passa_e_e_desfeito(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil) "
            "VALUES (%s, 'temporario', 'Temporário', 'x', 'visualizador') RETURNING id",
            (ids["demo"],),
        )
        assert cur.fetchone()["id"] > 0
    conexao_plat_app.rollback()


def test_contexto_e_local_a_transacao(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM plat.tenant")
        assert cur.fetchone()["n"] == 0


def test_log_acesso_so_por_funcao(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("INSERT INTO plat.log_acesso(tenant_id, metodo, rota, status, tempo_ms) "
                        "VALUES (%s, 'GET', '/x', 200, 1)", (ids["demo"],))
    conexao_plat_app.rollback()
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.log_registrar(%s, NULL, NULL, '127.0.0.1', 'GET', '/x', 200, 0, 1, 'teste', NULL)",
                    (ids["demo"],))
        cur.execute("SELECT count(*) AS n FROM plat.log_acesso WHERE rota = '/x'")
        assert cur.fetchone()["n"] == 1
    conexao_plat_app.rollback()
