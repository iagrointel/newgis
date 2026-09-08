"""Ambiente da suíte do SDK (item L7-08-b-sdk-python): sobe a API real da trilha (`app.main:app`) num
processo uvicorn de verdade — não `TestClient` em memória — porque a prova pedida é "o SDK contra a
API real da trilha", e o SDK fala HTTP de rede (retentativa, timeout, cookies inclusive). Sobe também
o worker da fila só para o exemplo de jobs. Reusa um processo já de pé na mesma porta se o `git_sha`
bater (outra chamada de teste no mesmo turno); nunca herda o servidor de OUTRA trilha."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
PORTA_API = int(os.environ.get("PLAT_SDK_PORTA", "8278"))
PORTA_WORKER_SAUDE = int(os.environ.get("PLAT_SDK_WORKER_PORTA", "8279"))
URL = f"http://127.0.0.1:{PORTA_API}"
GIT_SHA = subprocess.run(
    ["git", "-C", str(RAIZ), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
).stdout.strip()


def _ambiente_da_trilha() -> dict[str, str]:
    """`.env` da trilha (posto por `laco/trilha_ambiente.sh`) + o que falta pra subir sozinho: sem
    isso o teste depende de alguém ter feito `source` antes, que é exatamente o que quebrou a
    sessão anterior (retomada 07/09)."""
    arq = os.environ.get("PLAT_SDK_ENV_ARQUIVO", "/home/dev/plataforma/laco/var/trilha/il708bsdkpy.env")
    valores = dict(os.environ)
    if Path(arq).exists():
        for linha in Path(arq).read_text().splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            valores.setdefault(chave, valor)
    valores["PLAT_GIT_SHA"] = GIT_SHA
    valores.setdefault("PLAT_JOBS_DIR", "/tmp/il708bsdkpy_jobs")
    valores.setdefault("PLAT_WORKER_URL", f"http://127.0.0.1:{PORTA_WORKER_SAUDE}")
    Path(valores["PLAT_JOBS_DIR"]).mkdir(parents=True, exist_ok=True)
    return valores


def _saude(url: str, tempo_limite_s: float = 1.5) -> dict | None:
    try:
        r = httpx.get(f"{url}/saude", timeout=tempo_limite_s)
        if r.status_code == 200:
            return r.json()
    except httpx.HTTPError:
        pass
    return None


def _esperar_saude(url: str, segundos: float, contexto: str) -> dict:
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        corpo = _saude(url)
        if corpo is not None:
            return corpo
        time.sleep(0.3)
    pytest.fail(f"{contexto} não respondeu /saude em {segundos}s — ver log em /tmp/il708bsdkpy_*.log")


@pytest.fixture(scope="session")
def url_api() -> str:
    """URL da API da trilha (porta 8278, ver o prompt do item). Reusa um processo já respondendo
    com o MESMO git_sha (idempotente entre rodadas de teste no mesmo turno); começa um novo senão."""
    ambiente = _ambiente_da_trilha()
    corpo = _saude(URL)
    if corpo is not None and corpo.get("git_sha") == GIT_SHA[:12]:
        yield URL
        return
    if corpo is not None:
        pytest.fail(
            f"porta {PORTA_API} já respondia com git_sha {corpo.get('git_sha')!r} != {GIT_SHA[:12]!r} "
            "— é o servidor de OUTRA trilha ou de outro commit; pare-o antes de rodar este teste"
        )
    log = open("/tmp/il708bsdkpy_api.log", "w")
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORTA_API), "--host", "127.0.0.1"],
        cwd=str(RAIZ),
        env=ambiente,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        _esperar_saude(URL, 30, "a API da trilha (uvicorn)")
        yield URL
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()
        log.close()


@pytest.fixture(scope="session")
def worker_da_fila(url_api: str):
    """Worker da fila, só para o exemplo de jobs (`07_jobs.py`) — job sem worker fica "pendente"
    para sempre, e isso não é o que a cláusula do portão pede provar."""
    ambiente = _ambiente_da_trilha()
    ja_rodando = False
    try:
        httpx.get(f"http://127.0.0.1:{PORTA_WORKER_SAUDE}/saude", timeout=1.0)
        ja_rodando = True
    except httpx.HTTPError:
        pass
    if ja_rodando:
        yield
        return
    log = open("/tmp/il708bsdkpy_worker.log", "w")
    processo = subprocess.Popen(
        [sys.executable, "-m", "app.jobs.worker"], cwd=str(RAIZ), env=ambiente, stdout=log, stderr=subprocess.STDOUT
    )
    time.sleep(2)  # sem /saude síncrono documentado no boot; o log de "worker iniciado" é o sinal
    try:
        yield
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()
        log.close()


@pytest.fixture(scope="session")
def credenciais_demo() -> tuple[str, str, str]:
    """(inquilino, login, senha) do admin de `demo`, semeado por `trilha_ambiente.sh` em
    `laco/var/trilha/il708bsdkpy.credenciais.txt` — nunca uma senha digitada no código."""
    arq = Path(
        os.environ.get("PLAT_CREDENCIAIS_ARQUIVO", "/home/dev/plataforma/laco/var/trilha/il708bsdkpy.credenciais.txt")
    )
    for linha in arq.read_text().splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0] == "demo":
            return "demo", partes[1], partes[2]
    pytest.fail(f"credenciais de 'demo' não encontradas em {arq}")
