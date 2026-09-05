"""Fila (ADR 0003 seção 12): 100 jobs executados exatamente uma vez com dois workers (3 processos) sem duplicata;
retentativa 2/4 s com traceback no log; FalhaDefinitiva sem retentativa; mesma chave em série; pesado nunca em
paralelo com pesado; criação valida tipo, parâmetros e perfil; medida jobs_vazios_por_min."""

import time

import pytest

from tests.api.jobs.conftest import criar_job, esperar


def test_tipos_listam_o_registro(cliente_demo):
    r = cliente_demo.get("/api/jobs/tipos")
    assert r.status_code == 200
    nomes = {t["nome"] for t in r.json()}
    assert {"prova.progresso", "prova.memoria", "prova.falha", "prova.pesado", "jobs.expurgo"} <= nomes
    prova = next(t for t in r.json() if t["nome"] == "prova.progresso")
    assert prova["memoria_mb"] == 256 and prova["executor"] == "local" and prova["perfil_minimo"] == "editor"
    assert "duracao_s" in prova["parametros_schema"]["properties"]


def test_criacao_valida_tipo_parametros_e_corpo(cliente_demo):
    r = cliente_demo.post("/api/jobs", json={"tipo": "nao.existe"})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_desconhecido" and r.json()["req_id"]
    r = cliente_demo.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 0}})
    assert r.status_code == 422 and r.json()["erro"] == "parametros_invalidos"
    assert r.json()["detalhe"][0]["campo"] == "passos"
    r = cliente_demo.post("/api/jobs", json={"tipo": "prova.progresso", "prioridade": 12})
    assert r.status_code == 422 and r.json()["erro"] == "prioridade_invalida"
    r = cliente_demo.post("/api/jobs", json={"parametros": {}})
    assert r.status_code == 422 and r.json()["erro"] == "corpo_invalido"


def test_sem_cookie_401_no_formato_d18(cliente):
    r = cliente.get("/api/jobs")
    assert r.status_code == 401
    assert set(r.json()) == {"erro", "mensagem", "req_id"} and r.json()["erro"] == "nao_autenticado"


def test_100_jobs_executados_exatamente_uma_vez(cliente_demo, worker_vivo, worker_extra, conexao_plat_app, medida):
    ids = []
    t0 = time.perf_counter()
    for _ in range(100):
        ids.append(criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})["id"])
    jobs = {i: esperar(cliente_demo, i, timeout=120) for i in ids}
    tempo_s = time.perf_counter() - t0
    estados = {j["estado"] for j in jobs.values()}
    assert estados == {"concluido"}, {i: (j["estado"], j["erro"]) for i, j in jobs.items()
                                      if j["estado"] != "concluido"}
    assert all(j["tentativa"] == 1 and j["reinicios"] == 0 for j in jobs.values())
    workers = {j["worker"] for j in jobs.values()}
    assert worker_extra in workers, f"o worker extra ({worker_extra}) não pegou nenhum job: {workers}"
    assert all(":" in w and w.rsplit(":", 1)[1].isdigit() for w in workers), workers  # identidade <base>:<pid>
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT job_id, count(*) AS n FROM plat_trabalho.marcadores WHERE job_id = ANY(%s::uuid[]) "
                    "GROUP BY job_id", (ids,))
        contagem = {str(r["job_id"]): r["n"] for r in cur.fetchall()}
    assert len(contagem) == 100 and set(contagem.values()) == {1}, "marcador ausente ou duplicado"
    por_min = round(100 / tempo_s * 60, 1)
    medida("L0-05-jobs")("jobs_vazios_por_min", por_min, "jobs/min",
                         "100 prova.progresso(duracao_s=0) criados pela API e concluídos por 2 workers "
                         "(plat-worker 1 processo + worker extra 2 processos); tests/api/jobs/test_jobs_fila.py")
    assert por_min >= 600, por_min


def test_excecao_comum_retenta_tres_vezes_e_falha_com_traceback(cliente_demo, worker_vivo, medida):
    job = criar_job(cliente_demo, "prova.falha", {"definitiva": False})
    t0 = time.perf_counter()
    fim = esperar(cliente_demo, job["id"], timeout=60)
    assert fim["estado"] == "falhou" and fim["tentativa"] == 3 and fim["reinicios"] == 0
    assert "falha comum de prova na tentativa 3" in fim["erro"]
    assert time.perf_counter() - t0 >= 6, "as esperas 2 s + 4 s entre tentativas não aconteceram"
    log = cliente_demo.get(f"/api/jobs/{job['id']}/log", params={"nivel": "ERRO"}).json()
    assert log["total"] == 3 and all("RuntimeError" in li["mensagem"] for li in log["linhas"])
    assert fim["proveniencia"]["tentativa"] == 3 and fim["proveniencia"]["git_sha"]


def test_falha_definitiva_nao_retenta(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.falha", {"definitiva": True})
    fim = esperar(cliente_demo, job["id"], timeout=30)
    assert fim["estado"] == "falhou" and fim["tentativa"] == 1 and "falha definitiva" in fim["erro"]
    log = cliente_demo.get(f"/api/jobs/{job['id']}/log").json()
    assert any("FalhaDefinitiva" in li["mensagem"] for li in log["linhas"])


def test_mesma_chave_roda_em_serie(cliente_demo, worker_vivo, worker_extra):
    chave = f"serie-{time.time_ns()}"
    a = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 2, "passos": 2, "chave": chave})
    b = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 2, "passos": 2, "chave": chave})
    fa, fb = esperar(cliente_demo, a["id"], timeout=60), esperar(cliente_demo, b["id"], timeout=60)
    assert fa["estado"] == fb["estado"] == "concluido" and fa["chave"] == chave
    primeiro, segundo = sorted((fa, fb), key=lambda j: j["iniciado_em"])
    assert segundo["iniciado_em"] >= primeiro["terminado_em"], (primeiro, segundo)


def test_pesado_nunca_em_paralelo_com_pesado(cliente_demo, worker_vivo, worker_extra):
    a = criar_job(cliente_demo, "prova.pesado", {"duracao_s": 3})
    b = criar_job(cliente_demo, "prova.pesado", {"duracao_s": 3})
    fa, fb = esperar(cliente_demo, a["id"], timeout=60), esperar(cliente_demo, b["id"], timeout=60)
    assert fa["estado"] == fb["estado"] == "concluido" and fa["pesado"] and fb["pesado"]
    primeiro, segundo = sorted((fa, fb), key=lambda j: j["iniciado_em"])
    assert segundo["iniciado_em"] >= primeiro["terminado_em"], (primeiro, segundo)


def test_listagem_filtra_e_ordena(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    esperar(cliente_demo, job["id"], timeout=60)
    r = cliente_demo.get("/api/jobs", params={"estado": "concluido", "tipo": "prova.progresso", "limite": 5})
    assert r.status_code == 200 and r.json()["total"] >= 1 and len(r.json()["itens"]) <= 5
    assert all(j["estado"] == "concluido" for j in r.json()["itens"])
    assert cliente_demo.get("/api/jobs", params={"estado": "x"}).json()["erro"] == "estado_invalido"
    assert cliente_demo.get("/api/jobs", params={"ordenar": "senha:asc"}).json()["erro"] == "ordenar_invalido"
    assert cliente_demo.get("/api/jobs", params={"de": "ontem"}).json()["erro"] == "data_invalida"
    resumo = cliente_demo.get("/api/jobs/resumo").json()
    assert set(resumo) == {"pendente", "rodando", "concluido_24h", "falhou_24h", "cancelado_24h"}
    assert resumo["concluido_24h"] >= 1


def test_repetir_cria_job_novo_com_proveniencia(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 2})
    esperar(cliente_demo, job["id"], timeout=60)
    r = cliente_demo.post(f"/api/jobs/{job['id']}/repetir", json={"parametros": {"passos": 3}})
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["id"] != job["id"] and novo["parametros"]["passos"] == 3 and novo["parametros"]["duracao_s"] == 0
    assert novo["proveniencia"]["repetido_de"] == job["id"]
    fim = esperar(cliente_demo, novo["id"], timeout=60)
    assert fim["estado"] == "concluido" and fim["proveniencia"]["repetido_de"] == job["id"]
    assert fim["resultado"]["passos"] == 3


@pytest.mark.parametrize("rota", ["/api/jobs/tipos", "/api/jobs/resumo", "/api/agendas"])
def test_rotas_de_leitura_respondem_sem_cache(cliente_demo, rota):
    r = cliente_demo.get(rota)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
