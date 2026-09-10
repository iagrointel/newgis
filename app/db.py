"""Pool psycopg2 com reconexão e contexto por inquilino (ADR 0001 seção 3.2). Substância copiada de
main.py do SIG de teste interno: só a PREPARAÇÃO repete (até 9 vezes); a consulta do chamador roda uma única vez.
Conexão que falhou na preparação é descartada (putconn close=True), nunca reaproveitada."""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.migracoes import chave_migracao
from app.migracoes import listar as listar_migracoes
from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings

ROOT = Path(__file__).resolve().parents[1]
DIR_MIGRACOES = ROOT / "db" / "migracoes"
TENTATIVAS = 9
POOL_ESPERA_S = 5.0  # espera por conexão livre antes de desistir (rajada > maxconn não vira 500; medido no L0-03)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_trava = threading.Lock()


@dataclass(frozen=True)
class Contexto:
    tenant_id: int
    usuario_id: int
    login: str


def pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Cria o pool na primeira chamada (a configuração é lida só então).

    O tamanho vem de PLAT_POOL_MIN/PLAT_POOL_MAX (padrão 1/8 = o que estava fixo aqui antes; produção não muda).
    O banco iagro_sat é compartilhado com dezenas de frentes da casa e tem max_connections=100 com 3 reservadas
    ao superusuário: cada trilha de teste do laço grava PLAT_POOL_MAX=2 no seu .env para que 12 trilhas em
    paralelo caibam no orçamento de conexões (ver laco/governador.sh e laco/trilha_ambiente.sh).
    """
    global _pool
    if _pool is None:
        with _trava:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    settings.PLAT_POOL_MIN, settings.PLAT_POOL_MAX, settings.PLAT_DSN
                )
    return _pool


def obter_conexao(p: psycopg2.pool.ThreadedConnectionPool):
    """getconn que ESPERA por uma conexão livre em vez de estourar na rajada.

    O ThreadedConnectionPool do psycopg2 levanta PoolError assim que passa de maxconn; sem esta espera, 20 pedidos
    simultâneos (medido no L0-03 com 20 clientes no mesmo link) derrubavam com 500 os que passassem de 8. A espera é
    limitada: passado POOL_ESPERA_S o PoolError sobe como antes.
    """
    limite = time.monotonic() + POOL_ESPERA_S
    while True:
        try:
            return p.getconn()
        except psycopg2.pool.PoolError:
            if time.monotonic() >= limite:
                raise
            time.sleep(0.01)


def _preparar(con, ctx: Contexto | None, somente_leitura: bool = False):
    if con.closed:
        raise psycopg2.OperationalError("conexão do pool já estava fechada")
    con.autocommit = False
    cur = con.cursor(cursor_factory=CursorSchemaAmbiente)
    cur.execute(f"SET search_path = {settings.PLAT_SCHEMA}, public")
    if ctx is not None:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(ctx.tenant_id), str(ctx.usuario_id), ctx.login),
        )
        # item L7-06-a-metricas-exporters: application_name é o ÚNICO GUC que pg_stat_activity mostra de
        # OUTRAS sessões (current_setting só lê a própria); o postgres_exporter usa isso para "conexões por
        # inquilino" (docs/OBSERVABILIDADE.md) SEM NUNCA tocar no slug — só o tenant_id, que já é opaco.
        # SET (não set_config local) porque application_name é do backend inteiro, não da transação: sem
        # resetar no ramo sem contexto, uma conexão do POOL devolvida por um pedido de A e reaproveitada
        # por um pedido sem contexto ficaria marcada com o inquilino errado até o próximo SET.
        cur.execute("SET application_name = %s", (f"plat:{ctx.tenant_id}",))
    else:
        cur.execute("SET application_name = 'plat'")
    if somente_leitura:
        # superadmin lendo outro inquilino (ADR 0002 seção 10): a transação inteira é só leitura
        cur.execute("SET LOCAL transaction_read_only = on")
    return cur


@contextmanager
def db(ctx: Contexto | None = None, somente_leitura: bool = False):
    """Cursor RealDict dentro de uma transação; commit no fim, rollback em exceção."""
    p = pool()
    con = cur = None
    for tentativa in range(TENTATIVAS):
        con = obter_conexao(p)
        try:
            cur = _preparar(con, ctx, somente_leitura)
            break
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            try:
                p.putconn(con, close=True)
            except Exception:  # noqa: BLE001 — a conexão já morreu; nada mais a fazer com ela
                pass
            con = cur = None
            if tentativa == TENTATIVAS - 1:
                raise
    try:
        yield cur
        con.commit()
    except Exception:
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        p.putconn(con, close=con.closed)


def migracoes_em_disco() -> list[str]:
    """Nomes (sem .sql) das migrações em db/migracoes/, na ordem de aplicação (ver app/migracoes.py)."""
    return listar_migracoes(DIR_MIGRACOES)


def migracoes_estado() -> tuple[int, int, str | None]:
    """(aplicadas, pendentes, ultima) comparando o disco com plat.versao_migracao.
    `ultima` é a de autoria mais recente pela chave_migracao, não a maior string."""
    disco = migracoes_em_disco()
    with db() as cur:
        cur.execute("SELECT nome FROM plat.versao_migracao")
        aplicadas = sorted((r["nome"] for r in cur.fetchall()), key=chave_migracao)
    pendentes = [n for n in disco if n not in aplicadas]
    return len(aplicadas), len(pendentes), (aplicadas[-1] if aplicadas else None)
