"""Memória (ADR 0003 seção 4.3): prova.memoria(mb=600) sob memoria_mb=256 morre por MemoryError no filho, o job vai
a `falhou` com "memória excedida (limite 256 MB)" e o worker continua vivo (/saude em :8153 responde)."""

import json
import urllib.request

from tests.api.jobs.conftest import criar_job, esperar


def _saude_worker(env) -> dict:
    url = (env.get("PLAT_WORKER_URL") or "http://127.0.0.1:8153").rstrip("/") + "/saude"
    with urllib.request.urlopen(url, timeout=3) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode("utf-8"))


def test_job_que_estoura_memoria_falha_e_o_worker_sobrevive(cliente_demo, worker_vivo, env, medida):
    antes = _saude_worker(env)
    job = criar_job(cliente_demo, "prova.memoria", {"mb": 600})
    assert job["memoria_mb"] == 256
    fim = esperar(cliente_demo, job["id"], timeout=60)
    assert fim["estado"] == "falhou" and fim["erro"] == "memória excedida (limite 256 MB)", fim["erro"]
    assert fim["tentativa"] == 1 and fim["reinicios"] == 0
    depois = _saude_worker(env)
    assert depois["pid"] == antes["pid"], "o worker reiniciou durante o job de memória"
    assert job["id"] not in depois["rodando"]
    log = cliente_demo.get(f"/api/jobs/{job['id']}/log").json()
    assert any("alocando 600 MB" in li["mensagem"] for li in log["linhas"])
    medida("L0-05-jobs")("rss_worker_kb", depois["rss_kb"], "kB",
                         "VmRSS do processo pai do worker lido em GET :8153/saude depois do job de memória "
                         "(tests/api/jobs/test_jobs_memoria.py); MemoryPeak da unidade é do testador")


def test_job_dentro_do_limite_conclui(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.memoria", {"mb": 64})
    fim = esperar(cliente_demo, job["id"], timeout=60)
    assert fim["estado"] == "concluido" and fim["resultado"] == {"mb": 64, "alocado": True}
