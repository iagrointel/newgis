"""Fixtures do SDK (item L2-16-a-sdk-python-geo): o SDK fala HTTP DE VERDADE (requests), então a
suíte sobe a app num servidor uvicorn em PORTA EFÊMERA (mesma app, mesmo schema da trilha, ambiente
do processo) e um worker da fila apontando para ele — os dois em subprocesso, sempre encerrados no
fim. Tokens de serviço são criados pela rota de sessão (POST /api/login + 2FA quando pede +
POST /api/tokens), exatamente como um usuário faria; o SDK em si nunca vê senha."""

import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
PACOTE = ROOT / "pacote"
if str(PACOTE) not in sys.path:  # o pacote mora fora de app/: entra no caminho antes do import
    sys.path.insert(0, str(PACOTE))

os.environ.setdefault("PLAT_AMBIENTE", "dev")

import plat  # noqa: E402
from plat import Plataforma  # noqa: E402

from tests.api.conftest import credenciais, totp_guardado  # noqa: E402

# itens criados pela suíte (a casa limpa por prefixo zt; a lixeira do catálogo aceita a exclusão)
PREFIXO = "zt-sdk-"


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _login_http(base: str, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    """Sessão HTTP com cookie, pela rota pública de login (com o passo 2FA quando o usuário liga)."""
    s = requests.Session()
    r = s.post(f"{base}/api/login", json={"inquilino": slug, "login": login, "senha": senha}, timeout=15)
    if r.status_code == 200 and r.json().get("exige_2fa"):
        from app.auth import totp

        assert segredo_totp, "usuário exige 2FA e o segredo não é conhecido"
        desafio = r.json()["desafio"]

        def _tentar():
            return s.post(f"{base}/api/login/2fa",
                          json={"desafio": desafio, "codigo": totp.codigo(segredo_totp)}, timeout=15)

        r = _tentar()
        if r.status_code != 200:  # anti-replay do passo de 30 s: esperar o próximo e repetir
            time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
            r = _tentar()
    r.raise_for_status()
    return s


def _criar_token(sessao, base: str, nome: str, escopos: list[str]) -> dict:
    r = sessao.post(f"{base}/api/tokens", json={"nome": f"{PREFIXO}{nome}", "escopos": escopos,
                                                "validade_dias": 1})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="session")
def servidor():
    """A app inteira em subprocesso (uvicorn, porta efêmera); /saude decide quando está de pé."""
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente["PYTHONNOUSERSITE"] = "1"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(porta), "--log-level", "warning"], cwd=ROOT, env=ambiente,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{base}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("servidor do SDK morreu na subida (veja o log do uvicorn)")
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("servidor do SDK não respondeu /saude em 30 s")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def worker(servidor):
    """Worker da fila apontando para o servidor desta suíte (jobs de ferramenta precisam de um)."""
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente.update({"PYTHONNOUSERSITE": "1", "PLAT_WORKER_NOME": f"sdk-{os.getpid()}",
                     "PLAT_WORKER_PROCESSOS": "1", "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}"})
    saida_erro = subprocess.DEVNULL
    if os.environ.get("PLAT_SDK_DEBUG"):
        saida_erro = open(f"/tmp/sdk-worker-{os.getpid()}.log", "wb")  # noqa: SIM115 — só com a chave
    proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
                            stdout=saida_erro, stderr=saida_erro)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("worker do SDK morreu na subida (PLAT_SDK_DEBUG=1 grava /tmp/sdk-worker-*.log)")
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("worker do SDK não respondeu em 10 s")
    yield
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def _sessao_admin(servidor: str, slug: str):
    creds = credenciais()
    assert slug in creds, f"trilha sem credencial do admin {slug} (PLAT_CREDENCIAIS_ARQUIVO)"
    login, senha = creds[slug]
    return _login_http(servidor, slug, login, senha, totp_guardado(slug))


@pytest.fixture(scope="session")
def _admin(servidor):
    """(sessão HTTP do admin demo, token admin:inquilino, id do token) — a sessão fica para a limpeza."""
    s = _sessao_admin(servidor, "demo")
    tok = _criar_token(s, servidor, f"admin-{os.getpid()}", ["admin:inquilino"])
    return s, tok["token"], tok["id"]


@pytest.fixture(scope="session")
def pla(servidor, _admin, worker) -> Plataforma:
    """SDK autenticado com o token do admin demo, com worker vivo para as ferramentas."""
    return Plataforma(servidor, _admin[1])


@pytest.fixture(scope="session")
def pla_demo2(servidor, worker) -> Plataforma:
    """Segundo inquilino (demo2): a refutação do item — item de A lido por B é 404 tipado, não 403."""
    s = _sessao_admin(servidor, "demo2")
    tok = _criar_token(s, servidor, f"demo2-{os.getpid()}", ["admin:inquilino"])
    try:
        yield Plataforma(servidor, tok["token"])
    finally:
        s.delete(f"{servidor}/api/tokens/{tok['id']}")


@pytest.fixture(scope="session")
def pla_leitura(servidor, _admin, worker) -> Plataforma:
    """Token de escopo SÓ-LEITURA cujo dono é um visualizador (o privilégio do token é o do dono)."""
    s_admin = _admin[0]
    login = f"zt{secrets.token_hex(4)}"
    r = s_admin.post(f"{servidor}/api/usuarios", json={"login": login, "nome": "SDK só leitura",
                                                       "perfil": "visualizador"})
    assert r.status_code == 201, r.text
    u = r.json()["usuario"]
    temporaria = r.json()["senha_temporaria"]
    s = _login_http(servidor, "demo", login, temporaria)
    definitiva = "Senha-definitiva-1" + secrets.token_hex(3)
    r = s.put(f"{servidor}/api/eu/senha", json={"atual": temporaria, "nova": definitiva})
    assert r.status_code == 204, r.text
    tok = _criar_token(s, servidor, f"leitura-{os.getpid()}", ["catalogo:ler"])
    try:
        yield Plataforma(servidor, tok["token"])
    finally:
        s.delete(f"{servidor}/api/tokens/{tok['id']}")
        s_admin.delete(f"{servidor}/api/usuarios/{u['id']}")


@pytest.fixture
def limpar_itens(pla):
    """Apaga os itens criados por um teste (lixeira lógica) no fim, mesmo com falha no meio."""
    ids: list[str] = []
    yield ids
    for iid in ids:
        try:
            pla.catalogo.apagar(iid)
        except Exception:
            pass


@pytest.fixture(scope="session")
def versao_sdk():
    return plat.__versao__
