"""Fixtures do catálogo de imagens (item L1-01-a): token de serviço com escopo imagens:escrever para os
dois inquilinos de demonstração (A=demo, B=demo2) — o par que o teste de isolamento cruza."""

import os

import pytest

from tests.api.conftest import PREFIXO_TESTE


@pytest.fixture(scope="module")
def garage_duble():
    """Garage de trilhas não existe neste servidor (a unidade `plataforma-garage-trilhas.service` não foi
    provisionada — TCP recusado no PLAT_GARAGE_URL da trilha, medido 18/09). Sem ele, `semear_raster` morre
    em `garantir_bucket` (PLAT_GARAGE_ADMIN_TOKEN vazio no .env da trilha) e NENHUM teste que semeia raster
    roda aqui. O duble em memória (tests/servidor_garage.py, mesmo remendo de test_arquivo_url.py) cobre o
    contrato S3/Admin que o caminho usa; SigV4 e cota física são prova do L0-11 contra o Garage real.

    Opt-in por nome: só o módulo que pede a fixture paga o remendo. Mexe nos DOIS lados — `os.environ`
    (qualquer subprocesso monta Settings do zero) e o `settings` deste processo (TestClient), já montado
    quando a fixture roda. Restaurado ao fim do módulo."""
    from app.settings import settings
    from tests.servidor_garage import GarageDuble

    chaves = ("PLAT_GARAGE_URL", "PLAT_GARAGE_ADMIN_URL", "PLAT_GARAGE_ADMIN_TOKEN")
    with GarageDuble() as g:
        ambiente_anterior = {k: os.environ.get(k) for k in chaves}
        atributos_anteriores = {k: getattr(settings, k) for k in chaves}
        for k, v in {"PLAT_GARAGE_URL": g.url, "PLAT_GARAGE_ADMIN_URL": g.url,
                     "PLAT_GARAGE_ADMIN_TOKEN": "token-do-duble-de-teste"}.items():
            os.environ[k] = v
            object.__setattr__(settings, k, v)  # Settings é dataclass frozen; o remendo é só de teste
        try:
            yield g
        finally:
            for k in chaves:
                if ambiente_anterior[k] is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = ambiente_anterior[k]
                object.__setattr__(settings, k, atributos_anteriores[k])


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


# Item L1-27: a fábrica de itens `zt*` (com a limpeza física no fim) vive no conftest do catálogo; a ficha
# de imagem precisa dela para criar itens do tipo `raster`. Importar é melhor que uma segunda fábrica:
# duas fábricas com duas limpezas diferentes deixariam resíduo na base compartilhada.
from tests.api.catalogo.conftest import itens_a, itens_b  # noqa: E402,F401
