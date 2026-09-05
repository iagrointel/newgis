"""Correção T2 (3) do L0-05 (achado do testador): o perfil `visualizador` tomava 403 em /api/jobs, /api/jobs/resumo e
/api/jobs/tipos porque toda rota da fila exigia `jobs.executar`. Com a migração 015 a leitura passou a exigir
`jobs.ver` (os quatro perfis) e a execução seguiu em `jobs.executar`. Este arquivo prova a separação nos dois
sentidos: o visualizador LÊ (200) e não EXECUTA (403 com o privilégio nomeado no detalhe); o editor continua
lendo e executando; o filtro de dono do ADR 0003 seção 9 não muda (o visualizador vê 0 jobs, não os do admin)."""

import pytest

from app.auth import privilegios as priv
from tests.api.conftest import PREFIXO_TESTE, com_token
from tests.api.jobs.conftest import criar_job

LEITURA = ("/api/jobs", "/api/jobs/resumo", "/api/jobs/tipos", "/api/agendas")


@pytest.fixture(scope="module")
def visualizador(usuarios_a):
    c, u, _ = usuarios_a.sessao("visualizador")
    return c, u


def test_jobs_ver_esta_no_vocabulario_e_nos_quatro_perfis(sessao_a):
    assert "jobs.ver" in priv.NOMES and "jobs.ver" not in priv.ADMINISTRATIVOS
    for perfil in priv.PERFIS:
        assert "jobs.ver" in priv.teto(perfil), perfil
    r = sessao_a.get("/api/eu")
    assert r.status_code == 200 and "jobs.ver" in r.json()["privilegios"]


def test_visualizador_le_as_rotas_de_leitura(visualizador):
    c, _ = visualizador
    assert "jobs.ver" in c.get("/api/eu").json()["privilegios"]
    assert "jobs.executar" not in c.get("/api/eu").json()["privilegios"]
    for rota in LEITURA:
        r = c.get(rota)
        assert r.status_code == 200, (rota, r.status_code, r.text)
    assert c.get("/api/jobs").json()["itens"] == []          # filtro de dono: não vê o que é do admin
    assert c.get("/api/jobs/resumo").json()["pendente"] >= 0
    assert {t["nome"] for t in c.get("/api/jobs/tipos").json()} >= {"prova.progresso"}


def test_visualizador_nao_executa(visualizador, cliente_demo):
    c, _ = visualizador
    r = c.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"duracao_s": 0, "passos": 1}})
    assert r.status_code == 403 and r.json()["erro"] == "sem_privilegio"
    assert r.json()["detalhe"]["exigido"] == "jobs.executar"
    r = c.post("/api/agendas", json={"nome": "zt-visualizador", "tipo": "prova.progresso",
                                     "parametros": {}, "cron": "30 3 * * *"})
    assert r.status_code == 403 and r.json()["detalhe"]["exigido"] == "jobs.executar"


def test_visualizador_nao_ve_nem_cancela_job_de_outro(visualizador, cliente_demo, worker_vivo):
    """O job do admin existe e o visualizador nem lê (404 pelo filtro de dono) nem cancela (403 antes disso)."""
    c, _ = visualizador
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    assert c.get(f"/api/jobs/{job['id']}").status_code == 404
    r = c.post(f"/api/jobs/{job['id']}/cancelar")
    assert r.status_code == 403 and r.json()["detalhe"]["exigido"] == "jobs.executar"


def test_editor_continua_lendo_e_executando(usuarios_a):
    c, _, _ = usuarios_a.sessao("editor")
    privilegios = c.get("/api/eu").json()["privilegios"]
    assert {"jobs.ver", "jobs.executar"} <= set(privilegios)
    for rota in LEITURA:
        assert c.get(rota).status_code == 200, rota
    job = criar_job(c, "prova.progresso", {"duracao_s": 0, "passos": 1})
    assert c.get(f"/api/jobs/{job['id']}").status_code == 200
    assert c.post(f"/api/jobs/{job['id']}/cancelar").status_code == 202


def test_openapi_declara_os_dois_privilegios_da_fila():
    from tests.api.conftest import arquivo_openapi

    spec = arquivo_openapi()
    esperado = {
        ("get", "/api/jobs"): "jobs.ver",
        ("get", "/api/jobs/resumo"): "jobs.ver",
        ("get", "/api/jobs/tipos"): "jobs.ver",
        ("get", "/api/jobs/{job_id}"): "jobs.ver",
        ("get", "/api/jobs/{job_id}/log"): "jobs.ver",
        ("get", "/api/jobs/{job_id}/eventos"): "jobs.ver",
        ("get", "/api/agendas"): "jobs.ver",
        ("get", "/api/agendas/{agenda_id}"): "jobs.ver",
        ("post", "/api/jobs"): "jobs.executar",
        ("post", "/api/jobs/{job_id}/cancelar"): "jobs.executar",
        ("post", "/api/jobs/{job_id}/repetir"): "jobs.executar",
        ("post", "/api/agendas"): "jobs.executar",
        ("put", "/api/agendas/{agenda_id}"): "jobs.executar",
        ("delete", "/api/agendas/{agenda_id}"): "jobs.executar",
        ("post", "/api/agendas/{agenda_id}/rodar-agora"): "jobs.executar",
    }
    for (metodo, caminho), privilegio in esperado.items():
        op = spec["paths"][caminho][metodo]
        assert op["x-privilegio"] == privilegio, (metodo, caminho, op.get("x-privilegio"))


def test_token_de_visualizador_le_e_nao_executa(visualizador, cliente):
    """Token de serviço com escopo jobs:executar cujo dono é visualizador: o escopo passa, o privilégio decide.
    Lê (200, exige jobs.ver, que ele tem) e não executa (403, exige jobs.executar, que ele não tem)."""
    c, _ = visualizador
    r = c.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-vis-jobs", "escopos": ["jobs:executar"]})
    assert r.status_code == 201, r.text
    tok, tid = r.json()["token"], r.json()["id"]
    try:
        for rota in LEITURA:
            resp = com_token(cliente, tok, "GET", rota)
            assert resp.status_code == 200, (rota, resp.status_code, resp.text)
        resp = com_token(cliente, tok, "POST", "/api/jobs",
                         json={"tipo": "prova.progresso", "parametros": {"duracao_s": 0, "passos": 1}})
        assert resp.status_code == 403 and resp.json()["detalhe"]["exigido"] == "jobs.executar"
    finally:
        c.delete(f"/api/tokens/{tid}")
