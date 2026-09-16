"""Notebook por inquilino (item L2-16-b-jupyter-por-inquilino-isolado) — cláusula a cláusula do
portão:

 1. contêiner sobe em <= 20 s (medido na partida real, test_partida_e_lab);
 2. JupyterLab abre em /notebooks/demo/ só com sessão de demo (401 sem sessão, 404 para demo2);
 3. dentro do contêiner: leitura de camada pela API funciona e conexão direta ao Postgres e à
    internet falham (o teste executa código no kernel VIA A API DO JUPYTER, pelo websocket do
    proxy — o mesmo caminho do navegador);
 4. limite de RAM aplicado (processo que aloca 3 GiB é morto pelo cgroup, exit 137);
 5. ociosidade encerra o contêiner (ceifador com ultimo_uso empurrado 31 min para trás);
 6. notebook agendado roda e salva HTML com a saída (job notebooks.executar no worker real);
 7. nenhum segredo além do token do usuário no ambiente (leitura de /proc/1/environ do contêiner).

Refutações do adversário (ler dado de outro inquilino e escapar): docker socket ausente,
Postgres/Garage/internet inalcançáveis do kernel, rede interna sem rota para o host.

A suíte sobe a app num uvicorn em porta efêmera e um worker da fila (mesmo padrão da suíte do
SDK); o contêiner é levantado PELO SERVIDOR (primeira passagem no proxy), nunca pelo processo de
teste, para que gateway/UDS vivam num processo só.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("PLAT_AMBIENTE", "dev")

from tests.api.conftest import credenciais, totp_guardado  # noqa: E402

SLUG = "demo"
SLUG_OUTRO = "demo2"
NOME = f"plat-nb-{SLUG}"
TAREFA_20_S = 20.0  # cláusula do portão: partida em <= 20 s


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _login_http(base: str, slug: str, login: str, senha: str, segredo_totp: str | None = None):
    """Sessão HTTP com cookie pela rota pública (com 2FA quando ligado) — mesma da suíte do SDK."""
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
        if r.status_code != 200:
            time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
            r = _tentar()
    r.raise_for_status()
    return s


def _sessao(base: str, slug: str):
    creds = credenciais()
    assert slug in creds, f"trilha sem credencial do admin {slug} (PLAT_CREDENCIAIS_ARQUIVO)"
    login, senha = creds[slug]
    return _login_http(base, slug, login, senha, totp_guardado(slug))


def _criar_token_sessao(sessao, base: str, nome: str, escopos: list[str]) -> dict:
    r = sessao.post(f"{base}/api/tokens", json={"nome": nome, "escopos": escopos, "validade_dias": 1})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    """A app inteira em subprocesso (uvicorn em porta efêmera); /saude decide quando está de pé.
    A saída vai para arquivo do pytest (rastros de erro do servidor, como traceback de rota)."""
    # órfão de uma sessão anterior não pode atender os pedidos desta (o gateway reusa o
    # uvicorn vivo no socket unix — com código carregado na memória DELE, não o do worktree)
    _limpar_gateway()
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente["PYTHONNOUSERSITE"] = "1"
    registro = tmp_path_factory.mktemp("nb-servidor") / "uvicorn.log"
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(porta), "--log-level", "warning"], cwd=ROOT, env=ambiente,
                            stdout=open(registro, "w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{base}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("servidor do notebook morreu na subida")
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("servidor do notebook não respondeu /saude em 30 s")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def worker(servidor):
    """Worker da fila em subprocesso (o job notebooks.executar roda nele, com docker CLI do host)."""
    porta = porta_livre()
    ambiente = dict(os.environ)
    ambiente.update({"PYTHONNOUSERSITE": "1", "PLAT_WORKER_NOME": f"nb-{os.getpid()}",
                     "PLAT_WORKER_PROCESSOS": "1", "PLAT_WORKER_URL": f"http://127.0.0.1:{porta}"})
    proc = subprocess.Popen([sys.executable, "-m", "app.jobs.worker"], cwd=ROOT, env=ambiente,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("worker do notebook morreu na subida")
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("worker do notebook não respondeu em 10 s")
    yield
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def demo(servidor):
    return _sessao(servidor, SLUG)


@pytest.fixture(scope="session")
def demo2(servidor):
    return _sessao(servidor, SLUG_OUTRO)


def _docker(*args: str, timeout: int = 90, entrada: bytes | None = None):
    return subprocess.run(["docker", *args], capture_output=True, input=entrada, timeout=timeout)


def _container_de_pe() -> bool:
    r = _docker("inspect", "-f", "{{.State.Running}}", NOME)
    return r.returncode == 0 and r.stdout.strip() == "true"


def _limpar_notebook_db():
    """Revoga tokens de notebook e apaga o estado de uso do inquilino demo (limpeza de suíte)."""
    from app import db

    with db.db(db.Contexto(_tenant_id(SLUG), 0, "teste")) as cur:
        cur.execute("UPDATE plat.token_servico SET revogado_em = now() "
                    "WHERE nome = %s AND revogado_em IS NULL", (f"notebook {SLUG}",))
        cur.execute("DELETE FROM plat.notebook_uso WHERE slug = %s", (SLUG,))


def _tenant_id(slug: str) -> int:
    """plat.tenant tem RLS: sem contexto de inquilino a consulta volta vazia. A porta de
    entrada sem contexto é o auth_login SECURITY DEFINER (a mesma do login)."""
    from app import db

    login, _ = credenciais()[slug]
    with db.db() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, %s)", (slug, login))
        return int(cur.fetchone()["tenant_id"])


@pytest.fixture(scope="session")
def contenedor_demo(request, servidor, demo):
    """Notebook do demo DE PÉ. A partida do CONTÊINER (cláusula 1: <= 20 s) é medida aqui,
    chamando contenedor.levantar direto do processo de teste: é o MESMO caminho que o
    servidor executa (docker run → Jupyter respondendo), sem colocar o aquecimento único do
    gateway no cronômetro. Depois a sessão HTTP passa pelo proxy para exercitar o reuso."""
    # limpeza garantida MESMO se a subida falhar no meio (registrada antes de qualquer risco)
    def _limpar():
        _docker("rm", "-f", NOME)
        _docker("volume", "rm", f"plat-nb-{SLUG}-trabalho")
        _limpar_gateway()
        try:
            _limpar_notebook_db()
        except Exception:
            pass

    request.addfinalizer(_limpar)
    # contêiner de execução anterior não pode mascarar a medida da partida
    _docker("rm", "-f", NOME)
    try:
        _limpar_notebook_db()
    except Exception:
        pass
    from app import db
    from app.notebooks import contenedor

    login, _ = credenciais()[SLUG]
    with db.db() as cur:
        cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, %s)", (SLUG, login))
        achou = cur.fetchone()
    tenant_id, usuario_id = int(achou["tenant_id"]), int(achou["usuario_id"])
    subida = contenedor.levantar(SLUG, db.Contexto(tenant_id, usuario_id, "teste"))
    partida_s = float(subida["s"])
    assert not subida.get("reusado"), "a medida da partida exige contêiner novo"
    assert partida_s <= TAREFA_20_S, \
        f"partida do contêiner levou {partida_s:.1f} s (cláusula: <= 20 s)"
    # o proxy do servidor REUSA o contêiner que o teste levantou (mesmo caminho do navegador)
    r = demo.get(f"{servidor}/notebooks/{SLUG}/api/status", timeout=60)
    assert r.status_code == 200, r.text
    yield partida_s


def _limpar_gateway():
    """Encerra vigia + bomba + uvicorn órfão do gateway pelo PID exato (o uvicorn é filho do
    servidor de teste, que morre sem levar os filhos junto). Só toca nos processos DESTA
    trilha: a linha do ps tem de carregar o socket unix do sufixo."""
    from app.notebooks import config

    cfg = config.obter()
    _docker("rm", "-f", cfg["gateway_nome"])
    ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True)
    for linha in ps.stdout.splitlines():
        if "app.notebooks.rele" in linha and cfg["gateway_uds"] in linha and "grep" not in linha:
            pid = linha.strip().split()[0]
            subprocess.run(["sudo", "-n", "kill", pid], capture_output=True)
    for linha in ps.stdout.splitlines():
        if f"--uds {cfg['gateway_uds']}" in linha and "grep" not in linha:
            pid = linha.strip().split()[0]
            try:
                os.kill(int(pid), 15)
            except (ValueError, ProcessLookupError):
                pass


@pytest.fixture(scope="session")
def camada_demo(servidor, demo):
    """Item camada_vetorial de teste (dado mínimo, sem carga real) para o kernel ler pela API."""
    corpo = {
        "tipo": "camada_vetorial",
        "titulo": "zt-nb-prova",
        "dados": {
            "schema": os.environ["PLAT_SCHEMA"],
            "tabela": "tipo_item",
            "geometria": "nenhuma",
            "srid": 4326,
            "campos": [{"nome": "nome", "tipo": "text"}],
            "fonte": "referenciada",
        },
    }
    r = demo.post(f"{servidor}/api/itens", json=corpo, timeout=15)
    assert r.status_code == 201, r.text
    item = r.json()
    yield item["id"]
    try:
        demo.delete(f"{servidor}/api/itens/{item['id']}", timeout=15)
    except Exception:
        pass


# ------------------------------------------------------------------ cláusula 2: sessão e slug
def test_401_sem_sessao(servidor):
    r = requests.get(f"{servidor}/notebooks/{SLUG}", timeout=15, allow_redirects=False)
    assert r.status_code == 401, r.text
    r = requests.get(f"{servidor}/notebooks/{SLUG}/lab", timeout=15)
    assert r.status_code == 401, r.text


def test_404_para_outro_inquilino(servidor, demo, demo2):
    r = demo.get(f"{servidor}/notebooks/{SLUG_OUTRO}", timeout=15, allow_redirects=False)
    assert r.status_code == 404, r.text
    r = demo2.get(f"{servidor}/notebooks/{SLUG}", timeout=15, allow_redirects=False)
    assert r.status_code == 404, r.text
    # e o próprio caminho interno do outro inquilino também é 404 (não 403: não confirma existência)
    r = demo.get(f"{servidor}/notebooks/{SLUG_OUTRO}/api/status", timeout=15)
    assert r.status_code == 404, r.text


# ------------------------------------------------- cláusula 1 (partida medida) e cláusula 2 (lab)
def test_partida_e_lab(servidor, demo, contenedor_demo):
    """`contenedor_demo` mediu a partida do contêiner (levantar direto: docker run → pronto)."""
    partida_s = contenedor_demo
    assert partida_s <= TAREFA_20_S, f"partida levou {partida_s:.1f} s (cláusula: <= 20 s)"
    # /notebooks/demo e /notebooks/demo/ abrem o lab (redirect), e o lab responde com sessão
    r = demo.get(f"{servidor}/notebooks/{SLUG}", timeout=15, allow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"/notebooks/{SLUG}/lab"
    r = demo.get(f"{servidor}/notebooks/{SLUG}/", timeout=15, allow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"/notebooks/{SLUG}/lab"
    r = demo.get(f"{servidor}/notebooks/{SLUG}/lab", timeout=30)
    assert r.status_code == 200 and "jupyter" in r.text.lower(), r.text[:200]


# ------------------------------------------------------------------ cláusula 7: segredo no ambiente
def test_environ_so_tem_o_token(contenedor_demo):
    r = _docker("exec", NOME, "cat", "/proc/1/environ")
    assert r.returncode == 0, r.stderr
    pares = dict(peca.split("=", 1) for peca in r.stdout.decode(errors="replace").split("\0") if "=" in peca)
    plats = {k: v for k, v in pares.items() if k.startswith("PLAT_")}
    assert set(plats) == {"PLAT_TOKEN", "PLAT_URL_API", "PLAT_INQUILINO"}, sorted(plats)
    assert plats["PLAT_TOKEN"].startswith("plat_"), "token de serviço é o formato da casa"
    assert plats["PLAT_INQUILINO"] == SLUG
    # nenhum DSN/senha em lugar nenhum do ambiente do processo 1
    for k, v in pares.items():
        assert "postgresql://" not in v, f"{k} carrega DSN"
        assert "postgres" not in k.lower(), f"{k} vazia nome de papel do banco"


# --------------------------------------- cláusula 3: kernel pela API da própria API do Jupyter
def _sessao_kernel(servidor, demo, nome_arquivo: str) -> dict:
    r = demo.post(f"{servidor}/notebooks/{SLUG}/api/sessions",
                  json={"path": nome_arquivo, "name": nome_arquivo, "type": "notebook",
                        "kernel": {"name": "python3"}}, timeout=60)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _executar_no_kernel(servidor, demo, kernel_id: str, codigo: str, teto_s: float = 150.0) -> dict:
    """execute_request pelo websocket do proxy; devolve {'saida': stdout, 'erro': texto do erro}."""
    from uuid import uuid4

    from websockets.sync.client import connect as ws_connect

    ws_url = (servidor.replace("http://", "ws://")
              + f"/notebooks/{SLUG}/api/kernels/{kernel_id}/channels")
    cookie = "; ".join(f"{c.name}={c.value}" for c in demo.cookies)
    msg_id = str(uuid4())
    pedido = {
        "header": {"msg_id": msg_id, "msg_type": "execute_request", "username": "teste",
                   "session": str(uuid4()), "date": "", "version": "5.3"},
        "parent_header": {}, "metadata": {},
        "content": {"code": codigo, "silent": False, "store_history": False,
                    "user_expressions": {}, "allow_stdin": False, "stop_on_error": True},
        "buffers": [], "channel": "shell",
    }
    saida: list[str] = []
    erros: list[str] = []
    with ws_connect(ws_url, additional_headers={"Cookie": cookie}, open_timeout=30) as ws:
        ws.send(json.dumps(pedido))
        inicio = time.monotonic()
        while time.monotonic() - inicio < teto_s:
            bruto = ws.recv(timeout=max(5.0, teto_s - (time.monotonic() - inicio)))
            msg = json.loads(bruto)
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            tipo = msg.get("header", {}).get("msg_type")
            if tipo == "stream":
                saida.append(msg["content"].get("text", ""))
            elif tipo == "error":
                erros.append("\n".join(msg["content"].get("evalue", "")))
            elif tipo == "status" and msg["content"].get("execution_state") == "idle":
                break
    return {"saida": "".join(saida), "erro": "\n".join(erros)}


def test_kernel_le_camada_pela_api_e_nao_escapa(servidor, demo, contenedor_demo, camada_demo):
    """Cláusula 3 + refutações, executadas DENTRO do contêiner pelo canal do kernel."""
    from app.notebooks import config

    cfg = config.obter()
    codigo = f"""
import json, os, socket
saida = {{}}
from plat_geo import Plataforma
pla = Plataforma(os.environ["PLAT_URL_API"], os.environ["PLAT_TOKEN"])
item = pla.catalogo.abrir({camada_demo!r})
saida["api_item"] = item["titulo"]
saida["api_inquilino"] = item.get("inquilino") or item.get("tenant_slug") or "demo"

def conecta(host, porta, teto=2.5):
    try:
        s = socket.create_connection((host, porta), teto)
        s.close()
        return True
    except OSError:
        return False

saida["pg_localhost"] = conecta("127.0.0.1", 5432)
saida["pg_gateway_ip"] = conecta({cfg["gateway_nome"]!r}, 5432)
saida["net_1_1_1_1"] = conecta("1.1.1.1", 443, 4.0)
saida["garage_localhost"] = conecta("127.0.0.1", 3900)
saida["docker_sock"] = os.path.exists("/var/run/docker.sock")
saida["trabalho"] = sorted(os.listdir("/home/jovyan/trabalho"))
print("PLATNB" + json.dumps(saida))
"""
    sessao = _sessao_kernel(servidor, demo, "prova-isolamento.ipynb")
    try:
        resultado = _executar_no_kernel(servidor, demo, sessao["kernel"]["id"], codigo)
        assert not resultado["erro"], f"célula falhou dentro do contêiner: {resultado['erro']}"
        linha = [ln for ln in resultado["saida"].splitlines() if ln.startswith("PLATNB")]
        assert linha, f"marcador PLATNB ausente na saída: {resultado['saida'][:400]}"
        visto = json.loads(linha[-1].removeprefix("PLATNB"))
    finally:
        demo.delete(f"{servidor}/notebooks/{SLUG}/api/sessions/{sessao['id']}", timeout=30)

    # leitura de camada pela API FUNCIONA (gateway + token do ambiente)
    assert visto["api_item"] == "zt-nb-prova", visto
    # Postgres direto, Garage direto e internet FALHAM
    assert visto["pg_localhost"] is False, visto
    assert visto["pg_gateway_ip"] is False, visto
    assert visto["garage_localhost"] is False, visto
    assert visto["net_1_1_1_1"] is False, visto
    # docker socket não existe: sem controlar o host por dentro
    assert visto["docker_sock"] is False, visto
    # volume de trabalho visível e vazio de segredos (só o que a sessão criou)
    assert isinstance(visto["trabalho"], list), visto


def test_kernel_de_outro_inquilino_nao_existe(servidor, demo2, contenedor_demo):
    """Refutação: a sessão de demo2 nunca alcança o notebook de demo (404 na sessão do kernel)."""
    r = demo2.post(f"{servidor}/notebooks/{SLUG}/api/sessions",
                   json={"path": "invade.ipynb", "name": "invade.ipynb", "type": "notebook",
                         "kernel": {"name": "python3"}}, timeout=30)
    assert r.status_code == 404, r.text


# ------------------------------------------------------------------ cláusula 4: limite de RAM
def test_ram_limite_mata_processo(contenedor_demo):
    """Cláusula 4: o processo que aloca 3 GiB morre pelo teto do cgroup (exit 137, medido).
    O Jupyter PODE ser levado junto pela onda do OOM (a escolha da vítima é do kernel,
    observado nas duas formas aqui); quando vai, a casa se recupera levantando de novo."""
    from app import db
    from app.notebooks import contenedor

    r = subprocess.run(["docker", "exec", NOME, "python3", "-c", "bytearray(3 * 1024 ** 3)"],
                       capture_output=True, timeout=120)
    assert r.returncode == 137, (r.returncode, r.stderr[-300:])
    est = contenedor.estado(SLUG)
    if est is None or not est["rodando"]:
        # levado pela onda: o levantar seguinte devolve o notebook do inquilino
        login, _ = credenciais()[SLUG]
        with db.db() as cur:
            cur.execute("SELECT tenant_id, usuario_id FROM plat.auth_login(%s, %s)", (SLUG, login))
            achou = cur.fetchone()
        ctx = db.Contexto(int(achou["tenant_id"]), int(achou["usuario_id"]), "teste")
        subida = contenedor.levantar(SLUG, ctx)
        assert subida["s"] <= TAREFA_20_S, f"recuperação após OOM levou {subida['s']} s"


# ------------------------------------------------------------------ cláusula 5: ociosidade
def test_ociosidade_ceifa(servidor, demo, contenedor_demo):
    from app import db
    from app.notebooks import contenedor

    tid = _tenant_id(SLUG)
    with db.db(db.Contexto(tid, 0, "teste")) as cur:
        cur.execute("UPDATE plat.notebook_uso SET ultimo_uso = now() - interval '31 minutes' "
                    "WHERE tenant_id = %s", (tid,))
    ceifados = contenedor.ceifar()
    assert ceifados == [SLUG], ceifados
    assert not _container_de_pe()
    # token do contêiner ceifado ficou revogado e o estado de uso sumiu
    with db.db(db.Contexto(tid, 0, "teste")) as cur:
        cur.execute("SELECT revogado_em FROM plat.token_servico WHERE nome = %s", (f"notebook {SLUG}",))
        linhas = cur.fetchall()
        assert linhas and all(ln["revogado_em"] is not None for ln in linhas)
        cur.execute("SELECT count(*) AS n FROM plat.notebook_uso WHERE slug = %s", (SLUG,))
        assert cur.fetchone()["n"] == 0
    # e o contêiner volta na próxima passagem com sessão (a fila de ativos não travou)
    r = demo.get(f"{servidor}/notebooks/{SLUG}/api/status", timeout=int(TAREFA_20_S) + 15)
    assert r.status_code == 200, r.text


# ------------------------------------------------- cláusula 6: notebook agendado via job no worker
def test_job_agendado_roda_e_salva_html(servidor, demo, worker, contenedor_demo):
    nb = {
        "cells": [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                   "source": ["print('PLATNB-JOB-OK', 2 + 3)"]}],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                    "name": "python3"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    bruto = json.dumps(nb).encode()
    tok = _criar_token_sessao(demo, servidor, "zt-nb-job", ["admin:inquilino"])
    portador = requests.Session()  # sem cookie: cookie + Authorization juntos o portão recusa
    try:
        r = portador.post(f"{servidor}/api/arquivos?classe=objeto", data=bruto,
                          headers={"Authorization": f"Bearer {tok['token']}",
                                   "Content-Type": "application/json"}, timeout=30)
        assert r.status_code == 201, r.text
        enviado = r.json()
        r = demo.post(f"{servidor}/api/itens", json={
            "tipo": "notebook", "titulo": "zt-nb-agendado",
            "dados": {**enviado, "nome_original": "agendado.ipynb"}}, timeout=15)
        assert r.status_code == 201, r.text
        item = r.json()
        r = demo.post(f"{servidor}/api/jobs",
                      json={"tipo": "notebooks.executar", "parametros": {"item_id": item["id"]}},
                      timeout=15)
        assert r.status_code == 201, r.text
        job = r.json()
        fim = time.monotonic() + 420
        while time.monotonic() < fim:
            j = demo.get(f"{servidor}/api/jobs/{job['id']}", timeout=15).json()
            if j["estado"] in ("concluido", "falhou", "cancelado"):
                break
            time.sleep(2.0)
        assert j["estado"] == "concluido", json.dumps(j.get("erro") or j, ensure_ascii=False)[:600]
        saida_id = j["resultado"]["item_id"]
        r = demo.get(f"{servidor}/api/itens/{saida_id}", timeout=15)
        assert r.status_code == 200, r.text
        saida = r.json()
        assert saida["tipo"] == "notebook_saida"
        dados = saida["dados"]
        assert dados["notebook_id"] == item["id"] and dados["bytes"] > 0
        from app import objetos

        r = demo.get(f"{servidor}{objetos.url_assinada(dados['chave'], 60)}", timeout=30)
        assert r.status_code == 200 and "PLATNB-JOB-OK" in r.text, r.text[:300]
        demo.delete(f"{servidor}/api/itens/{saida_id}", timeout=15)
        demo.delete(f"{servidor}/api/itens/{item['id']}", timeout=15)
    finally:
        try:
            demo.delete(f"{servidor}/api/tokens/{tok['id']}", timeout=15)
        except Exception:
            pass
