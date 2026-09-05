"""RLS da fila (P6, ADR 0003 seção 2.2): inquilino A não vê, cancela, repete nem lê o log do job de B (404); sem
contexto 0 linhas em job/job_log/agenda; plat.worker inacessível a plat_app; usuário não-admin só vê os próprios
jobs; a API não expõe plat.worker."""

import psycopg2
import pytest

from tests import jobs_sessao
from tests.api.jobs.conftest import criar_job, esperar


@pytest.fixture(scope="module")
def job_de_demo(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    return esperar(cliente_demo, job["id"], timeout=60)


def test_a_nao_ve_job_de_b(cliente_demo, cliente_demo2, job_de_demo):
    jid = job_de_demo["id"]
    assert cliente_demo.get(f"/api/jobs/{jid}").status_code == 200
    for metodo, rota in (("GET", f"/api/jobs/{jid}"), ("POST", f"/api/jobs/{jid}/cancelar"),
                         ("POST", f"/api/jobs/{jid}/repetir"), ("GET", f"/api/jobs/{jid}/log"),
                         ("GET", f"/api/jobs/{jid}/eventos")):
        r = cliente_demo2.request(metodo, rota)
        assert r.status_code == 404, (metodo, rota, r.status_code, r.text[:200])
        assert r.json()["erro"] == "job_inexistente"
    ids_b = {j["id"] for j in cliente_demo2.get("/api/jobs", params={"limite": 200}).json()["itens"]}
    assert jid not in ids_b


def test_sem_contexto_zero_linhas_e_worker_inacessivel(conexao_plat_app, job_de_demo):
    with conexao_plat_app.cursor() as cur:
        for tabela in ("job", "job_log", "agenda"):
            cur.execute(f"SELECT count(*) AS n FROM plat.{tabela}")
            assert cur.fetchone()["n"] == 0, tabela
        cur.execute("SELECT count(*) AS n FROM plat_trabalho.passos")
        assert cur.fetchone()["n"] == 0, "efeito parcial de prova.progresso sobrou depois do fim dos jobs"
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT count(*) FROM plat.worker")
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT * FROM plat.fila_estado()")
        r = cur.fetchone()
        assert r["workers_vivos"] >= 1 and r["pendentes"] >= 0
    conexao_plat_app.rollback()


def test_insert_de_job_em_outro_inquilino_falha_no_with_check(conexao_plat_app, sessao_demo, sessao_demo2):
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, sessao_demo[1], sessao_demo[2], "admin")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="row-level security"):
            cur.execute("INSERT INTO plat.job(tenant_id, tipo, pesado, memoria_mb, timeout_s) "
                        "VALUES (%s, 'prova.progresso', false, 256, 60)", (sessao_demo2[1],))
    conexao_plat_app.rollback()


def test_job_log_de_b_invisivel_para_a(conexao_plat_app, sessao_demo, sessao_demo2, job_de_demo):
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, sessao_demo[1], sessao_demo[2], "admin")
        cur.execute("SELECT count(*) AS n FROM plat.job_log WHERE job_id = %s", (job_de_demo["id"],))
        assert cur.fetchone()["n"] >= 1
    conexao_plat_app.rollback()
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, sessao_demo2[1], sessao_demo2[2], "admin")
        cur.execute("SELECT count(*) AS n FROM plat.job_log WHERE job_id = %s", (job_de_demo["id"],))
        assert cur.fetchone()["n"] == 0
    conexao_plat_app.rollback()


def test_usuario_nao_admin_so_ve_os_proprios_jobs(env, cliente_demo, sessao_demo, job_de_demo):
    from tests.api.jobs.conftest import _cliente_com_cookie

    login = "editor_rls_jobs"
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        uid = jobs_sessao.criar_usuario_temporario(con, sessao_demo[1], sessao_demo[2], login, "editor")
        token, _, _ = jobs_sessao.criar_sessao(con, "demo", login)
        with _cliente_com_cookie(token) as editor:
            assert editor.get(f"/api/jobs/{job_de_demo['id']}").status_code == 404
            meu = criar_job(editor, "prova.progresso", {"duracao_s": 0, "passos": 1})
            assert meu["usuario_id"] == uid and meu["usuario_login"] == login
            ids = {j["id"] for j in editor.get("/api/jobs", params={"limite": 200}).json()["itens"]}
            assert meu["id"] in ids and job_de_demo["id"] not in ids
            assert cliente_demo.get(f"/api/jobs/{meu['id']}").status_code == 200, "admin vê o job do editor"
            esperar(cliente_demo, meu["id"], timeout=60)
            assert editor.post("/api/jobs", json={"tipo": "jobs.expurgo"}).json()["erro"] == "perfil_insuficiente"
    finally:
        jobs_sessao.apagar_usuario_temporario(con, sessao_demo[1], sessao_demo[2], login)
        con.close()


def test_api_nao_expoe_plat_worker(cliente):
    esquema = cliente.get("/api/openapi.json").json()
    assert not any("worker" in rota for rota in esquema["paths"]), list(esquema["paths"])
    for rota in ("/api/jobs", "/api/jobs/resumo", "/api/jobs/tipos", "/api/agendas"):
        assert rota in esquema["paths"], rota
