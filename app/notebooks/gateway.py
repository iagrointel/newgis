"""Gateway da API para os contêineres de notebook (L2-16-b).

O firewall desta máquina derruba todo o tráfego contêiner → host (ufw INPUT policy DROP,
medido no item), e a máquina é partilhada com produção — abrir porta no firewall está fora
de questão. O caminho que ficou provado em prova de conceito:

1. um contêiner "vigia" (busybox sleep infinity) vive na rede docker interna e só serve de
   rede de nomes (netns);
2. um uvicorn da plataforma escuta num SOCKET UNIX no sistema de arquivos do host
   (`python -m uvicorn app.main:app --uds ...`) — nada escuta em TCP do host;
3. um processo bomba (`python -m app.notebooks.rele`, stdlib) é lançado com
   `sudo -n nsenter -t <pid do vigia> -n`: ele é processo DA MÁQUINA (vê o socket unix)
   morando na REDE do vigia, então escuta 0.0.0.0:8000 dentro da rede interna e entrega
   cada conexão ao socket unix;
4. os contêineres de notebook alcançam a API por `http://<nome do vigia>:8000` — o DNS
   embutido do docker resolve o nome na rede interna, sem contato com o host.

Tudo é recurso desta trilha: nome do vigia, rede e socket derivam do sufixo do schema
(app.notebooks.config). `parar()` encerra pelos PIDs exatos (nunca pkill -f).
"""

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from app.notebooks import config

# REENTRANTE: parar() é chamado de dentro de levantar() no caminho de falha; com Lock comum
# o mesmo thread ficaria preso esperando a própria trava (bug achado pela suíte: o pedido do
# notebook nunca respondia e o uvicorn ficava órfão).
_TRAVA = threading.RLock()
_estado: dict | None = None  # {"uvicorn": Popen, "rele": Popen, "cfg": dict, "url": str}


def _rodar(cmd: list[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


def _garantir_rede(cfg: dict) -> None:
    r = _docker("network", "inspect", cfg["rede"])
    if r.returncode != 0:
        r = _docker("network", "create", "--internal", "--driver", "bridge", cfg["rede"])
        if r.returncode != 0:
            raise RuntimeError(f"rede docker {cfg['rede']} não criou: {r.stderr.strip()}")


def _garantir_vigia(cfg: dict) -> int:
    """Contêiner vigia rodando na rede interna; devolve o PID dele (host)."""
    nome = cfg["gateway_nome"]
    r = _docker("inspect", "-f", "{{.State.Running}}", nome)
    if r.returncode == 0 and r.stdout.strip() == "true":
        pass
    else:
        if r.returncode == 0:  # existe mas parado
            _docker("rm", "-f", nome)
        r = _docker(
            "run", "-d", "--name", nome, "--network", cfg["rede"],
            "--label", "plat.notebook-gateway=1", "busybox:latest", "sleep", "infinity",
        )
        if r.returncode != 0:
            raise RuntimeError(f"vigia {nome} não subiu: {r.stderr.strip()}")
    r = _docker("inspect", "-f", "{{.State.Pid}}", nome)
    pid = int(r.stdout.strip())
    if pid <= 0:
        raise RuntimeError(f"vigia {nome} sem pid: {r.stdout.strip()}")
    return pid


def _ip_vigia(cfg: dict) -> str:
    r = _docker(
        "inspect", "-f",
        f"{{{{(index .NetworkSettings.Networks \"{cfg['rede']}\" ).IPAddress}}}}",
        cfg["gateway_nome"],
    )
    ip = r.stdout.strip()
    if not ip:
        raise RuntimeError(f"vigia {cfg['gateway_nome']} sem IP em {cfg['rede']}")
    return ip


def _saude_ok(url: str) -> bool:
    """200 ou 503 = o aplicativo respondeu (503 é semântica da casa G4-19: Garage fora)."""
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status in (200, 503)
    except urllib.error.HTTPError as e:
        return e.code in (200, 503)
    except Exception:
        return False


def _esperar_saude(cfg: dict, limite_s: float) -> None:
    # vigia + bomba PRIMEIRO: o IP do vigia só existe depois que ele existe (na partida fria
    # não há vigia ainda — consultar o IP antes era erro garantido no primeiro levantar)
    _tentar_rele(cfg)
    url = f"http://{_ip_vigia(cfg)}:{cfg['gateway_porta']}/saude"
    fim = time.monotonic() + limite_s
    ultimo = ""
    reinicios = 0
    while time.monotonic() < fim:
        if _saude_ok(url):
            return
        st = _estado
        if st is not None and st["rele"] is not None and st["rele"].poll() is not None:
            saida = (st["rele"].stdout.read() or b"").decode(errors="replace")[-300:]
            ultimo = f"rele morreu: {saida.strip()}"
            reinicios += 1
            if reinicios > 3:
                # um rele antigo e quebrado segurando a porta dentro da netns derruba tudo:
                # mata pelo pid EXATO que o ss reporta na própria rede de nomes (nunca pkill -f)
                _matar_rele_porta(cfg)
            _tentar_rele(cfg)
        time.sleep(1.0)
    raise RuntimeError(f"gateway do notebook não ficou saudável em {limite_s:.0f} s ({ultimo})")


def _tentar_rele(cfg: dict) -> str:
    st = _estado
    if st is not None and st.get("rele") is not None and st["rele"].poll() is None:
        return "rele ja rodando"
    pid_vigia = _garantir_vigia(cfg)
    st["rele"] = _rodar(
        ["sudo", "-n", "nsenter", "-t", str(pid_vigia), "-n",
         "python3", "-m", "app.notebooks.rele", cfg["gateway_uds"], str(cfg["gateway_porta"])],
        cwd=_raiz(),
    )
    return f"rele pid {st['rele'].pid}"


def _matar_rele_porta(cfg: dict) -> None:
    """Se sobrou um processo escutando a porta do gateway dentro da netns (de um rele que
    morreu mal), encerra pelo pid exato reportado pelo `ss` na própria rede de nomes."""
    nome = cfg["gateway_nome"]
    r = _docker("inspect", "-f", "{{.State.Pid}}", nome)
    if r.returncode != 0:
        return
    try:
        pid_vigia = int(r.stdout.strip())
    except ValueError:
        return
    try:
        ss = subprocess.run(
            ["sudo", "-n", "nsenter", "-t", str(pid_vigia), "-n",
             "ss", "-ltnp", f"sport = :{cfg['gateway_porta']}"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return
    for linha in ss.stdout.splitlines():
        if "pid=" not in linha:
            continue
        for pedaco in linha.split():
            if pedaco.startswith("pid="):
                alvo = pedaco.removeprefix("pid=").split(",")[0]
                subprocess.run(["sudo", "-n", "kill", alvo], capture_output=True, timeout=15)


def _raiz() -> str:
    """Raiz do repositório (onde mora o pacote `app`) para cwd dos subprocessos."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _uds_nosso(caminho: str) -> bool:
    """Já há um uvicorn NOSSO servindo neste socket unix? (A API e o worker podem chegar aqui
    em processos diferentes; quem chega segundo REUSA o uvicorn do primeiro em vez de roubar
    o socket.) Conectar não basta: um órfão de uma partida anterior responde como qualquer
    processo — a suíte achou um uvicorn velho segurando o arquivo e o pedido do notebook foi
    atendido por código velho. Pergunta /saude: a app da casa responde 200 (ou 503 com o
    Garage fora, G4-19); qualquer outra coisa devolve False e o levantar cria o próprio
    uvicorn — o --uds remove o arquivo alheio ao começar, então rebind é seguro."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect(caminho)
        s.sendall(b"GET /saude HTTP/1.0\r\nHost: localhost\r\n\r\n")
        pedacos = []
        while sum(len(p) for p in pedacos) <= 65536:
            pedaco = s.recv(4096)
            if not pedaco:
                break
            pedacos.append(pedaco)
    except OSError:
        return False
    finally:
        s.close()
    resposta = b"".join(pedacos)
    primeira = resposta.split(b"\r\n", 1)[0]
    return primeira.endswith(b" 200") or primeira.endswith(b" 503")


def levantar() -> str:
    """Garante rede + vigia + uvicorn no socket unix + bomba na netns; devolve a URL da API
    vista de dentro da rede docker. Idempotente (trava por processo)."""
    global _estado
    cfg = config.obter()
    if cfg["url_api"]:
        return cfg["url_api"]
    with _TRAVA:
        uv, rel = (_estado or {}).get("uvicorn"), (_estado or {}).get("rele")
        if _estado is not None and (uv is None or uv.poll() is None) \
                and rel is not None and rel.poll() is None:
            # uvicorn próprio vivo (ou alheio: este processo só trouxe a bomba) e bomba viva
            return _estado["url"]
        if _estado is not None:
            for p in (_estado.get("uvicorn"), _estado.get("rele")):
                if p is not None and p.poll() is None:
                    p.terminate()
        _garantir_rede(cfg)
        os.makedirs(os.path.dirname(cfg["gateway_uds"]), exist_ok=True)
        uds = cfg["gateway_uds"]
        dono_uds = not _uds_nosso(uds)
        uv = None
        if dono_uds:
            uv = _rodar(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--uds", uds, "--log-level", "warning"],
                cwd=_raiz(),
            )
        _estado = {
            "uvicorn": uv,
            "dono_uds": dono_uds,
            "rele": None,
            "cfg": cfg,
            "url": f"http://{cfg['gateway_nome']}:{cfg['gateway_porta']}",
        }
        try:
            _esperar_saude(cfg, 60.0)
        except Exception:
            parar()
            raise
        return _estado["url"]


def parar() -> None:
    """Encerra uvicorn + bomba pelos PIDs exatos e remove o vigia. Não levanta exceção."""
    global _estado
    with _TRAVA:
        st, _estado = _estado, None
        if st is None:
            return
        for p in (st.get("rele"), st.get("uvicorn")):
            if p is not None and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=10)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
        cfg = st["cfg"]
        _matar_rele_porta(cfg)
        try:
            _docker("rm", "-f", cfg["gateway_nome"])
        except Exception:
            pass
        if st.get("dono_uds"):
            try:
                if os.path.exists(cfg["gateway_uds"]):
                    os.unlink(cfg["gateway_uds"])
            except OSError:
                pass
