"""Sobrevivência a reinício (lento; refutação do item): no meio de um job, `systemctl restart plat-worker` devolve o
job (reinicios=1, tentativa segue 1) e o worker novo o termina; `kill -9` no pai mata o filho (PDEATHSIG), a ceifa
por heartbeat vencido (nunca por nome, 012) devolve em até ~90 s e o job conclui; 3 × kill -9 = falhou, nunca
`concluido`; em nenhum momento `concluido` sem o marcador do último passo. Exige `sudo -n systemctl`; pula com
mensagem quando não há sudo.

Migração `20260906T1615a3f` (recurso partilhado, achado do adversário G3 no L0-05-a: 3 SIGKILL seguidos no
mesmo job terminavam em `concluido`, porque a ceifa por heartbeat vencido devolvia como REINÍCIO, e o teto de
reinícios era 5): morte do executor sem sinal (`plat.job_ceifar`, chamada na ceifa da partida e do laço do
worker) passou a consumir TENTATIVA, não reinício — `reinicios` ficou só para a parada LIMPA do worker
(`systemctl restart`, `_parar()`, que continua devolvendo com `p_conta_tentativa := false`). Por isso os dois
testes de `kill -9` abaixo (que derrubam o processo inteiro sem sinal, sem passar por `_parar()`) agora leem
`tentativa`, não `reinicios` — `reinicios` fica em 0 do início ao fim nos dois. Confirmado por simulação SQL
direta em `plat_tpartilha` antes desta edição: 3 chamadas de `job_pegar`+`job_devolver(..., true, ...)` levam
tentativa 1→2→3 e falham exatamente na 3ª, com `reinicios` sempre 0 (prova.progresso tem `max_tentativas=3`,
`app/jobs/tipos_prova.py`)."""

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
    # kill -9: ninguém devolve na hora; a ceifa por heartbeat vencido (60 s, a cada 30 s) recoloca em até ~90 s
    # (012). Migração 20260906T1615a3f: a ceifa por heartbeat vencido (job_ceifar) devolve consumindo
    # TENTATIVA, não reinício — reinicios fica em 0 (essa contagem é só da parada LIMPA, systemctl restart).
    devolvido = esperar(cliente_demo, job["id"], timeout=150,
                        condicao=lambda j: j["tentativa"] >= 2 and j["estado"] in ("pendente", "rodando"))
    assert devolvido["reinicios"] == 0 and devolvido["estado"] != "concluido"
    fim = esperar(cliente_demo, job["id"], timeout=120)
    assert fim["estado"] == "concluido" and fim["tentativa"] == 2 and fim["reinicios"] == 0
    assert _marcadores(conexao_plat_app, job["id"]) == [fim["resultado"]["marcador"]]
    assert fim["proveniencia"].get("reinicios", 0) == 0


def test_tres_kill_9_marcam_falhou_e_nunca_concluido(cliente_demo, worker_vivo, conexao_plat_app, env):
    """Refutação literal do L0-05-a (achado do adversário G3): 'mata o worker com SIGKILL (não SIGTERM) 3
    vezes seguidas no mesmo job e verifica que o job termina falhou na 4a e nunca concluido'. Antes do
    conserto, 3 mortes só somavam reinicios=3 (teto 5) e a 4a passagem completava o job normalmente —
    CAIU (medido: `laco/handoffs/T3/ataque-g3-ADVERSARIO.md`, bloco L0-05-a item 1). Agora a ceifa consome
    tentativa; prova.progresso tem max_tentativas=3 (app/jobs/tipos_prova.py), então a 3a morte já fecha em
    falhou — nunca chega a existir uma 4a passagem."""
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 600, "passos": 600})
    for k in range(1, 4):
        esperar(cliente_demo, job["id"], timeout=150,
                condicao=lambda j, k=k: j["estado"] == "rodando" and j["tentativa"] == k and j["progresso"] >= 1)
        assert _systemctl("kill", "-s", "KILL").returncode == 0
        _pid_worker(env)
    fim = esperar(cliente_demo, job["id"], timeout=150)
    assert fim["estado"] == "falhou" and fim["tentativa"] == 3 and fim["reinicios"] == 0
    assert fim["erro"] == "worker morreu sem terminar o trabalho"
    assert _marcadores(conexao_plat_app, job["id"]) == []
