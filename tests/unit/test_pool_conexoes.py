"""Tamanho do pool de conexões (PLAT_POOL_MIN/PLAT_POOL_MAX).

Por que este teste existe: o Postgres `iagro_sat` é compartilhado com dezenas de frentes da casa e
tem `max_connections` = 100, das quais 3 são reservadas ao superusuário. Enquanto o tamanho do pool
estava fixo em (1, 8) dentro de `app/db.py`, cada trilha de teste do laço com serviço próprio pedia
até 8 conexões: vinte trilhas pediriam 160 e quarenta pediriam 320, mais do que o servidor inteiro
oferece. O tamanho passou a vir da configuração, e o padrão continua sendo exatamente (1, 8) para
que produção não mude em nada.
"""

import psycopg2.pool
import pytest

import app.db as db_mod
from app.settings import POOL_MAX_PADRAO, POOL_MIN_PADRAO, ErroConfiguracao, carregar

BASE = {
    "PLAT_DSN": "postgresql://plat_app:x@127.0.0.1:5432/iagro_sat",
    "PLAT_SECRET": "ab" * 32,
    "PLAT_AMBIENTE": "producao",
    "PLAT_URL_PUBLICA": "https://exemplo.invalido",
}


def test_padrao_e_1_e_8_como_antes_da_chave_existir():
    s = carregar(BASE)
    assert (s.PLAT_POOL_MIN, s.PLAT_POOL_MAX) == (1, 8)
    assert (POOL_MIN_PADRAO, POOL_MAX_PADRAO) == (1, 8)


def test_le_as_variaveis_de_ambiente():
    s = carregar({**BASE, "PLAT_POOL_MIN": "1", "PLAT_POOL_MAX": "2"})
    assert s.PLAT_POOL_MIN == 1
    assert s.PLAT_POOL_MAX == 2


@pytest.mark.parametrize(
    "valores,trecho",
    [
        ({"PLAT_POOL_MAX": "0"}, "PLAT_POOL_MAX"),
        ({"PLAT_POOL_MIN": "0"}, "PLAT_POOL_MIN"),
        ({"PLAT_POOL_MAX": "dois"}, "PLAT_POOL_MAX"),
        ({"PLAT_POOL_MIN": "4", "PLAT_POOL_MAX": "2"}, "PLAT_POOL_MAX"),
    ],
)
def test_valor_invalido_e_recusado_nomeando_a_chave(valores, trecho):
    with pytest.raises(ErroConfiguracao) as erro:
        carregar({**BASE, **valores})
    assert trecho in str(erro.value)


def test_pool_usa_o_que_a_configuracao_diz(monkeypatch):
    """`app.db.pool()` repassa min/max da configuração ao ThreadedConnectionPool (sem abrir conexão)."""
    registrado = {}

    class PoolFalso:
        def __init__(self, minconn, maxconn, dsn):
            registrado.update(minconn=minconn, maxconn=maxconn, dsn=dsn)

    monkeypatch.setattr(psycopg2.pool, "ThreadedConnectionPool", PoolFalso)
    monkeypatch.setattr(db_mod, "_pool", None)
    monkeypatch.setattr(db_mod, "settings", carregar({**BASE, "PLAT_POOL_MIN": "1", "PLAT_POOL_MAX": "2"}))
    try:
        db_mod.pool()
    finally:
        db_mod._pool = None
    assert registrado["minconn"] == 1
    assert registrado["maxconn"] == 2
