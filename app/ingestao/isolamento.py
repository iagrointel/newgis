"""Isolamento do GDAL/OGR contra o arquivo de terceiro (ADR 0015, reaproveitado aqui para o vetor: L0-04).

O arquivo que chega na ingestão é do cliente e o GDAL abre o que o cabeçalho mandar. O `ogrinfo`/`ogr2ogr`
chamado por `app.ingestao.inspecionar` e `app.ingestao.carregar` herdava só o `RLIMIT_DATA` do job
(`ContextoJob.subprocesso`, ADR 0003) e rodava com o ambiente do worker inteiro: sem `GDAL_SKIP=HTTP` nem
`PROJ_NETWORK=OFF`, um GeoJSON/GPKG com referência de CRS remota ou um KML com `NetworkLink` sai para a rede
como qualquer outro processo do host, e nada impedia o GDAL de varrer o diretório do envio procurando
arquivo auxiliar (`.aux.xml`, sidecar). Duas camadas, a mesma receita do raster (ADR 0015 §3):

* `AMBIENTE_GDAL_ISOLADO` — variáveis de ambiente que fecham o driver HTTP do GDAL, o PROJ de rede, a
  varredura de diretório e o PAM; aplicadas em TODA chamada de `ogrinfo`/`ogr2ogr` deste módulo, inclusive a
  que grava no PostgreSQL (essa precisa de `AF_INET` para o próprio banco — não pode levar o bloqueio de
  soquete do item 2).
* `preexec_bloquear_rede()` — o mesmo filtro seccomp do ADR 0015 (`socket(AF_INET|AF_INET6)` devolve
  `EAFNOSUPPORT`), usado SÓ nas chamadas de leitura (`ogrinfo`, `ogr2ogr -f GeoJSON /vsistdout/`) que nunca
  precisam de rede. `ingestao.carregar` (grava no Postgres via `AF_INET`) usa só o ambiente, não o seccomp.

Cinto e fecho: a variável de ambiente sozinha não fecha a rede (um driver que ignore `GDAL_SKIP` continuaria
livre), e o seccomp sozinho não impede o GDAL de tentar e falhar tarde. As duas camadas juntas.
"""

from __future__ import annotations

import ctypes
import os
import platform
import resource

# ---------------------------------------------------------------- ambiente (cinto)
AMBIENTE_GDAL_ISOLADO: dict[str, str] = {
    "GDAL_SKIP": "HTTP",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".nenhuma-extensao-permitida",
    "GDAL_HTTP_TIMEOUT": "1",
    "GDAL_HTTP_CONNECTTIMEOUT": "1",
    "GDAL_HTTP_MAX_RETRY": "0",
    "PROJ_NETWORK": "OFF",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_PAM_ENABLED": "NO",
    "GDAL_VRT_ENABLE_PYTHON": "NO",
    "GDAL_VRT_ENABLE_RAWRASTERBAND": "NO",
    "OGR_SKIP": "OAPIF,WFS,GeoRSS,PLSCENES,ODBC",
    "CPL_CURL_ENABLE_VSIMEM": "NO",
    "GDAL_CACHEMAX": "64",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
}


def ambiente_isolado(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Ambiente do processo atual (herda PATH etc.) menos os segredos, mais o isolamento do GDAL. `PLAT_DSN`/
    `PLAT_SECRET` continuam fora daqui: quem precisa deles (ogr2ogr → Postgres) passa a DSN como argumento de
    linha de comando (`PG:...`), nunca por variável de ambiente do processo que abre o arquivo do cliente."""
    base = {k: v for k, v in os.environ.items() if not k.startswith("PLAT_")}
    base.update(AMBIENTE_GDAL_ISOLADO)
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------- seccomp (fecho, só quando não há Postgres)
_PR_SET_NO_NEW_PRIVS, _PR_SET_SECCOMP, _SECCOMP_MODE_FILTER = 38, 22, 2
_SECCOMP_ALLOW, _SECCOMP_ERRNO_EAFNOSUPPORT = 0x7FFF0000, 0x00050000 | 97
_ARQUITETURAS = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198)}  # (AUDIT_ARCH, nº de `socket`)


class _FiltroBpf(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class _ProgramaBpf(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_FiltroBpf))]


def _montar_seccomp() -> tuple[object, int] | None:
    par = _ARQUITETURAS.get(platform.machine())
    if par is None:
        return None
    arch, nr_socket = par
    ld, jeq, ret = 0x20, 0x15, 0x06  # BPF_LD|BPF_W|BPF_ABS, BPF_JMP|BPF_JEQ|BPF_K, BPF_RET|BPF_K
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


def preexec_bloquear_rede() -> None:
    """`preexec_fn` do `subprocess.Popen`: aplica o filtro seccomp no filho, entre o fork e o exec. Nunca
    levanta — se o kernel recusar o filtro, o subprocesso continua rodando, só sem a camada extra (o cinto do
    ambiente ainda vale). Usar SÓ quando o subprocesso não precisa de nenhuma rede (nunca no `ogr2ogr` que
    grava no Postgres)."""
    if _LIBC is not None and _SECCOMP is not None:
        _vivos, endereco = _SECCOMP
        try:
            if _LIBC.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0:
                _LIBC.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, endereco, 0, 0)
        except OSError:  # pragma: no cover
            pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    except (OSError, ValueError):  # pragma: no cover
        pass
