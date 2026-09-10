"""Isolamento do schema de dado por instalação (achado F8 do adversário de 07/09/2026).

O dado de camada morava em `d_<slug>`, derivado só do apelido do inquilino. Esse nome não contém a
palavra `plat`, então o tradutor de schema (app/schema_ambiente.py) nunca o alcançava: produção,
homologação e todas as trilhas gravavam no MESMO `d_demo`. Medido em 07/09/2026: 79 tabelas em
`d_demo`, 65 delas de sete trilhas e 14 do produto.

Os quatro testes deste arquivo são as quatro exigências do portão do conserto. Os dois primeiros
precisam de uma SEGUNDA instalação no mesmo banco, criada com:

    bash /home/dev/plataforma/laco/trilha_ambiente.sh f8isolb /home/dev/plataforma/wt/f8isol

Nenhum deles escreve em `d_demo`/`d_demo2` — o terceiro e o quarto só medem privilégio e catálogo, e
o `DROP TABLE` do quarto roda dentro de uma transação desfeita.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest
from dotenv import dotenv_values

from app.ingestao.inspecionar import tabela_de
from app.schema_ambiente import SCHEMA_PADRAO
from tests.api.ingestao.conftest import GERADOS
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "F8-isolamento-d-slug"
SEGUNDA = Path("/home/dev/plataforma/laco/var/trilha/f8isolb.env")
PRODUCAO = "d_demo"  # o schema de dado do inquilino `demo` na instalação de produção


def _prefixo(con) -> str:
    with con.cursor() as cur:
        cur.execute("SELECT plat.camada_schema_prefixo() AS p")
        return cur.fetchone()["p"]


def _admin(con, slug: str = "demo") -> None:
    ids = ids_por_slug(con)
    with con.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        adm = cur.fetchone()["usuario_id"]
    contexto(con, ids[slug], usuario_id=adm, login="admin")


def _instalacao(dsn: str, esquema: str):
    """Conexão com UMA instalação, falando com ela pelo nome do schema (o mesmo que o tradutor de
    app/schema_ambiente.py escreve em tempo de execução). Devolve (conexão, prefixo do schema de dado)."""
    con = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    with con.cursor() as cur:
        # auth_login é SECURITY DEFINER: devolve o tenant_id antes de haver contexto (a RLS de
        # plat.tenant esconde a linha de quem ainda não se identificou)
        cur.execute(f'SELECT tenant_id FROM "{esquema}".auth_login(%s, %s)', ("demo", "admin"))
        tid = cur.fetchone()["tenant_id"]
        cur.execute("SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', '0', false)",
                    (str(tid),))
        cur.execute(f'SELECT "{esquema}".camada_schema_garantir(%s) ', ("demo",))
        cur.execute(f'SELECT "{esquema}".camada_schema_prefixo() AS p')
        prefixo = cur.fetchone()["p"]
    con.commit()
    return con, prefixo


@pytest.fixture
def segunda_instalacao():
    if not SEGUNDA.exists():
        pytest.fail(f"crie a segunda instalação antes: bash /home/dev/plataforma/laco/trilha_ambiente.sh "
                    f"f8isolb /home/dev/plataforma/wt/f8isol  (esperado {SEGUNDA})")
    v = dotenv_values(SEGUNDA)
    return {"dsn": v["PLAT_DSN"], "schema": v["PLAT_SCHEMA"]}


# ------------------------------------------------------------------ exigência 1
def test_duas_instalacoes_com_o_mesmo_identificador_de_camada_nao_se_veem(env, segunda_instalacao, medida):
    """Mesmo identificador de camada, duas instalações no MESMO banco: cada uma acha a SUA tabela, com o
    SEU conteúdo. Com o código anterior os dois nomes eram `d_demo.c_<hex>` — a segunda carga apagava a
    primeira (o passo 0 de carregar.py é `DROP TABLE IF EXISTS`)."""
    tabela = tabela_de(uuid.uuid4())  # o MESMO identificador nas duas instalações
    con_a, pref_a = _instalacao(env["PLAT_DSN"], env["PLAT_SCHEMA"])
    con_b, pref_b = _instalacao(segunda_instalacao["dsn"], segunda_instalacao["schema"])
    esq_a, esq_b = pref_a + "demo", pref_b + "demo"
    try:
        assert esq_a != esq_b, f"as duas instalações caíram no MESMO schema de dado ({esq_a})"
        for con, esq, marca in ((con_a, esq_a, "instalacao_a"), (con_b, esq_b, "instalacao_b")):
            with con.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "{esq}"."{tabela}"')
                cur.execute(f'CREATE TABLE "{esq}"."{tabela}" (marca text)')
                cur.execute(f'INSERT INTO "{esq}"."{tabela}" VALUES (%s)', (marca,))
            con.commit()
        for con, esq, marca in ((con_a, esq_a, "instalacao_a"), (con_b, esq_b, "instalacao_b")):
            with con.cursor() as cur:
                cur.execute(f'SELECT marca FROM "{esq}"."{tabela}"')
                assert [r["marca"] for r in cur.fetchall()] == [marca], f"{esq} não tem o próprio conteúdo"
        with con_a.cursor() as cur:  # a instalação A não alcança a tabela de mesmo nome da B
            with pytest.raises(psycopg2.Error):
                cur.execute(f'SELECT marca FROM "{esq_b}"."{tabela}"')
        con_a.rollback()
    finally:
        for con, esq in ((con_a, esq_a), (con_b, esq_b)):
            try:
                with con.cursor() as cur:
                    cur.execute(f'DROP TABLE IF EXISTS "{esq}"."{tabela}"')
                con.commit()
            finally:
                con.close()
    medida(ITEM)("schemas_de_dado_de_duas_instalacoes", f"{esq_a} x {esq_b}", "nome",
                 "pytest tests/api/ingestao/test_isolamento_schema_dado.py")


# ------------------------------------------------------------------ exigência 2
def test_instalacao_de_teste_sem_privilegio_no_schema_de_dado_de_producao(conexao_plat_app):
    """Prova pelo PRIVILÉGIO, não pelo nome: a role desta instalação não lê, não escreve, não cria e não
    é dona de nada no schema de dado de produção."""
    from app.settings import settings

    if settings.PLAT_SCHEMA == SCHEMA_PADRAO:
        pytest.skip("rodando COMO produção: não há o que isolar")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (PRODUCAO,))
        if cur.fetchone() is None:
            pytest.skip(f"{PRODUCAO} não existe nesta máquina")
        cur.execute("SELECT current_user AS u, has_schema_privilege(%s, 'USAGE') AS usa, "
                    "has_schema_privilege(%s, 'CREATE') AS cria", (PRODUCAO, PRODUCAO))
        r = cur.fetchone()
        assert not r["usa"], f"{r['u']} tem USAGE em {PRODUCAO}"
        assert not r["cria"], f"{r['u']} tem CREATE em {PRODUCAO}"
        cur.execute(
            "SELECT count(*) FILTER (WHERE has_table_privilege(c.oid, 'SELECT')) AS le, "
            "       count(*) FILTER (WHERE has_table_privilege(c.oid, 'DELETE')) AS apaga, "
            "       count(*) FILTER (WHERE c.relowner = current_user::regrole) AS minhas, count(*) AS total "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = 'r'", (PRODUCAO,))
        r = cur.fetchone()
        assert r["le"] == 0 and r["apaga"] == 0 and r["minhas"] == 0, r


# ------------------------------------------------------------------ exigência 3
def test_carga_e_funcoes_respeitam_a_instalacao(ingestor_a, conexao_plat_app, medida):
    """O caminho de carga inteiro (carregar.py + camada_schema_garantir + camada_preparar) grava no
    schema da INSTALAÇÃO, e o item registra esse schema."""
    if not GERADOS.exists():
        pytest.skip("rode `venv/bin/python tests/dados/gerar.py` antes")
    from app.settings import settings

    importacao_id, _ = ingestor_a.importar("cobertura.gpkg", "gpkg")
    final = ingestor_a.confirmar(importacao_id)
    assert final["estado"] == "concluida", final

    _admin(conexao_plat_app)
    prefixo = _prefixo(conexao_plat_app)
    if settings.PLAT_SCHEMA != SCHEMA_PADRAO:
        assert prefixo == f"d_{settings.PLAT_SCHEMA}_", prefixo
    else:
        assert prefixo == "d_", prefixo
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id = %s::uuid",
                    (final["item_id"],))
        r = cur.fetchone()
        assert r["s"] == prefixo + "demo", r
        if settings.PLAT_SCHEMA != SCHEMA_PADRAO:
            assert r["s"] != PRODUCAO
        cur.execute(f'SELECT count(*) AS n FROM "{r["s"]}"."{r["t"]}"')
        assert cur.fetchone()["n"] == 80
        cur.execute("SELECT pg_get_userbyid(nspowner) AS dono FROM pg_namespace WHERE nspname = %s", (r["s"],))
        assert cur.fetchone()["dono"] == f"{settings.PLAT_SCHEMA}_app"
    medida(ITEM)("schema_da_camada_carregada", r["s"], "nome",
                 "pytest tests/api/ingestao/test_isolamento_schema_dado.py")


# ------------------------------------------------------------------ exigência 4 (refutação)
def test_refutacao_carga_de_trilha_nao_alcanca_camada_de_producao(conexao_plat_app):
    """Monta de propósito o caso que destruía: MESMO identificador de camada em produção e na trilha.
    O passo 0 de carregar.py (`DROP TABLE IF EXISTS ... CASCADE`) é executado com o identificador de uma
    camada REAL de produção, dentro de uma transação desfeita: tem de ser recusado, e a tabela de
    produção continua no catálogo."""
    from psycopg2 import errors

    from app.settings import settings

    if settings.PLAT_SCHEMA == SCHEMA_PADRAO:
        pytest.skip("rodando COMO produção: não há o que refutar")
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT c.relname AS t FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND c.relkind = 'r' AND c.relname ~ '^c_[0-9a-f]{16}$' "
                    "ORDER BY 1 LIMIT 1", (PRODUCAO,))
        alvo = cur.fetchone()
        if alvo is None:
            pytest.skip(f"nenhuma camada em {PRODUCAO} para refutar")
        tabela = alvo["t"]

    # o nome que o código ANTIGO derivava era o mesmo dos dois lados
    assert "d_" + "demo" == PRODUCAO
    prefixo = _prefixo(conexao_plat_app)
    assert prefixo + "demo" != PRODUCAO, "o prefixo da instalação não separou nada"

    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout = '2s'")
        with pytest.raises((errors.InsufficientPrivilege, errors.InvalidSchemaName, psycopg2.ProgrammingError)):
            cur.execute(f'DROP TABLE IF EXISTS "{PRODUCAO}"."{tabela}" CASCADE')
    conexao_plat_app.rollback()

    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND c.relname = %s", (PRODUCAO, tabela))
        assert cur.fetchone()["n"] == 1, "a camada de produção sumiu"
