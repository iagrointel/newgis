"""Fixtures da fila (ADR 0003 seção 12): sessões demo/demo2, TestClient com cookie, espera por estado, worker vivo
(a unidade plat-worker tem de estar ativa: os jobs de prova rodam nela), worker extra em subprocesso com 2 processos
para os testes de concorrência (sempre encerrado no fim, nunca fica rodando fora do systemd)."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests import jobs_sessao

ROOT = Path(__file__).resolve().parents[3]
FINAIS = ("concluido", "falhou", "cancelado")
PORTA_WORKER_EXTRA = 18159


@pytest.fixture(scope="session")
def sessao_demo(env):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        return jobs_sessao.criar_sessao(con, "demo", "admin")
    finally:
        con.close()


@pytest.fixture(scope="session")
def sessao_demo2(env):
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        return jobs_sessao.criar_sessao(con, "demo2", "admin")
    finally:
        con.close()


@pytest.fixture(scope="session")
def sessao_plataforma(env):
    """Admin do inquilino técnico `plataforma` (tests/credenciais.txt): é onde os periódicos (L0-05-d) vivem —
    testar `jobs.expurgo` fora deste contexto levanta (a função recusa; migração 006)."""
    con = jobs_sessao.conectar(env["PLAT_DSN"])
    try:
        return jobs_sessao.criar_sessao(con, "plataforma", "admin")
    finally:
        con.close()


def _cliente_com_cookie(token: str):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, cookies={jobs_sessao.COOKIE_SESSAO: token})


@pytest.fixture(scope="session")
def cliente_demo(env, sessao_demo):
    with _cliente_com_cookie(sessao_demo[0]) as c:
        yield c


@pytest.fixture(scope="session")
def cliente_demo2(env, sessao_demo2):
    with _cliente_com_cookie(sessao_demo2[0]) as c:
        yield c


@pytest.fixture(scope="session")
def cliente_plataforma(env, sessao_plataforma):
    with _cliente_com_cookie(sessao_plataforma[0]) as c:
        yield c


@pytest.fixture(scope="session")
def worker_vivo(env, cliente):
    """A suíte exige a unidade plat-worker ativa (ou `make worker`): sem worker nenhum job de prova termina."""
    r = cliente.get("/saude").json()
    fila = r.get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.fail(f"nenhum worker vivo em /saude ({fila}); rode `sudo systemctl start plat-worker` ou `make worker`")
    return fila


def criar_job(cliente, tipo: str, parametros: dict | None = None, **extra) -> dict:
    corpo = {"tipo": tipo, "parametros": parametros or {}, **extra}
    r = cliente.post("/api/jobs", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def esperar(cliente, job_id: str, estados=FINAIS, timeout: float = 60, condicao=None) -> dict:
    """Espera o job chegar a um dos estados (ou satisfazer `condicao(job)`); falha com o último JSON visto."""
    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = cliente.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if condicao is not None and condicao(ultimo):
            return ultimo
        if condicao is None and ultimo["estado"] in estados:
            return ultimo
        time.sleep(0.2)
    pytest.fail(f"job {job_id} não chegou a {estados} em {timeout} s: {json.dumps(ultimo)[:600]}")


class WorkerExtra:
    """Worker em subprocesso (só para teste; sempre encerrado no fim). `nome` é a identidade `<base>:<pid>` que o
    processo registra; `saude()` lê o /saude dele."""

    def __init__(self, env: dict, nome_base: str, processos: int = 1, porta: int = PORTA_WORKER_EXTRA):
        ambiente = {k: v for k, v in os.environ.items()}
        ambiente.update({k: v for k, v in env.items() if v is not None})
        ambiente.update({"PYTHONNOUSERSITE": "1", "PLAT_WORKER_NOME": nome_base,
                         "PLAT_WORKER_PROCESSOS": str(processos), "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}"})
        self.nome_base = nome_base
        self.porta = porta
        self.proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                self.saude()
                break
            except OSError:
                time.sleep(0.2)
        else:
            self.proc.kill()
            pytest.fail(f"worker extra {nome_base} não respondeu em /saude (:{porta}) em 10 s")
        self.nome = self.saude()["worker"]

    def saude(self) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/saude", timeout=1) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def parar(self, sinal: str = "TERM") -> None:
        if self.proc.poll() is not None:
            return
        (self.proc.kill if sinal == "KILL" else self.proc.terminate)()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture
def iniciar_worker(env):
    """Fábrica: iniciar_worker(nome_base, processos, porta) -> WorkerExtra; todos encerrados no fim do teste."""
    vivos: list[WorkerExtra] = []

    def _iniciar(nome_base: str, processos: int = 1, porta: int = PORTA_WORKER_EXTRA) -> WorkerExtra:
        w = WorkerExtra(env, nome_base, processos, porta)
        vivos.append(w)
        return w

    yield _iniciar
    for w in vivos:
        w.parar()


@pytest.fixture
def worker_extra(iniciar_worker):
    """Segundo worker (2 processos, /saude em :18159); devolve a identidade `<base>:<pid>`."""
    return iniciar_worker(f"teste-extra-{os.getpid()}", 2).nome
