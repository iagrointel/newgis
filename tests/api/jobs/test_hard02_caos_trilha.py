"""Caos de TRILHA no meio do job (cláusula do HARD-02 que faltava). O caos de banco é do
tests/api/adversario (wt/cx4h08) e o reinício da unidade de produção é do test_jobs_reinicio.py — aqui
os processos mortos são os da trilha mesma: o worker é um subprocesso da suíte (não há systemd de
trilha) e a API é um uvicorn próprio nesta porta.

Prova 1 — worker de trilha morto no meio: kill -9 no worker com o job rodando; ninguém ceifa enquanto
não há worker (o job segue 'rodando', sem marcador gravado no meio); o worker NOVO ceifa por heartbeat
vencido (migração 012: limite de 60 s, ceifa na partida e a cada 30 s), devolve o job (reinicios=1) e
o retoma; o job nunca saiu do rastro e cancela limpo.

Prova 2 — API de trilha morta no meio: kill -9 no uvicorn com o job rodando; o job não sumiu: uma API
nova (mesma trilha, mesmo banco) responde 200 para o MESMO cookie — a sessão vive no banco, não no
processo — o job segue sendo executado pelo MESMO worker (a morte da API não é devolução) e o
cancelamento segue funcionando pela API nova.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import pytest

from tests import jobs_sessao
from tests.api.jobs.conftest import WorkerExtra, porta_livre

ROOT = Path(__file__).resolve().parents[3]
COOKIE = jobs_sessao.COOKIE_SESSAO
FINAIS = ("concluido", "falhou", "cancelado")
PROVA = {"tipo": "prova.progresso", "parametros": {"duracao_s": 300, "passos": 60}}

pytestmark = [
    pytest.mark.lento,
    pytest.mark.skipif(os.environ.get("PLAT_SCHEMA", "plat") == "plat",
                       reason="caos de trilha: nunca corre contra o schema plat (o processo morto aqui "
                              "é subprocesso da suíte; contra produção o rastro ficaria na mesma base)"),
]


class ApiTrilha:
    """uvicorn em subprocesso com o env da trilha (o mesmo app de produção, PLAT_SCHEMA da trilha). A
    porta é pedida ao sistema (bind 0, mesmo padrão do worker extra); tudo é morto por PID exato,
    nunca por pkill."""

    def __init__(self, env: dict, nome: str):
        self.env = env
        self.nome = nome
        self.porta = porta_livre()
        self.proc: subprocess.Popen | None = None
        self.iniciar()

    def iniciar(self) -> None:
        ambiente = {k: v for k, v in os.environ.items()}
        ambiente.update({k: v for k, v in self.env.items() if v is not None})
        ambiente.setdefault("PLAT_AMBIENTE", "dev")
        ambiente["PYTHONNOUSERSITE"] = "1"
        # uma única reposição: porta em TIME_WAIT morre no bind e pede outra ao sistema; env quebrado
        # morre de novo e falha aqui, sem encher a máquina de processo
        for _reposicao in range(2):
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                 "--port", str(self.porta), "--no-access-log", "--log-level", "warning"],
                cwd=ROOT, env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            morreu = False
            for _ in range(100):
                if self.proc.poll() is not None:
                    morreu = True  # bind recusado (porta em TIME_WAIT): tenta de novo com outra porta
                    break
                try:
                    with urllib.request.urlopen(self.url("/saude"), timeout=1) as r:
                        if r.status == 200:
                            return
                except OSError:
                    pass
                time.sleep(0.2)
            if not morreu:
                break
            self.porta = porta_livre()
        self.parar()
        pytest.fail(f"uvicorn {self.nome} não respondeu /saude (:{self.porta}) em 20 s")

    def url(self, caminho: str) -> str:
        return f"http://127.0.0.1:{self.porta}{caminho}"

    def http(self, metodo: str, caminho: str, token: str | None = None, corpo: dict | None = None) -> httpx.Response:
        return httpx.request(metodo, self.url(caminho), json=corpo,
                             cookies={COOKIE: token} if token else None, timeout=10.0)

    def matar(self) -> None:
        assert self.proc is not None and self.proc.poll() is None, "API já estava morta antes do caos"
        self.proc.kill()
        self.proc.wait(timeout=15)

    def parar(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture(scope="module")
def api_trilha(env):
    api = ApiTrilha(env, f"caos-{os.getpid()}")
    yield api
    api.parar()


@pytest.fixture(scope="module")
def token(env):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        return jobs_sessao.criar_sessao(con, "demo", "admin")[0]
    finally:
        con.close()


@pytest.fixture
def iniciar_worker(env):
    """Fábrica de worker de trilha em subprocesso (WorkerExtra); todos encerrados no fim do teste."""
    vivos: list[WorkerExtra] = []

    def _iniciar(nome_base: str, processos: int = 1) -> WorkerExtra:
        w = WorkerExtra(env, nome_base, processos)
        vivos.append(w)
        return w

    yield _iniciar
    for w in vivos:
        w.parar()


def _job(api: ApiTrilha, token: str, job_id: str) -> dict:
    r = api.http("GET", f"/api/jobs/{job_id}", token)
    assert r.status_code == 200, r.text
    return r.json()


def _esperar(api: ApiTrilha, token: str, job_id: str, timeout: float, condicao=None) -> dict:
    fim = time.monotonic() + timeout
    ultimo: dict | None = None
    while time.monotonic() < fim:
        ultimo = _job(api, token, job_id)
        if condicao is not None and condicao(ultimo):
            return ultimo
        if condicao is None and ultimo["estado"] in FINAIS:
            return ultimo
        time.sleep(0.3)
    pytest.fail(f"job {job_id} não chegou lá em {timeout} s: {json.dumps(ultimo)[:400]}")


def _marcadores(con, job_id) -> list[str]:
    with con.cursor() as cur:
        cur.execute("SELECT marcador FROM plat_trabalho.marcadores WHERE job_id = %s", (job_id,))
        r = [str(x["marcador"]) for x in cur.fetchall()]
    con.rollback()
    return r


def test_worker_de_trilha_morto_no_meio_e_ceifado_pelo_worker_novo(
        api_trilha, token, iniciar_worker, conexao_plat_app):
    a = iniciar_worker(f"caos-a-{os.getpid()}")
    r = api_trilha.http("POST", "/api/jobs", token, PROVA)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    rodando = _esperar(api_trilha, token, job_id, 60,
                       lambda j: j["estado"] == "rodando" and j["progresso"] >= 3)
    assert rodando["worker"] == a.nome, "quem executa é o worker de trilha da própria suíte"

    a.parar("KILL")  # kill -9: sem despedida, sem devolução na hora
    orfao = _job(api_trilha, token, job_id)
    assert orfao["estado"] == "rodando", "job órfão segue 'rodando': sem worker ninguém ceifa"
    assert _marcadores(conexao_plat_app, job_id) == [], "nenhum marcador no meio da execução"

    b = iniciar_worker(f"caos-b-{os.getpid()}")  # quem levanta é a suíte: não há systemd de trilha
    devolvido = _esperar(api_trilha, token, job_id, 150,
                         lambda j: j["reinicios"] >= 1 and j["estado"] in ("pendente", "rodando"))
    assert devolvido["reinicios"] == 1 and devolvido["tentativa"] <= 2
    retomado = _esperar(api_trilha, token, job_id, 90,
                        lambda j: j["estado"] == "rodando" and j["progresso"] >= 1)
    assert retomado["worker"] == b.nome, "quem retomou é o worker NOVO, nunca o morto"
    assert _marcadores(conexao_plat_app, job_id) == []

    assert api_trilha.http("POST", f"/api/jobs/{job_id}/cancelar", token).status_code == 202
    fim = _esperar(api_trilha, token, job_id, 30)
    assert fim["estado"] == "cancelado" and fim["reinicios"] == 1


def test_api_de_trilha_morta_no_meio_o_job_segue_e_a_sessao_sobrevive(api_trilha, token, iniciar_worker):
    w = iniciar_worker(f"caos-api-{os.getpid()}")
    r = api_trilha.http("POST", "/api/jobs", token, PROVA)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    _esperar(api_trilha, token, job_id, 60, lambda j: j["estado"] == "rodando" and j["progresso"] >= 3)

    api_trilha.matar()  # kill -9 no uvicorn da trilha, com o job rodando
    with pytest.raises(httpx.HTTPError):
        api_trilha.http("GET", f"/api/jobs/{job_id}", token)

    api_trilha.iniciar()  # mesma trilha, mesmo banco, MESMO cookie
    j = _job(api_trilha, token, job_id)
    assert j["estado"] in ("pendente", "rodando"), j
    assert j["reinicios"] == 0, "morte da API não é morte de worker: ninguém devolve o job por isso"
    assert j["worker"] == w.nome, "o worker que executava segue o mesmo"

    assert api_trilha.http("POST", f"/api/jobs/{job_id}/cancelar", token).status_code == 202
    assert _esperar(api_trilha, token, job_id, 30)["estado"] == "cancelado"
