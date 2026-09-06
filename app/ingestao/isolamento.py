"""Execução ISOLADA de ferramenta de linha de comando sobre arquivo de terceiro (CAD, item L0-04-e).

O mecanismo é o MESMO do ADR 0015 (`app/raster/validacao.py`, item L1-01-b), aplicado aqui a um programa
externo em vez de um módulo Python: o adversário daquele item provou que o GDAL sai para a rede (VRT aninhado,
`/vsicurl`, driver HTTP) e lê caminho de fora do envio se o processo não for fechado. DXF e DWG têm a mesma
superfície: o DXF é texto que o GDAL interpreta, o DWG passa por um conversor em C de terceiro.

Três camadas, iguais às do ADR 0015 seção 3:

1. **seccomp** montado à mão em BPF clássico (`ctypes` sobre a libc, nenhuma dependência nova): `socket(AF_INET, …)`
   e `socket(AF_INET6, …)` devolvem `EAFNOSUPPORT`. Vai com `PR_SET_NO_NEW_PRIVS`, logo sobrevive ao `execve` e
   não exige privilégio. `AF_UNIX`/`AF_NETLINK` continuam livres (a libc precisa deles). O que o filho de fato
   conseguiu é MEDIDO em `/proc/self/status` pelo pai antes do exec? Não: quem mede é `isolamento_declarado()`,
   que roda um filho de prova e lê o `/proc` dele. Nada é prometido sem leitura.
2. **ambiente do GDAL** (`AMBIENTE_ISOLADO`): sem driver HTTP, sem PROJ na rede, sem varredura de diretório ao
   abrir, sem PAM (`.aux.xml` ao lado do arquivo do cliente), cache e threads limitados.
3. **conferência de caminho** no chamador: `/vsi` é recusado, e o argumento de arquivo tem de estar dentro do
   diretório do envio (`caminho_dentro`).

Mais: `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_NOFILE`, `RLIMIT_CORE=0`, `os.setsid()` + `killpg` no relógio de parede
(pega o neto que o GDAL lance), `PLAT_DSN`/`PLAT_SECRET` removidos do ambiente (o filho não fala com o banco).

Nota de convergência: quando o ramo do item L1-01-b entrar em `master`, `app/raster/validacao.py` passa a
importar `_preparar_filho`/`AMBIENTE_ISOLADO` daqui em vez de manter a sua cópia — está registrado no handoff
deste item como pendência de merge, não como código morto.
"""

from __future__ import annotations

import ctypes
import os
import platform
import resource
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

RLIMIT_AS_MB = 768
RLIMIT_CPU_S = 60
RLIMIT_NOFILE = 256
TIMEOUT_S = 90
GDAL_CACHEMAX_MB = 64
SAIDA_MAX = 32 * 1024 * 1024        # stdout do ogrinfo -json de um DXF grande; acima disso é truncado e recusado

AMBIENTE_ISOLADO = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_CACHEMAX": str(GDAL_CACHEMAX_MB),
    "GDAL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "GDAL_VRT_ENABLE_PYTHON": "NO",
    "GDAL_VRT_ENABLE_RAWRASTERBAND": "NO",
    "GDAL_HTTP_TIMEOUT": "1",
    "GDAL_HTTP_MAX_RETRY": "0",
    "GDAL_HTTP_CONNECTTIMEOUT": "1",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".nenhuma-extensao-permitida",
    "GDAL_SKIP": "HTTP",
    "PROJ_NETWORK": "OFF",
    "GDAL_PAM_ENABLED": "NO",
    "CPL_DEBUG": "OFF",
}

_PR_SET_NO_NEW_PRIVS, _PR_SET_SECCOMP, _SECCOMP_MODE_FILTER = 38, 22, 2
_SECCOMP_ALLOW, _SECCOMP_ERRNO_EAFNOSUPPORT = 0x7FFF0000, 0x00050000 | 97
_ARQUITETURAS = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198)}   # (AUDIT_ARCH, nº de `socket`)


class _FiltroBpf(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class _ProgramaBpf(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_FiltroBpf))]


def _montar_seccomp() -> tuple[object, int] | None:
    par = _ARQUITETURAS.get(platform.machine())
    if par is None:
        return None
    arch, nr_socket = par
    ld, jeq, ret = 0x20, 0x15, 0x06
    programa = [(ld, 0, 0, 4),
                (jeq, 0, 6, arch),
                (ld, 0, 0, 0),
                (jeq, 0, 4, nr_socket),
                (ld, 0, 0, 16),
                (jeq, 1, 0, 2),
                (jeq, 0, 1, 10),
                (ret, 0, 0, _SECCOMP_ERRNO_EAFNOSUPPORT),
                (ret, 0, 0, _SECCOMP_ALLOW)]
    vetor = (_FiltroBpf * len(programa))(*[_FiltroBpf(*linha) for linha in programa])
    prog = _ProgramaBpf(len(programa), vetor)
    return (vetor, prog), ctypes.cast(ctypes.byref(prog), ctypes.c_void_p).value


try:
    _LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
    _LIBC.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    _SECCOMP = _montar_seccomp()
except OSError:  # pragma: no cover — máquina sem glibc no caminho esperado
    _LIBC, _SECCOMP = None, None


def fechar_a_rede() -> bool:
    """Aplica o filtro no processo corrente. Nunca levanta: kernel sem seccomp não pode impedir a inspeção de
    rodar — nesse caso o relatório diz que a rede está fechada só por variável de ambiente."""
    if _LIBC is None or _SECCOMP is None:
        return False
    _vivos, endereco = _SECCOMP
    try:
        if _LIBC.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            return False
        return _LIBC.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, endereco, 0, 0) == 0
    except OSError:
        return False


def _preparar_filho() -> None:  # roda no filho, entre o fork e o exec (preexec_fn)
    as_bytes = RLIMIT_AS_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (RLIMIT_CPU_S, RLIMIT_CPU_S))
    resource.setrlimit(resource.RLIMIT_NOFILE, (RLIMIT_NOFILE, RLIMIT_NOFILE))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    fechar_a_rede()
    os.setsid()


@dataclass(frozen=True)
class Resultado:
    """Saída de um programa isolado. `morte` diz por que o filho não terminou sozinho (None = terminou)."""

    argv: list[str]
    codigo: int
    stdout: str
    stderr: str
    tempo_s: float
    ram_pico_kb: int
    morte: str | None
    truncado: bool

    @property
    def ok(self) -> bool:
        return self.codigo == 0 and self.morte is None and not self.truncado

    def ultima_linha_erro(self) -> str:
        linhas = [ln.strip() for ln in (self.stderr or "").splitlines() if ln.strip()]
        return linhas[-1][:300] if linhas else ""


class CaminhoRecusado(ValueError):
    """Caminho fora do diretório do envio ou com `/vsi`: nunca chega ao GDAL."""


def caminho_dentro(caminho: str | os.PathLike, raiz: str | os.PathLike) -> str:
    """Resolve por `realpath` (desfaz `..` e ligação simbólica) e exige que caia dentro de `raiz`. Mesma regra da
    conferência de fonte de VRT do ADR 0015 seção 3.1."""
    texto = os.fspath(caminho)
    if "/vsi" in texto:
        raise CaminhoRecusado(f"caminho com /vsi não é aceito: {os.path.basename(texto)}")
    real = os.path.realpath(texto)
    raiz_real = os.path.realpath(os.fspath(raiz))
    if not (real == raiz_real or real.startswith(raiz_real.rstrip("/") + "/")):
        raise CaminhoRecusado(f"caminho fora do diretório do envio: {os.path.basename(texto)}")
    return real


def executar(argv: list[str], *, raiz: str | os.PathLike, timeout_s: int = TIMEOUT_S,
             ambiente_extra: dict[str, str] | None = None) -> Resultado:
    """Roda `argv` com seccomp, rlimits, ambiente de GDAL fechado e relógio de parede. `raiz` é o diretório de
    trabalho: o programa nasce lá dentro. Nunca levanta por causa do arquivo — o defeito vira `Resultado`."""
    ambiente = {**os.environ, **AMBIENTE_ISOLADO, **(ambiente_extra or {})}
    ambiente.pop("PLAT_DSN", None)
    ambiente.pop("PLAT_DSN_WORKER", None)
    ambiente.pop("PLAT_SECRET", None)
    inicio = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=ambiente, preexec_fn=_preparar_filho, cwd=str(Path(raiz)))
    morte: dict[str, str | None] = {"causa": None}

    def matar():
        morte["causa"] = "tempo"
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass

    relogio = threading.Timer(timeout_s, matar)
    relogio.daemon = True
    relogio.start()
    truncado = False
    try:
        bruto = proc.stdout.read(SAIDA_MAX + 1)
        if len(bruto) > SAIDA_MAX:
            truncado = True
            matar()
            bruto = bruto[:SAIDA_MAX]
        erro = proc.stderr.read(1024 * 1024)
    finally:
        relogio.cancel()
    _pid, status, uso = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    if proc.returncode < 0 and morte["causa"] is None:
        sinal = -proc.returncode
        nome = signal.Signals(sinal).name if sinal in [s.value for s in signal.Signals] else str(sinal)
        morte["causa"] = f"sinal {nome}"
    return Resultado(
        argv=list(argv), codigo=proc.returncode,
        stdout=bruto.decode("utf-8", "replace"), stderr=erro.decode("utf-8", "replace"),
        tempo_s=round(time.monotonic() - inicio, 3), ram_pico_kb=int(uso.ru_maxrss),
        morte=morte["causa"], truncado=truncado,
    )


def isolamento_declarado(raiz: str | os.PathLike | None = None) -> dict:
    """Roda um filho de prova e LÊ o `/proc/self/status` dele: `Seccomp: 2` e `NoNewPrivs: 1` são medidos, não
    prometidos. Entra no relatório da inspeção como `isolamento`."""
    import sys

    raiz = raiz or Path(__file__).resolve().parents[2]
    codigo = ("import sys;"
              "d={};"
              "[d.__setitem__(l.split(':')[0].strip(), l.split(':')[1].strip())"
              " for l in open('/proc/self/status') if l.startswith(('Seccomp:','NoNewPrivs:'))];"
              "print(d.get('Seccomp'), d.get('NoNewPrivs'))")
    r = executar([sys.executable, "-c", codigo], raiz=raiz, timeout_s=30)
    partes = (r.stdout or "").split()
    seccomp = int(partes[0]) if partes and partes[0].isdigit() else None
    nnp = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else None
    return {
        "seccomp": seccomp, "no_new_privs": nnp,
        "rede": ("bloqueada no processo (seccomp: socket AF_INET/AF_INET6 devolve EAFNOSUPPORT)"
                 if seccomp == 2 else "bloqueada apenas por variável de ambiente do GDAL"),
        "rlimit_as_mb": RLIMIT_AS_MB, "rlimit_cpu_s": RLIMIT_CPU_S, "timeout_s": TIMEOUT_S,
    }
