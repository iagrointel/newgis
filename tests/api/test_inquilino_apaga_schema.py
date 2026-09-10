"""Item L0-02-z-apagar-inquilino-apaga-schema: apagar o inquilino apaga o schema de dado d_<slug> (tabelas de camada
e funções de tile) na mesma transação da função; a fixture InquilinoTemporario usada duas vezes deixa zero schema
d_zt* a mais; 404 para inquilino inexistente e 409 para `plataforma` continuam (refutação)."""

import psycopg2

from tests.api.conftest import InquilinoTemporario, schema_de_dado_existe
from tests.api.test_rls import contexto


def _schemas_zt(cur) -> set[str]:
    cur.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'd\\_zt%'")
    return {r["nspname"] for r in cur.fetchall()}


def test_apagar_inquilino_apaga_schema_com_tabela_e_funcao_de_tile(env, sessao_plat, conexao_plat_app):
    inq = InquilinoTemporario(sessao_plat)
    slug, tid = inq.slug, inq.id
    # objetos de verdade no schema do inquilino (plat.tenant_criar já criou d_<slug>): uma tabela e uma função no
    # lugar da camada preparada — o slug de teste tem hífen e camada_preparar/camada_tile_garantir recusam o nome;
    # o que se prova aqui é que o DROP SCHEMA ... CASCADE leva tabela e função na mesma transação do apagar
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=type(conexao_plat_app.cursor()))
    con.autocommit = False
    try:
        contexto(con, tid, usuario_id=inq.admin_id, login="admin")
        with con.cursor() as cur:
            cur.execute(f'CREATE TABLE "d_{slug}"."c_0123456789abcdef" (fid bigserial PRIMARY KEY, nome text, '
                        f'geom geometry(Point, 4326))')
            cur.execute(f'CREATE FUNCTION "d_{slug}".t_0123456789abcdef(z integer, x integer, y integer, '
                        f"query_params json DEFAULT '{{}}'::json) RETURNS bytea LANGUAGE sql AS $$ SELECT ''::bytea $$")
        con.commit()
    finally:
        con.close()
    funcao = "t_0123456789abcdef"
    assert schema_de_dado_existe(slug)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT to_regprocedure(%s) IS NOT NULL AS e",
                    (f'"d_{slug}".{funcao}(integer,integer,integer,json)',))
        assert cur.fetchone()["e"]
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS e", (f'"d_{slug}".c_0123456789abcdef',))
        assert cur.fetchone()["e"]
    r = sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}")
    assert r.status_code == 204, r.text
    assert not schema_de_dado_existe(slug)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT to_regprocedure(%s) IS NOT NULL AS e",
                    (f'"d_{slug}".{funcao}(integer,integer,integer,json)',))
        assert not cur.fetchone()["e"]
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS e", (f'"d_{slug}".c_0123456789abcdef',))
        assert not cur.fetchone()["e"]
        cur.execute("SELECT count(*) AS n FROM plat.tenant WHERE id = %s", (tid,))
        assert cur.fetchone()["n"] == 0
    assert sessao_plat.delete(f"/api/plataforma/inquilinos/{tid}").status_code == 404
    inq.schema_apagado = True


def test_fixture_duas_vezes_nao_deixa_schema(sessao_plat, conexao_plat_app):
    with conexao_plat_app.cursor() as cur:
        antes = _schemas_zt(cur)
    for _ in range(2):
        inq = InquilinoTemporario(sessao_plat)
        assert schema_de_dado_existe(inq.slug)  # tenant_criar cria o schema de dado junto com o inquilino
        inq.apagar()
        assert inq.schema_apagado
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        depois = _schemas_zt(cur)
    assert depois - antes == set(), depois - antes


def test_plataforma_nao_se_apaga(sessao_plat):
    r = sessao_plat.get("/api/plataforma/inquilinos")
    plat = next(t for t in r.json() if t["slug"] == "plataforma")
    assert sessao_plat.delete(f"/api/plataforma/inquilinos/{plat['id']}").status_code == 409
