"""Funções SECURITY DEFINER (ADR 0002 seção 16.2), conexão plat_app: nenhuma com EXECUTE para PUBLIC; as chamadas
cruzadas (contexto de demo + usuário de demo2) levantam exceção; tenant_criar por GUC forjado = exceção;
evento_registrar sem contexto = exceção; plat_app sem INSERT/UPDATE/DELETE em log_acesso, evento, privilegio,
perfil_privilegio, evento_tipo; partições sem GRANT direto; RLS em toda partição."""

import psycopg2
import pytest

from tests.api.test_rls import contexto, ids_por_slug


def _cruzado(con):
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo2', 'admin')")
        u2 = cur.fetchone()["usuario_id"]
    contexto(con, ids["demo"], usuario_id=0)
    return ids, u2


def test_nenhuma_funcao_com_execute_para_public(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("""
            SELECT proname FROM pg_proc WHERE pronamespace = 'plat'::regnamespace
              AND (proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(proacl) a WHERE a::text LIKE '=%'))""")
        assert [r["proname"] for r in cur.fetchall()] == []
        cur.execute("SELECT count(*) AS n FROM pg_proc WHERE pronamespace = 'plat'::regnamespace")
        assert cur.fetchone()["n"] >= 30


@pytest.mark.parametrize(
    "chamada",
    [
        "SELECT plat.auth_sessao_criar(%s, 7, '127.0.0.1', 'teste')",
        "SELECT plat.auth_falha(%s, 5, 15, 15)",
        "SELECT plat.auth_ok(%s, '127.0.0.1')",
        "SELECT plat.sessoes_encerrar_usuario(%s, NULL)",
        "SELECT plat.auth_desafio_2fa_criar(%s)",
    ],
)
def test_funcao_com_contexto_de_outro_inquilino_levanta(conexao_plat_app, chamada):
    _, u2 = _cruzado(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="contexto_de_outro_inquilino"):
            cur.execute(chamada, (u2,))
    conexao_plat_app.rollback()


def test_log_registrar_com_contexto_divergente_levanta(conexao_plat_app):
    ids, _ = _cruzado(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="contexto_de_outro_inquilino"):
            cur.execute(
                "SELECT plat.log_registrar(%s, NULL, NULL, '1.1.1.1', 'GET', '/x', 200, 0, 1, 't', NULL)",
                (ids["demo2"],),
            )
    conexao_plat_app.rollback()


def test_tenant_criar_por_guc_forjado_levanta(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT id FROM plat.usuario WHERE superadmin LIMIT 1")  # sem contexto: 0 linhas (RLS)
        assert cur.fetchone() is None
        cur.execute("SELECT set_config('plat.usuario_id', '1', true), set_config('plat.tenant_id', '1', true)")
        with pytest.raises(psycopg2.errors.RaiseException, match="so_superadmin"):
            cur.execute("SELECT * FROM plat.tenant_criar('hash-invalido', 'zz-forjado', 'x', '{}', 'a', 'A', 'h')")
    conexao_plat_app.rollback()
    for fn in (
        "plat.tenant_listar('x')",
        "plat.tenant_suspender('x', 1, false)",
        "plat.plataforma_tenant_id('x', 'demo')",
    ):
        with conexao_plat_app.cursor() as cur:
            with pytest.raises(psycopg2.errors.RaiseException, match="so_superadmin"):
                cur.execute(f"SELECT * FROM {fn}")
        conexao_plat_app.rollback()


def test_evento_registrar_sem_contexto_levanta(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="evento_sem_contexto"):
            cur.execute("SELECT plat.evento_registrar('usuarios/entrar', 'usuario', '1', '{}', '1.1.1.1', 'r')")
    conexao_plat_app.rollback()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO plat.evento(tenant_id, tipo) VALUES (1, 'usuarios/entrar')",
        "INSERT INTO plat.log_acesso(tenant_id, metodo, rota, status, tempo_ms) VALUES (1, 'GET', '/x', 200, 1)",
        "INSERT INTO plat.privilegio VALUES ('x.y', 'x', 'y', false)",
        "INSERT INTO plat.perfil_privilegio VALUES ('admin', 'membros.ver')",
        "INSERT INTO plat.evento_tipo VALUES ('x/y', 'z')",
        "DELETE FROM plat.privilegio",
        "UPDATE plat.evento SET tipo = 'usuarios/sair'",
        "DELETE FROM plat.log_acesso",
    ],
)
def test_plat_app_sem_escrita_nas_tabelas_protegidas(conexao_plat_app, sql):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"])
    with conexao_plat_app.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(sql)
    conexao_plat_app.rollback()


def test_particoes_sem_acesso_direto_e_com_rls(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("""
            SELECT c.relname, c.relrowsecurity, has_table_privilege('plat_app', c.oid, 'SELECT') AS select_direto,
                   (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS politicas
            FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
            WHERE i.inhparent IN ('plat.log_acesso'::regclass, 'plat.evento'::regclass) ORDER BY 1""")
        particoes = cur.fetchall()
    assert len(particoes) >= 8
    for p in particoes:
        assert p["relrowsecurity"] and p["politicas"] >= 1 and p["select_direto"] is False, p


def test_privilegios_de_e_tem_respeitam_rls(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        u1 = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo2"], usuario_id=u1)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.privilegios_de(%s) AS p, plat.tem('membros.gerir') AS t", (u1,))
        r = cur.fetchone()
    assert r["p"] == [] and r["t"] is False  # admin de demo, visto do contexto de demo2: nada
    conexao_plat_app.rollback()
    contexto(conexao_plat_app, ids["demo"], usuario_id=u1)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT cardinality(plat.privilegios_de(%s)) AS n, plat.tem('membros.gerir') AS t", (u1,))
        r = cur.fetchone()
    assert r["n"] == 46 and r["t"] is True
    conexao_plat_app.rollback()
