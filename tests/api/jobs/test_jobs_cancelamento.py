"""Cancelamento e morte (ADR 0003 seção 6): cancelar rodando cooperativo em <= 2 s sem deixar a tabela de trabalho;
cancelar pendente é imediato; cancelar concluído = 409; timeout_s excedido = falhou "tempo esgotado"; tarefa que
ignora a flag morre em 30 + 10 s (lento)."""

import time

import pytest

from tests.api.jobs.conftest import criar_job, esperar


def _tabela_de_trabalho_existe(con, job_id: str) -> bool:
    """Efeito parcial de prova.progresso: linhas em plat_trabalho.passos (apagadas na limpeza)."""
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM plat_trabalho.passos WHERE job_id = %s LIMIT 1", (job_id,))
        existe = cur.fetchone() is not None
    con.rollback()
    return existe


def test_cancelar_rodando_em_ate_2_s(cliente_demo, worker_vivo, conexao_plat_app, medida):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 120, "passos": 120})
    rodando = esperar(cliente_demo, job["id"], timeout=60,
                      condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 2)
    assert _tabela_de_trabalho_existe(conexao_plat_app, job["id"]), "a tarefa de prova grava efeito parcial ao iniciar"
    t0 = time.perf_counter()
    r = cliente_demo.post(f"/api/jobs/{job['id']}/cancelar")
    assert r.status_code == 202 and r.json()["cancelar_solicitado"] is True and r.json()["estado"] == "rodando"
    fim = esperar(cliente_demo, job["id"], timeout=30)
    cancelamento_s = round(time.perf_counter() - t0, 3)
    assert fim["estado"] == "cancelado" and fim["cancelado_por"] == rodando["usuario_id"] and fim["cancelado_em"]
    assert fim["progresso"] < 100 and fim["tentativa"] == 1
    assert not _tabela_de_trabalho_existe(conexao_plat_app, job["id"]), "tabela de trabalho sobrou após cancelar"
    medida("L0-05-jobs")("cancelamento_s", cancelamento_s, "s",
                         "POST /api/jobs/{id}/cancelar em prova.progresso rodando até estado=cancelado "
                         "(tests/api/jobs/test_jobs_cancelamento.py)")
    assert cancelamento_s <= 2.0, cancelamento_s


def test_cancelar_pendente_e_imediato(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 1, "passos": 1},
                    agendado_para="2099-01-01T00:00:00Z")
    assert job["estado"] == "pendente"
    r = cliente_demo.post(f"/api/jobs/{job['id']}/cancelar")
    assert r.status_code == 202 and r.json()["estado"] == "cancelado"
    assert r.json()["erro"] == "cancelado antes de iniciar"
    assert r.json()["terminado_em"] and r.json()["tentativa"] == 0


def test_cancelar_concluido_e_409_e_estado_final_e_imutavel(cliente_demo, worker_vivo, conexao_plat_app, sessao_demo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    fim = esperar(cliente_demo, job["id"], timeout=60)
    assert fim["estado"] == "concluido" and fim["progresso"] == 100
    r = cliente_demo.post(f"/api/jobs/{job['id']}/cancelar")
    assert r.status_code == 409 and r.json()["erro"] == "estado_final"
    # nem sob o contexto do próprio inquilino plat_app altera plat.job (006: REVOKE UPDATE; cancelar é por função)
    import psycopg2

    from tests import jobs_sessao

    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, sessao_demo[1], sessao_demo[2], "admin")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege, match="permission denied"):
            cur.execute("UPDATE plat.job SET estado = 'pendente' WHERE id = %s", (job["id"],))
    conexao_plat_app.rollback()


def test_timeout_excedido_marca_falhou_tempo_esgotado(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.tempo_esgotado", {"duracao_s": 60})
    assert job["timeout_s"] == 5
    fim = esperar(cliente_demo, job["id"], timeout=40)
    assert fim["estado"] == "falhou" and fim["erro"] == "tempo esgotado (timeout_s = 5)"
    assert fim["duracao_s"] >= 5 and fim["duracao_s"] < 30


@pytest.mark.lento
def test_tarefa_que_ignora_a_flag_e_morta_em_30_mais_10_s(cliente_demo, worker_vivo, medida):
    job = criar_job(cliente_demo, "prova.ignora_cancelamento", {"duracao_s": 300})
    esperar(cliente_demo, job["id"], timeout=60, condicao=lambda j: j["estado"] == "rodando")
    time.sleep(1)
    t0 = time.perf_counter()
    assert cliente_demo.post(f"/api/jobs/{job['id']}/cancelar").status_code == 202
    fim = esperar(cliente_demo, job["id"], timeout=90)
    demora = round(time.perf_counter() - t0, 1)
    assert fim["estado"] == "cancelado" and fim["erro"] == "morto após ignorar cancelamento"
    assert 30 <= demora <= 60, demora
    medida("L0-05-jobs")("cancelamento_forcado_s", demora, "s",
                         "prova.ignora_cancelamento: pedido até SIGTERM (30 s) + SIGKILL (10 s) e estado cancelado")
