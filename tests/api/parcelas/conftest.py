"""Fixtures próprias do diretório de parcelas.

A reconcessão das visões existe por causa do ambiente de trilha, não do produto: a migração
20260908T2140_parcelas.sql concede SELECT nas visões ao papel da aplicação e as torna DONAS
dele; em produção isso basta. O ambiente de trilha (laco/trilha_ambiente.sh), porém, REVOGA
todos os privilégios do papel e recopia a matriz do schema `plat` de produção — e a matriz de
produção não conhece visão que só existe neste ramo. Medido (09/09): o REVOKE derruba até o
privilégio implícito de DONO. O que sobrevive é concessão feita DEPOIS do REVOKE; como o papel
é dono, ele tem a opção de concessão inerente e se reconcede o SELECT aqui, na abertura da
sessão de testes. Em produção a mesma ordem é um no-op idempotente.
"""

import psycopg2
import pytest


@pytest.fixture(scope="session", autouse=True)
def reconcessao_das_visoes(env):
    schema = env.get("PLAT_SCHEMA") or "plat"
    con = psycopg2.connect(env["PLAT_DSN"])
    con.autocommit = True
    try:
        with con.cursor() as cur:
            cur.execute("SELECT current_user")
            papel = cur.fetchone()[0]
            cur.execute(f"GRANT SELECT ON {schema}.v_parcela_atual, {schema}.v_parcela_historico "
                        f"TO {papel}")  # nomes vêm do ambiente da trilha (identificador validado)
    finally:
        con.close()
    yield


@pytest.fixture
def _ids(conexao_plat_app):
    """tenant_id dos inquilinos de demonstração (mesma convenção de test_modelo/test_fluxos)."""
    ids = {}
    with conexao_plat_app.cursor() as cur:
        for slug in ("demo", "demo2"):
            cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", (slug,))
            r = cur.fetchone()
            assert r is not None, f"admin de {slug} não semeado na trilha"
            ids[slug] = r["tenant_id"]
    return ids
