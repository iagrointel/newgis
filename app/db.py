"""Pool psycopg2 com reconexão e contexto por inquilino (ADR 0001 seção 3.2). Substância copiada de
main.py do SIG de teste interno: só a PREPARAÇÃO repete (até 9 vezes); a consulta do chamador roda uma única vez.
Conexão que falhou na preparação é descartada (putconn close=True), nunca reaproveitada."""

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.settings import settings

ROOT = Path(__file__).resolve().parents[1]
DIR_MIGRACOES = ROOT / "db" / "migracoes"
TENTATIVAS = 9

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_trava = threading.Lock()


@dataclass(frozen=True)
class Contexto:
    tenant_id: int
    usuario_id: int
    login: str


def pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Cria o pool na primeira chamada (a configuração é lida só então)."""
    global _pool
    if _pool is None:
        with _trava:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(1, 8, settings.PLAT_DSN)
    return _pool


def _preparar(con, ctx: Contexto | None):
    if con.closed:
        raise psycopg2.OperationalError("conexão do pool já estava fechada")
    con.autocommit = False
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET search_path = plat, public")
    if ctx is not None:
        cur.execute(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true), "
            "set_config('plat.login', %s, true)",
            (str(ctx.tenant_id), str(ctx.usuario_id), ctx.login),
        )
    return cur


@contextmanager
def db(ctx: Contexto | None = None):
    """Cursor RealDict dentro de uma transação; commit no fim, rollback em exceção."""
    p = pool()
    con = cur = None
    for tentativa in range(TENTATIVAS):
        con = p.getconn()
        try:
            cur = _preparar(con, ctx)
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
    """Nomes (sem .sql) de db/migracoes/NNN_*.sql em ordem lexicográfica."""
    return sorted(p.stem for p in DIR_MIGRACOES.glob("[0-9][0-9][0-9]_*.sql"))


def migracoes_estado() -> tuple[int, int, str | None]:
    """(aplicadas, pendentes, ultima) comparando o disco com plat.versao_migracao."""
    disco = migracoes_em_disco()
    with db() as cur:
        cur.execute("SELECT nome FROM plat.versao_migracao ORDER BY nome")
        aplicadas = [r["nome"] for r in cur.fetchall()]
    pendentes = [n for n in disco if n not in aplicadas]
    return len(aplicadas), len(pendentes), (aplicadas[-1] if aplicadas else None)
