"""A reescrita de schema (`app/schema_ambiente.py`) é o que permite a trilha/homologação rodar o mesmo código
de produção sem editar os `plat.` literais. Regressão do achado da suíte cruzada (item L0-08-a-oidc):
`executemany` não passa pelo `execute` do psycopg2 (laço próprio em C), então INSERT em massa com `plat.`
literal batia no schema de PRODUÇÃO dentro da trilha — 42501 "permission denied for schema plat",
convertido em 403 "fora do inquilino" pela rota. O cursor vem da conexão real de teste (o tipo é C e não
se constrói sem conexão); o método do PAI é espiado, então nada chega ao servidor."""

from __future__ import annotations

import contextlib

import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente

ALVO = "plat_teste_reescrita"  # nunca toca o servidor: o pai é espiado


@pytest.fixture
def cursor(conexao_plat_app):
    c = conexao_plat_app.cursor()
    yield c
    conexao_plat_app.rollback()  # nada chegou ao servidor (pai espiado); por garantia, descarta


def _espiar_pai(metodo: str, monkeypatch) -> list[str]:
    """Substitui o método do pai (RealDictCursor) por um gravador: intercepta a consulta DEPOIS da
    sobrecarga da subclasse, sem tocar o banco."""
    visto: list[str] = []

    def gravar(self, query, *args, **kwargs):
        visto.append(query)

    monkeypatch.setattr(psycopg2.extras.RealDictCursor, metodo, gravar)
    return visto


@contextlib.contextmanager
def _schema_trocado(valor: str):
    """Settings é dataclass congelado lido de env na importação: troca o campo por object.__setattr__ e
    restaura o original (na trilha ele já é um schema de ambiente, não 'plat')."""
    from app.settings import settings

    original = settings.PLAT_SCHEMA
    object.__setattr__(settings, "PLAT_SCHEMA", valor)
    try:
        yield
    finally:
        object.__setattr__(settings, "PLAT_SCHEMA", original)


def test_executemany_reescreve_plat_literal(cursor, monkeypatch):
    """O caso reprovado: rota POST /api/papeis usa executemany com `plat.` literal."""
    visto = _espiar_pai("executemany", monkeypatch)
    with _schema_trocado(ALVO):
        cursor.executemany("INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)", [(1, "a")])
    assert visto == [f"INSERT INTO {ALVO}.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)"], visto


def test_execute_reescreve_plat_literal(cursor, monkeypatch):
    visto = _espiar_pai("execute", monkeypatch)
    with _schema_trocado(ALVO):
        cursor.execute("SELECT * FROM plat.usuario WHERE id = %s", (1,))
    assert visto == [f"SELECT * FROM {ALVO}.usuario WHERE id = %s"], visto


def test_callproc_reescreve(cursor, monkeypatch):
    visto = _espiar_pai("callproc", monkeypatch)
    with _schema_trocado(ALVO):
        cursor.callproc("plat.tenant_atual")
    assert visto == [f"{ALVO}.tenant_atual"], visto


def test_guc_customizado_nunca_e_reescrito(cursor, monkeypatch):
    """current_setting('plat.tenant_id')/set_config('plat.usuario_id') são GUC de SESSÃO, não objetos do
    schema — a reescrita os preserva (contrato do módulo, garantido pelo lookbehind da regex)."""
    visto = _espiar_pai("executemany", monkeypatch)
    with _schema_trocado(ALVO):
        cursor.executemany(
            "SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true)", [("1", "1")]
        )
    assert "plat.tenant_id" in visto[0] and "plat.usuario_id" in visto[0], visto


def test_schema_padrao_passa_igual(cursor, monkeypatch):
    """Produção (PLAT_SCHEMA='plat', o padrão do módulo): nenhuma consulta é alterada — custo zero."""
    from app.settings import settings

    original = settings.PLAT_SCHEMA
    visto = _espiar_pai("execute", monkeypatch)
    with _schema_trocado("plat"):
        cursor.execute("SELECT * FROM plat.usuario WHERE id = %s", (1,))
    assert visto == ["SELECT * FROM plat.usuario WHERE id = %s"], visto
    assert settings.PLAT_SCHEMA == original  # gerenciador restaurou o valor do ambiente
