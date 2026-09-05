"""Sobrevivência a reinício (lento; refutação do item): no meio de um job, `systemctl restart plat-worker` devolve o
job (reinicios=1, tentativa segue 1) e o worker novo o termina; `kill -9` no pai mata o filho (PDEATHSIG), a ceifa
na partida devolve e o job conclui; 5 × kill -9 = falhou "devolvido 5 vezes"; em nenhum momento `concluido` sem o
marcador do último passo. Exige `sudo -n systemctl`; pula com mensagem quando não há sudo."""

import json
import subprocess
import time
import urllib.request

import pytest

from tests.api.jobs.conftest import criar_job, esperar

pytestmark = pytest.mark.lento
UNIDADE = "plat-worker"


def _sudo_ok() -> bool:
    return subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0


def _systemctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["sudo", "-n", "systemctl", *args, UNIDADE], capture_output=True, text=True, timeout=90)


def _pid_worker(env) -> int:
    url = (env.get("PLAT_WORKER_URL") or "http://127.0.0.1:8153").rstrip("/") + "/saude"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))["pid"]
        except OSError:
            time.sleep(0.5)
    pytest.fail("worker não voltou em /saude em 30 s")


def _marcadores(con, job_id) -> list:
    with con.cursor() as cur:
        cur.execute("SELECT marcador FROM plat_trabalho.marcadores WHERE job_id = %s", (job_id,))
        r = [str(x["marcador"]) for x in cur.fetchall()]
    con.rollback()
    return r


@pytest.fixture(autouse=True)
def exige_sudo():
    if not _sudo_ok():
        pytest.skip("sem sudo -n: os testes de reinício são do testador (sudo systemctl restart plat-worker)")
    assert _systemctl("is-active").stdout.strip() == "active", "unidade plat-worker inativa"


def test_restart_devolve_o_job_e_o_worker_novo_conclui(cliente_demo, worker_vivo, conexao_plat_app, env, medida):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 300, "passos": 60})
    esperar(cliente_demo, job["id"], timeout=60, condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 3)
    pid_antes = _pid_worker(env)
    t0 = time.perf_counter()
    r = _systemctl("restart")
    assert r.returncode == 0, r.stderr
    pid_depois = _pid_worker(env)
    assert pid_depois != pid_antes
    visto = esperar(cliente_demo, job["id"], timeout=60,
                    condicao=lambda j: j["reinicios"] >= 1 and j["estado"] in ("pendente", "rodando"))
    retomada_s = round(time.perf_counter() - t0, 1)
    assert visto["reinicios"] == 1 and visto["tentativa"] <= 2 and visto["estado"] != "concluido"
    assert _marcadores(conexao_plat_app, job["id"]) == [], "marcador gravado antes de a execução inteira terminar"
    # cancela para não esperar os 5 min inteiros de novo: o que se prova aqui é a devolução e a retomada
    rodando = esperar(cliente_demo, job["id"], timeout=60,
                      condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 1)
    assert rodando["tentativa"] == 1 and rodando["reinicios"] == 1 and rodando["worker"]
    assert cliente_demo.post(f"/api/jobs/{job['id']}/cancelar").status_code == 202
    assert esperar(cliente_demo, job["id"], timeout=30)["estado"] == "cancelado"
    medida("L0-05-jobs")("reinicio_retomada_s", retomada_s, "s",
                         "systemctl restart plat-worker no meio de prova.progresso até o job voltar a pendente/rodando "
                         "com reinicios=1 (tests/api/jobs/test_jobs_reinicio.py)")


def test_kill_9_no_pai_mata_o_filho_e_a_ceifa_na_partida_retoma(cliente_demo, worker_vivo, conexao_plat_app, env):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 40, "passos": 40})
    esperar(cliente_demo, job["id"], timeout=60, condicao=lambda j: j["estado"] == "rodando" and j["progresso"] >= 3)
    r = _systemctl("kill", "-s", "KILL")
    assert r.returncode == 0, r.stderr
    _pid_worker(env)
    devolvido = esperar(cliente_demo, job["id"], timeout=60,
                        condicao=lambda j: j["reinicios"] >= 1 and j["estado"] in ("pendente", "rodando"))
    assert devolvido["reinicios"] == 1 and devolvido["estado"] != "concluido"
    fim = esperar(cliente_demo, job["id"], timeout=120)
    assert fim["estado"] == "concluido" and fim["tentativa"] == 1 and fim["reinicios"] == 1
    assert _marcadores(conexao_plat_app, job["id"]) == [fim["resultado"]["marcador"]]
    assert fim["proveniencia"]["reinicios"] == 1


def test_cinco_kill_9_marcam_falhou_devolvido_5_vezes(cliente_demo, worker_vivo, conexao_plat_app, env):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 600, "passos": 600})
    for k in range(5):
        esperar(cliente_demo, job["id"], timeout=90,
                condicao=lambda j, k=k: j["estado"] == "rodando" and j["reinicios"] == k and j["progresso"] >= 1)
        assert _systemctl("kill", "-s", "KILL").returncode == 0
        _pid_worker(env)
    fim = esperar(cliente_demo, job["id"], timeout=90)
    assert fim["estado"] == "falhou" and fim["reinicios"] == 5
    assert fim["erro"].startswith("devolvido 5 vezes sem terminar")
    assert _marcadores(conexao_plat_app, job["id"]) == []
