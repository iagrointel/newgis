"""Servidor real (uvicorn, subprocesso próprio, sem nginx) para os testes do motor de render no servidor
(item L2-12-a-motor-render-servidor). O pipeline inteiro é: chromium do playwright -> HTTP de verdade ->
página /render/mapa -> /static/... — nada disso passa pelo transporte ASGI em processo do `TestClient`, que
o playwright não consegue alcançar. Por isso este helper sobe um `uvicorn app.main:app` de verdade numa porta
livre da máquina (nunca uma das já escutando: ADENDO 06/09 do BRIEF_WORKTREES.md) e devolve a URL base.

Reaproveitado por tests/unit/test_motor_render.py (o pool direto, sem sessão) e tests/api/test_render.py
(a rota HTTP `/api/render/mapa`, com login de verdade)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]


def porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def subir_servidor(porta: int | None = None, timeout_s: float = 20.0) -> tuple[subprocess.Popen, str]:
    porta = porta or porta_livre()
    base_url = f"http://127.0.0.1:{porta}"
    env = dict(os.environ)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(porta),
         "--no-access-log", "--log-level", "warning"],
        cwd=str(RAIZ),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # O PIPE de stdout tem ~64 KB e NINGUÉM o drena depois da partida: cada render gera dezenas de linhas
    # de access log (a página pede estáticos e faixas de tile), o buffer enche por volta do 21º render e o
    # uvicorn BLOQUEIA escrevendo log — o servidor inteiro para de responder e todo `goto` seguinte estoura
    # em 15 s (medido duas vezes: 21 amostras quente OK e depois só timeout, com a máquina a carga 20 e a
    # carga 2 — não era contenção, era o pipe; achado 08/09). --no-access-log corta o volume; a thread abaixo
    # drena o que sobrar (o diagnóstico de partida continua lendo o que a thread guarda).
    ultimas_saida: list[bytes] = []

    def _drenar() -> None:
        try:
            for linha in iter(proc.stdout.readline, b""):
                ultimas_saida.append(linha)
                del ultimas_saida[:-200]
        except Exception:  # noqa: BLE001 — dreno best-effort; o processo pode morrer durante o readline
            pass

    if proc.stdout is not None:
        threading.Thread(target=_drenar, daemon=True).start()
    inicio = time.time()
    ultimo_erro = None
    while time.time() - inicio < timeout_s:
        if proc.poll() is not None:
            saida = b"".join(ultimas_saida).decode(errors="replace")
            raise RuntimeError(f"uvicorn de teste morreu na partida (porta {porta}):\n{saida[-4000:]}")
        try:
            r = httpx.get(f"{base_url}/render/mapa", timeout=1.0)
            if r.status_code == 200:
                return proc, base_url
        except httpx.HTTPError as e:
            ultimo_erro = e
        time.sleep(0.2)
    derrubar_servidor(proc)
    raise TimeoutError(f"uvicorn de teste não respondeu em {timeout_s}s ({ultimo_erro})")


def derrubar_servidor(proc: subprocess.Popen) -> None:
    """Mata SÓ pelo PID (regra 3 do adendo 06/09 do BRIEF_WORKTREES.md) — nunca pkill/systemctl."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# --- memória do pool e teto do cgroup (cláusula "RSS do pool <= MemoryMax" do item L2-12-a) -------
# `laco/roda_teste.sh` roda o pytest dentro de um escopo do systemd com `MemoryMax=${PLAT_TESTE_RSS:-4G}`
# e `MemorySwapMax=0`. O teto do portão é, portanto, o `memory.max` do cgroup deste processo — não um
# número escolhido no teste. Se o pytest for chamado fora do lançador (sem cgroup com teto), não há teto
# a comparar e o teste diz isso em vez de inventar um.


def cgroup_do_processo() -> Path | None:
    """Caminho em /sys/fs/cgroup do cgroup (v2) deste processo, ou None se não houver."""
    try:
        linhas = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in linhas:
        partes = linha.split(":", 2)
        if len(partes) == 3 and partes[0] == "0":
            caminho = Path("/sys/fs/cgroup") / partes[2].lstrip("/")
            return caminho if caminho.exists() else None
    return None


def memoria_max_do_cgroup() -> int | None:
    """`memory.max` em bytes, ou None quando não há teto ("max") nem cgroup."""
    base = cgroup_do_processo()
    if base is None:
        return None
    try:
        bruto = (base / "memory.max").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return None if bruto == "max" else int(bruto)


def memoria_pico_do_cgroup() -> int | None:
    """`memory.peak` (pico de uso do cgroup inteiro) em bytes; None se o núcleo não expõe."""
    base = cgroup_do_processo()
    if base is None:
        return None
    for nome in ("memory.peak", "memory.current"):
        try:
            return int((base / nome).read_text(encoding="utf-8").strip())
        except OSError:
            continue
    return None


def _filhos_por_pai() -> dict[int, list[int]]:
    mapa: dict[int, list[int]] = {}
    for entrada in Path("/proc").iterdir():
        if not entrada.name.isdigit():
            continue
        try:
            stat = (entrada / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        # o nome do processo vem entre parênteses e pode conter espaços: corta depois do ')'
        resto = stat[stat.rfind(")") + 2:].split()
        if len(resto) < 2:
            continue
        mapa.setdefault(int(resto[1]), []).append(int(entrada.name))
    return mapa


def rss_dos_descendentes(pid: int | None = None) -> tuple[int, int]:
    """(RSS somado em bytes, nº de processos) de TODOS os descendentes deste processo — que é onde o pool
    vive: o playwright sobe o driver em node e o node sobe o chromium (navegador + zigoto + um processo por
    contexto/renderizador). Soma-se o RSS de cada um; páginas compartilhadas entram mais de uma vez, então
    o número é um LIMITE SUPERIOR do que o pool ocupa, que é o lado seguro para um teto."""
    pid = pid or os.getpid()
    filhos = _filhos_por_pai()
    pilha = list(filhos.get(pid, []))
    total = n = 0
    pagina = os.sysconf("SC_PAGE_SIZE")
    while pilha:
        atual = pilha.pop()
        pilha.extend(filhos.get(atual, []))
        try:
            campos = Path(f"/proc/{atual}/statm").read_text(encoding="utf-8").split()
        except OSError:
            continue
        total += int(campos[1]) * pagina
        n += 1
    return total, n
