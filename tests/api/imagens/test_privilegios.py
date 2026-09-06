"""Cláusulas 1 e 2 do item L1-01-a: `pypgstac migrate` aplicado com a versão registrada, e `plat_app`
(nesta trilha, `plat_tpgstac_app`) só com `pgstac_read`/`pgstac_ingest`, nunca `pgstac_admin`."""


def test_pgstac_schema_instalado_com_migrations_table(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT to_regclass('pgstac.collections') IS NOT NULL AS ok")
        assert cur.fetchone()["ok"] is True
        cur.execute("SELECT version FROM pgstac.migrations ORDER BY datetime DESC LIMIT 1")
        r = cur.fetchone()
        assert r is not None and r["version"], "pgstac sem versão migrada"


def test_versao_do_pgstac_registrada_na_trilha(conexao_plat_app):
    """`db/pgstac_instalar.sh` registra `pgstac-migrate-<versão>` em `<schema>.versao_migracao`, o MESMO
    lugar/formato das migrações .sql comuns (nunca uma tabela nova só para isto). O literal `plat.` abaixo
    é reescrito para o schema da trilha por `CursorSchemaAmbiente` (o mesmo mecanismo do resto da suíte)."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT nome FROM plat.versao_migracao WHERE nome LIKE 'pgstac-migrate-%'")
        linhas = [r["nome"] for r in cur.fetchall()]
    assert linhas, "nenhuma linha pgstac-migrate-* em versao_migracao — rode db/pgstac_instalar.sh"


def test_plat_app_tem_pgstac_read_e_ingest_nunca_admin(conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT current_user AS quem")
        quem = cur.fetchone()["quem"]  # plat_tpgstac_app nesta trilha
        cur.execute(
            "SELECT r.rolname FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles m2 ON m2.oid = m.member "
            "WHERE m2.rolname = %s",
            (quem,),
        )
        papeis = {r["rolname"] for r in cur.fetchall()}
    assert "pgstac_read" in papeis, papeis
    assert "pgstac_ingest" in papeis, papeis
    assert "pgstac_admin" not in papeis, f"{quem} tem pgstac_admin — a migração de privilégios reprovou: {papeis}"


def test_plat_app_le_pgstac_mas_nao_e_dono(conexao_plat_app):
    """Prova positiva (lê) e negativa (não pode DDL) no MESMO teste: pgstac_read dá SELECT nas tabelas,
    mas plat_app não é dono do schema (só pgstac_admin é) — não pode alterar a estrutura do pgstac."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pgstac.collections")
        assert cur.fetchone()["n"] >= 0  # só confere que SELECT não estoura por privilégio
        falhou = False
        try:
            cur.execute("ALTER TABLE pgstac.collections ADD COLUMN zt_intruso text")
            cur.connection.commit()
        except Exception:
            cur.connection.rollback()
            falhou = True
        assert falhou, "plat_app conseguiu alterar DDL do pgstac — isso é coisa de pgstac_admin"
