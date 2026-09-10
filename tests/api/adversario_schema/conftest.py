"""Trava de segurança do pacote do adversário: estes testes provocam de propósito consultas que, se
escaparem do reescritor, batem no schema `plat` de PRODUÇÃO. Só rodam num ambiente de trilha/homologação
(PLAT_SCHEMA != 'plat'), e só fazem leitura ou erro de privilégio -- nunca escrita fora do schema da trilha.
"""

import psycopg2
import pytest

from app.schema_ambiente import SCHEMA_PADRAO, CursorSchemaAmbiente


@pytest.fixture(scope="session")
def schema(env) -> str:
    s = env.get("PLAT_SCHEMA") or SCHEMA_PADRAO
    if s == SCHEMA_PADRAO:
        pytest.skip("pacote do adversário só roda em trilha/homologação (PLAT_SCHEMA != 'plat')")
    return s


@pytest.fixture
def con(env, schema):
    """Conexão como a role da trilha, COM o reescritor. A role não tem USAGE em `plat`: por isso qualquer
    consulta que escape da reescrita levanta `permission denied for schema plat` -- o detector é o próprio
    erro de privilégio, e nada é escrito em produção."""
    c = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    c.autocommit = False
    try:
        yield c
    finally:
        c.rollback()
        c.close()
