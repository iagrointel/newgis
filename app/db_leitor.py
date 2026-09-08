"""Pool minúsculo com o papel de leitura `plat_leitor` (LOGIN, sem BYPASSRLS, sem dono de nada),
usado só por `app/tiles/rotas.py` (a checagem de token antes do Martin). Deliberadamente SEPARADO
do pool de `app/db.py` (que conecta como `plat_app`, dona do schema): a rota de verificação nunca deve
ter mais privilégio que o próprio Martin teria."""

import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.pool

from app.schema_ambiente import CursorSchemaAmbiente
from app.settings import settings

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_trava = threading.Lock()


class SemLeitorConfigurado(RuntimeError):
    """PLAT_DSN_LEITOR não configurado neste ambiente."""


def pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _trava:
            if _pool is None:
                if not settings.PLAT_DSN_LEITOR:
                    raise SemLeitorConfigurado
                # 1/10, não 1/2: esta rota atende a CADA pedido de tile (via auth_request), não a cada
                # pedido de página; achado do adversário (200 pedidos em paralelo ao z0 da camada de
                # 1 mi): com 1/2 a piscina esgotava sob 50 threads e `getconn()` levantava PoolError,
                # que o `except Exception` genérico classificava como "token_invalido" (401 errado por
                # motivo errado, embora seguro — nunca deixava passar). 10 é modesto sobre o
                # max_connections=100 compartilhado (ADR 0001; a trilha já reserva PLAT_POOL_MAX=2 para
                # o pool principal, plat_app).
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 10, settings.PLAT_DSN_LEITOR, cursor_factory=CursorSchemaAmbiente
                )
    return _pool


@contextmanager
def conexao_leitor():
    """Cursor com o papel de leitura. Autocommit: contexto_por_token grava seu próprio log mesmo em
    recusa (a exceção sobe do `with`); não há nada mais para esta rota fazer dentro da transação."""
    p = pool()
    con = p.getconn()
    con.autocommit = True
    try:
        with con.cursor() as cur:
            yield cur
    finally:
        p.putconn(con, close=con.closed)
