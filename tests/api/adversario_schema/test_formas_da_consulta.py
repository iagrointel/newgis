"""FURO por FORMA: o reescritor só age no argumento `query` de `execute`/`callproc` quando ele é `str`
(ou, desde 26fe79c, `bytes`). Toda outra forma de mandar SQL pelo MESMO cursor escapa em silêncio.

Cada teste está escrito na forma CORRETA (o SQL tem de cair no schema do ambiente). Hoje falha: o
`xfail(strict=True)` registra isso. Quando o furo for fechado o teste passa e o strict acusa XPASS,
obrigando quem consertou a tirar o marcador -- a partir daí, qualquer regressão vira falha comum.
"""

import io

import psycopg2
import pytest
from psycopg2 import sql

def escapou(exc: BaseException) -> bool:
    """A consulta foi parar no `plat` de producao (a role da trilha nao tem privilegio la)."""
    return "schema plat" in str(exc) or "plat.tenant" in str(exc)

# `plat.tenant` existe nos dois lados; a role da trilha só enxerga o do seu schema.
SELECT = "SELECT id FROM plat.tenant WHERE id = %s"


@pytest.mark.xfail(strict=True, reason="FURO F1: cursor.executemany e do C do psycopg2 e nao chama o "
                                       "execute() do CursorSchemaAmbiente (app/schema_ambiente.py:44); "
                                       "usado em app/auth/rotas_usuarios.py:242 e :285")
def test_executemany_passa_pelo_reescritor(con):
    with con.cursor() as cur:
        try:
            cur.executemany(SELECT, [(1,), (2,)])
        except psycopg2.Error as e:
            assert not escapou(e), f"executemany escapou para o plat de producao: {e}"
            raise


@pytest.mark.xfail(strict=True, reason="FURO F2: COPY nao passa por execute(); CursorSchemaAmbiente nao "
                                       "sobrescreve copy_expert/copy_from/copy_to. Uso real com `plat.` "
                                       "fixo: scripts/geocodificador_instalar_uf.py:278")
def test_copy_expert_passa_pelo_reescritor(con):
    buf = io.StringIO()
    with con.cursor() as cur:
        try:
            cur.copy_expert("COPY (SELECT count(*) FROM plat.tenant) TO STDOUT", buf)
        except psycopg2.Error as e:
            assert not escapou(e), f"copy_expert escapou para o plat de producao: {e}"
            raise


@pytest.mark.xfail(strict=True, reason="FURO F3: psycopg2.sql.SQL/Composed/Identifier nao e str nem bytes, "
                                       "entao `isinstance(query, str)` em app/schema_ambiente.py:52 nao bate. "
                                       "L2-04-a promete montar nome de tabela/coluna com sql.Identifier "
                                       "(laco/decomposicao/gera_l7.py:402) -- furo armado, ainda nao disparado")
def test_composed_passa_pelo_reescritor(con):
    consulta = sql.SQL("SELECT id FROM {}.{} LIMIT 1").format(sql.Identifier("plat"), sql.Identifier("tenant"))
    with con.cursor() as cur:
        try:
            cur.execute(consulta)
        except psycopg2.Error as e:
            assert not escapou(e), f"psycopg2.sql.Composed escapou para o plat de producao: {e}"
            raise


@pytest.mark.xfail(strict=True, reason="FURO F4: conexao aberta sem cursor_factory devolve cursor comum; "
                                       "app/jobs/eventos.py:46 abre exatamente assim (hoje so faz LISTEN, "
                                       "parametrizado, logo nao dispara -- mas esta a uma linha de disparar)")
def test_conexao_sem_cursor_factory_ainda_reescreve(env, schema):
    c = psycopg2.connect(env["PLAT_DSN"])
    try:
        with c.cursor() as cur:
            try:
                cur.execute(SELECT, (1,))
            except psycopg2.Error as e:
                assert not escapou(e), f"cursor sem fabrica escapou para o plat de producao: {e}"
                raise
    finally:
        c.rollback()
        c.close()
