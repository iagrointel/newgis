"""Corrida de DDL entre sessões do MESMO inquilino (defeito medido em 07/09/2026, produção-de-teste).

Dois usuários do mesmo cliente publicando camada ao mesmo tempo caem os dois em
`plat.camada_schema_garantir(slug)`, que faz `CREATE SCHEMA IF NOT EXISTS` + `GRANT USAGE ON SCHEMA`.
Nenhum dos dois é atômico contra outra transação: o `IF NOT EXISTS` lê o catálogo com a visão da
própria transação e o `GRANT` atualiza a MESMA linha de `pg_namespace`, que não tem EvalPlanQual.
Resultado antes do conserto: `tuple concurrently updated` e o job de ingestão morre no passo 0.

Os testes daqui usam conexões REAIS em paralelo, como `plat_app`, nunca como postgres. O conserto é a
migração `20260907T0240_ddl_concorrente_trinco.sql` (ADR 0025): `pg_advisory_xact_lock` com chave
derivada do slug, tomado antes do DDL.
"""

import os
import re
import threading

import psycopg2
import pytest

from tests.api.test_rls import contexto, ids_por_slug

CONEXOES_PADRAO = 4
RODADAS = 6


def _schema_plat() -> str:
    return os.environ.get("PLAT_SCHEMA") or "plat"


def _abrir(env):
    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = False
    return con


def _corrida(env, alvos: list[tuple[str, int]]) -> list[str | None]:
    """Abre uma conexão por alvo `(slug, tenant_id)`, alinha todas numa barreira e chama
    `plat.camada_schema_garantir` ao mesmo tempo. Devolve o erro de cada uma (None quando passou)."""
    n = len(alvos)
    barreira = threading.Barrier(n, timeout=30)
    erros: list[str | None] = [None] * n

    def trabalhar(i: int, slug: str, tid: int) -> None:
        con = _abrir(env)
        try:
            contexto(con, tid)
            with con.cursor() as cur:
                barreira.wait()
                try:
                    cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
                    con.commit()
                except Exception as e:  # o que se quer medir: qualquer falha da corrida
                    con.rollback()
                    erros[i] = f"{type(e).__name__}: {e}".strip()
        finally:
            con.close()

    fios = [threading.Thread(target=trabalhar, args=(i, s, t)) for i, (s, t) in enumerate(alvos)]
    for f in fios:
        f.start()
    for f in fios:
        f.join(timeout=60)
    assert not any(f.is_alive() for f in fios), "conexão travada na corrida"
    return erros


@pytest.fixture(scope="module")
def ids_demo(env):
    con = _abrir(env)
    try:
        return ids_por_slug(con)
    finally:
        con.rollback()
        con.close()


@pytest.mark.parametrize("n", [2, CONEXOES_PADRAO, 6])
def test_publicacao_simultanea_no_mesmo_inquilino_nao_quebra(env, ids_demo, n):
    """VERMELHO antes da migração 20260907T0240: com o GRANT sem trinco, parte das conexões termina em
    `tuple concurrently updated`. Repete a corrida algumas vezes porque a janela é curta."""
    alvos = [("demo", ids_demo["demo"])] * n
    falhas = []
    for _ in range(RODADAS):
        falhas += [e for e in _corrida(env, alvos) if e]
    assert falhas == [], f"{len(falhas)} de {n * RODADAS} chamadas falharam na corrida: {falhas[:3]}"


def test_inquilinos_diferentes_nao_esperam(env, ids_demo):
    """A chave do trinco é o slug: uma trilha presa em `demo` não pode segurar `demo2`.
    Prova nos dois sentidos — o mesmo slug espera (e estoura o statement_timeout), o outro passa."""
    segurador = _abrir(env)
    outro = _abrir(env)
    mesmo = _abrir(env)
    try:
        # 1) segurador toma o trinco de `demo` e NÃO confirma: o trinco de transação fica de pé
        contexto(segurador, ids_demo["demo"])
        with segurador.cursor() as cur:
            cur.execute("SELECT plat.camada_schema_garantir(%s)", ("demo",))

        # 2) outro inquilino progride sem esperar
        contexto(outro, ids_demo["demo2"])
        with outro.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 5000")
            cur.execute("SELECT plat.camada_schema_garantir(%s)", ("demo2",))
        outro.commit()

        # 3) o MESMO inquilino espera de verdade (senão o trinco não estaria protegendo nada)
        contexto(mesmo, ids_demo["demo"])
        with pytest.raises(psycopg2.errors.QueryCanceled):
            with mesmo.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = 1000")
                cur.execute("SELECT plat.camada_schema_garantir(%s)", ("demo",))
    finally:
        for c in (mesmo, outro, segurador):
            c.rollback()
            c.close()


# Funções SECURITY DEFINER que emitem DDL mas NÃO precisam do trinco, com a razão. `ALTER TABLE` sozinho
# pega bloqueio pesado na própria tabela antes de mexer no catálogo, logo duas sessões serializam em vez
# de colidir; o problema é o DDL de SCHEMA e o GRANT, que atualizam linha de catálogo sem esse bloqueio.
SEM_TRINCO_JUSTIFICADO = {"tenant_apagar_interno"}
DDL_QUE_CORRE = re.compile(r"CREATE SCHEMA|GRANT |CREATE TABLE|DROP TABLE", re.I)


def test_toda_funcao_com_ddl_tem_trinco(env, conexao_plat_app):
    """Guarda da CLASSE: qualquer função SECURITY DEFINER de `plat` que monte DDL de schema, GRANT ou
    CREATE/DROP TABLE tem de tomar `pg_advisory_xact_lock`. Reprova se um ramo futuro redefinir uma das
    funções consertadas e deixar o trinco cair fora."""
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = %s AND p.prosecdef AND p.prosrc LIKE %s",
            (_schema_plat(), "%EXECUTE%"),
        )
        linhas = cur.fetchall()
    assert linhas, "nenhuma função SECURITY DEFINER encontrada — ambiente errado"
    sem_trinco = sorted(
        r["proname"]
        for r in linhas
        if r["proname"] not in SEM_TRINCO_JUSTIFICADO
        and DDL_QUE_CORRE.search(r["prosrc"])
        and "pg_advisory_xact_lock" not in r["prosrc"]
    )
    assert sem_trinco == [], f"função SECURITY DEFINER faz DDL sem trinco: {sem_trinco}"


def test_medidas(env, ids_demo, medida):
    grava = medida("corrida-camada-schema")
    n = CONEXOES_PADRAO
    falhas = 0
    for _ in range(RODADAS):
        falhas += len([e for e in _corrida(env, [("demo", ids_demo["demo"])] * n) if e])
    grava(
        "falhas_em_corrida_4_conexoes",
        falhas,
        f"falhas em {n * RODADAS} chamadas",
        "bash /home/dev/plataforma/laco/roda_teste.sh tests/api/test_camada_schema_corrida.py -q",
    )
