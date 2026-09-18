"""Fixtures do teste de portão do GPServer (item UX-22-ferramentas-esri-sem-tela): mesma camada de apoio e
mesmo token de serviço que `tests/api/ferramentas/conftest.py` usa — o registro de ferramentas é o mesmo
(item L2-05-a). Fixtures repetidas aqui, e não importadas, porque conftest de pacote irmão não é visível."""

import pytest

from tests.api.ferramentas import apoio


@pytest.fixture(scope="module")
def criados_esri():
    return {"demo": []}


@pytest.fixture(scope="module")
def camada_gp(env, sessao_a, criados_esri):
    c = apoio.criar_camada(env, sessao_a, "demo")
    criados_esri["demo"].append(c["id"])
    yield c
    apoio.apagar_itens(env, "demo", criados_esri["demo"])


@pytest.fixture(scope="module")
def token_gp_esri(sessao_a):
    r = sessao_a.post("/api/tokens", json={"nome": "zt-esri-gpserver", "escopos": ["jobs:executar"]})
    assert r.status_code == 201, r.text
    tok = r.json()
    yield tok["token"]
    sessao_a.delete(f"/api/tokens/{tok['id']}")


@pytest.fixture(scope="session")
def worker_vivo_esri(cliente):
    fila = (cliente.get("/saude").json() or {}).get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.fail(f"nenhum worker vivo em /saude ({fila}); suba `venv/bin/python -m app.jobs.worker` "
                    "com o env da trilha")
    return fila
