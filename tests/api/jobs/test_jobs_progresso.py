"""Portão literal (lento): job de 5 min (prova.progresso duracao_s=300, passos=60) com progresso em tempo real pelo
SSE (>= 60 eventos estado crescentes), heartbeat que avança a cada <= 10 s, conclusão com marcador e resultado.
Medidas tempo_job_5min_s e heartbeat_intervalo_max_s."""

import datetime
import time

import pytest

from tests.api.jobs.conftest import criar_job
from tests.api.jobs.test_jobs_sse import _eventos

pytestmark = pytest.mark.lento


def _dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_job_de_5_min_com_progresso_em_tempo_real(cliente_demo, worker_vivo, conexao_plat_app, medida):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 300, "passos": 60})
    t0 = time.perf_counter()
    estados, heartbeats, fim = [], [], None
    with cliente_demo.stream("GET", f"/api/jobs/{job['id']}/eventos") as r:
        assert r.status_code == 200
        for evento, _, dados in _eventos(r, maximo_s=420):
            if evento == "estado":
                estados.append((time.perf_counter() - t0, dados["progresso"], dados["estado"]))
                if dados["heartbeat_em"]:
                    heartbeats.append(_dt(dados["heartbeat_em"]))
            elif evento == "fim":
                fim = dados
                break
    tempo = round(time.perf_counter() - t0, 1)
    assert fim and fim["estado"] == "concluido" and fim["progresso"] == 100, fim
    progressos = [p for _, p, _ in estados]
    assert all(b >= a for a, b in zip(progressos, progressos[1:], strict=False)), progressos
    assert len(set(progressos)) >= 60, f"{len(set(progressos))} valores distintos de progresso"
    assert 300 <= tempo <= 360, tempo
    intervalos = [(b - a).total_seconds() for a, b in zip(heartbeats, heartbeats[1:], strict=False)]
    assert intervalos and max(intervalos) <= 10.0, max(intervalos)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT marcador FROM plat_trabalho.marcadores WHERE job_id = %s", (job["id"],))
        marcadores = [str(x["marcador"]) for x in cur.fetchall()]
    conexao_plat_app.rollback()
    assert marcadores == [fim["resultado"]["marcador"]]
    gravar = medida("L0-05-jobs")
    gravar("tempo_job_5min_s", tempo, "s", "prova.progresso(300 s, 60 passos) da criação ao evento fim pelo SSE")
    gravar("heartbeat_intervalo_max_s", round(max(intervalos), 1), "s",
           "maior intervalo entre heartbeat_em consecutivos vistos nos eventos estado do job de 5 min")
    gravar("eventos_estado_job_5min", len(estados), "eventos", "eventos estado recebidos pelo SSE no job de 5 min")
