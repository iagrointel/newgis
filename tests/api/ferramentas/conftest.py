"""Fixtures do item L2-05-a: camada de A (demo) e de B (demo2), token de serviço com escopo jobs:executar para o
GPServer, worker vivo para os jobs, e limpeza de tudo o que a suíte criou (entradas e resultados)."""

import pytest

from tests.api.ferramentas import apoio


@pytest.fixture(scope="module")
def criados():
    return {"demo": [], "demo2": []}


@pytest.fixture(scope="module")
def camada_a(env, sessao_a, criados):
    c = apoio.criar_camada(env, sessao_a, "demo")
    criados["demo"].append(c["id"])
    yield c
    apoio.apagar_itens(env, "demo", criados["demo"])


@pytest.fixture(scope="module")
def camada_b(env, sessao_b, criados):
    c = apoio.criar_camada(env, sessao_b, "demo2")
    criados["demo2"].append(c["id"])
    yield c
    apoio.apagar_itens(env, "demo2", criados["demo2"])


@pytest.fixture(scope="module")
def token_gp(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-ferramentas-gp", "escopos": ["jobs:executar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture(scope="session")
def worker_vivo(cliente):
    r = cliente.get("/saude").json()
    fila = r.get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.fail(f"nenhum worker vivo em /saude ({fila}); suba `venv/bin/python -m app.jobs.worker` "
                    "com o env da trilha")
    return fila
