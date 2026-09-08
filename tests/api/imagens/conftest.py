"""Fixtures do catálogo de imagens (item L1-01-a): token de serviço com escopo imagens:escrever para os
dois inquilinos de demonstração (A=demo, B=demo2) — o par que o teste de isolamento cruza."""

import pytest

from tests.api.conftest import PREFIXO_TESTE


def _criar_token(sessao, escopos):
    r = sessao.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-stac", "escopos": escopos})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="session")
def token_stac_a(sessao_a):
    tok = _criar_token(sessao_a, ["imagens:escrever"])
    yield tok
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture(scope="session")
def token_stac_b(sessao_b):
    tok = _criar_token(sessao_b, ["imagens:escrever"])
    yield tok
    sessao_b.delete(f"/api/tokens/{tok['id']}")


def _tenant_id(env, slug: str) -> int:
    """Conexão PRÓPRIA e curta (não `conexao_plat_app`, que é escopo de função de propósito — uma por
    teste, rollback no fim): tenant_id_a/b precisam valer em fixture de módulo (test_medida_10000.py
    semeia 10.000 itens uma vez só) e um fixture de escopo maior não pode depender de um mais estreito."""
    import psycopg2

    from app.schema_ambiente import CursorSchemaAmbiente

    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        with con.cursor() as cur:
            # `plat.tenant` tem RLS (só o próprio inquilino se vê) — `tenant_publico`, a mesma função
            # SECURITY DEFINER que a tela de login usa antes de qualquer credencial, contorna isso de
            # propósito (app/auth/rotas_login.py); nunca um SELECT direto em plat.tenant sem contexto.
            cur.execute("SELECT id FROM plat.tenant_publico(%s)", (slug,))
            return cur.fetchone()["id"]
    finally:
        con.close()


@pytest.fixture(scope="session")
def tenant_id_a(env):
    return _tenant_id(env, "demo")


@pytest.fixture(scope="session")
def tenant_id_b(env):
    return _tenant_id(env, "demo2")


def item_stac(
    item_id: str, colecao: str, lon: float = -47.9, lat: float = -15.8, quando: str = "2026-01-01T00:00:00Z"
) -> dict:
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "collection": colecao,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "bbox": [lon, lat, lon, lat],
        "properties": {"datetime": quando},
        "assets": {},
        "links": [],
    }
