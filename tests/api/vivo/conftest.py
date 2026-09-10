"""Apoio dos testes de atualização viva (item L2-06-d-atualizacao-viva-sse).

A camada usada é a do painel de exemplo da demo (`plat.painel_exemplo_semear`, migração
`20260906T2145_documento_painel.sql`): já existe, é dado sintético declarado e a tabela física é da PRÓPRIA
trilha — nenhum teste daqui escreve em tabela de produção."""

import time

import psycopg2
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.paineis.conftest import _semear


@pytest.fixture(scope="session")
def conexao_semente(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    yield con
    con.close()


def _semear_com_repeticao(con, slug: str, tentativas: int = 12) -> dict:
    """`plat.painel_exemplo_semear` chama `camada_schema_garantir`, que faz `GRANT USAGE ON SCHEMA d_<slug>`
    sem condição. `d_demo` é COMPARTILHADO por todas as trilhas do laço, e duas trilhas concedendo ao mesmo
    tempo colidem na mesma linha de `pg_namespace` — o Postgres devolve `tuple concurrently updated`
    (medido: 8 sessões mexendo em `d_demo` na hora deste teste; a colisão repetiu em três rodadas seguidas).
    Não é falha do produto nem da semente: é disputa de catálogo entre trilhas. Repete com espera curta."""
    ultimo = None
    for tentativa in range(tentativas):
        try:
            return _semear(con, slug)
        except psycopg2.errors.InternalError_ as e:  # noqa: PERF203 — repetição é o ponto
            if "concurrently updated" not in str(e):
                raise
            ultimo = e
            con.rollback()
            time.sleep(0.5 + 0.5 * tentativa)
    raise AssertionError(f"semente de {slug} não passou em {tentativas} tentativas: {ultimo}")


@pytest.fixture(scope="session")
def camada_a(conexao_semente):
    """Camada vetorial do inquilino demo (A)."""
    return {**_semear_com_repeticao(conexao_semente, "demo"), "slug": "demo"}


@pytest.fixture(scope="session")
def camada_b(conexao_semente):
    """Camada vetorial do inquilino demo2 (B)."""
    return {**_semear_com_repeticao(conexao_semente, "demo2"), "slug": "demo2"}


def conectar_como(env, slug: str):
    """Conexão `plat_app` já com o contexto de inquilino posto na sessão. Sem isso a RLS esconde tudo e
    um SELECT em `plat.item` (ou em `plat.camada_evento`) volta VAZIO — que num teste se disfarça de
    "o produto não gravou nada"."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
        r = cur.fetchone()
        assert r is not None, f"admin de {slug} não semeado (rode install.sh)"
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false), "
            "set_config('plat.login', 'teste-vivo', false)",
            (str(r["tenant_id"]), str(r["usuario_id"])),
        )
    return con


def tabela_fisica(env, camada_id: str, slug: str) -> tuple[str, str]:
    con = conectar_como(env, slug)
    try:
        with con.cursor() as cur:
            cur.execute("SELECT dados->>'schema' AS s, dados->>'tabela' AS t FROM plat.item WHERE id = %s::uuid",
                        (camada_id,))
            r = cur.fetchone()
        assert r is not None, f"camada {camada_id} não visível para {slug}"
        return r["s"], r["t"]
    finally:
        con.close()
