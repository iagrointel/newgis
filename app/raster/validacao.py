"""Validação e isolamento da ENTRADA raster (item L1-01-b; ADR 0015). Todo arquivo raster enviado passa por aqui
ANTES de qualquer conversão (COG, pirâmide, tile). Duas metades no mesmo módulo:

* o PAI (`validar()`), que roda no processo do worker: confere existência, extensão e ASSINATURA de formato (os
  primeiros bytes, nunca o nome), e então lança o filho com `resource.setrlimit` (RLIMIT_AS = RLIMIT_AS_MB,
  RLIMIT_CPU = RLIMIT_CPU_S, RLIMIT_NOFILE, RLIMIT_CORE = 0), FILTRO SECCOMP que faz `socket(AF_INET/AF_INET6)`
  devolver EAFNOSUPPORT (a rede fecha no processo, não só por variável do GDAL), relógio de parede TIMEOUT_S
  (SIGKILL), ambiente GDAL sem leitura de diretório (`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`), sem driver HTTP
  (`GDAL_SKIP`), sem PROJ na rede, sem VRT com fonte fora do diretório e sem `VRTRawRasterBand`, cache de 64 MB e
  1 thread. Mede tempo e pico de RSS do filho por `os.wait4`. O que quer que aconteça ao filho (estouro de
  memória, tempo, sinal, saída sem JSON) vira um relatório `recusado` com a causa em português: o pai NUNCA
  importa rasterio para olhar o arquivo do cliente.
* o FILHO (`python -m app.raster.validacao <json>`), que abre o arquivo com rasterio e produz o relatório:
  formato, dimensões, bandas, tipo, ColorInterp, CRS (EPSG resolvível, WKT2 sem EPSG, ou pendência), NoData
  (declarado, informado, ou pendência), data de aquisição (metadado, informada, ou pendência), extensão em
  EPSG:4326 (aviso se fora do Brasil, PENDÊNCIA se a coordenada não existe no planeta), tamanho descompactado
  ESTIMADO pelo cabeçalho contra a cota (recusa antes de ler um pixel: BigTIFF esparso de 100 GB virtual cai
  aqui), zip conferido pelo diretório central antes de extrair (nº de entradas, razão de compressão, soma
  declarada contra a cota E contra o teto de volume ligado ao tamanho do envio, nomes de caminho), VRT conferido
  RECURSIVAMENTE (toda fonte, resolvida por `os.path.realpath`, tem de cair dentro do diretório do envio),
  leitura de uma janela pequena com os arquivos abertos UM DE CADA VEZ (JP2 truncado cai aqui).
  `validate()` de `plataforma/pipeline/ingest.py` foi a base das checagens de CRS/tipo/NoData/extensão (copiado,
  aquele arquivo não é editado).

Nenhum defeito do arquivo sai como traceback: toda exceção do GDAL (inclusive `CPLE_*`, que não é `RasterioError`)
vira problema em português, sem caminho absoluto do servidor. NaN e ±Infinity viram texto declarado antes de o
relatório sair, porque o `jsonb` do Postgres recusa o documento inteiro se houver um.

Relatório (dict serializável, gravado no resultado do job pelo `raster.validar`):
  estado: 'aceito' | 'pendente' (falta resposta do usuário: crs/nodata/data_aquisicao/escala) | 'recusado'
  problemas: [str]   avisos: [str]   pendencias: [{campo, mensagem}]   info: {…}   respostas: {…}
  info.isolamento: {seccomp, no_new_privs, rede} lido no /proc do próprio filho
  subprocesso: {rlimit_as_mb, rlimit_cpu_s, timeout_s, codigo_saida, tempo_s, ram_pico_kb, morte}
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import platform
import re
import resource
import signal
import subprocess
import sys
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

VERSAO = 1

# --- limites do subprocesso (ADR 0015 seção 2; refletidos em tests/medidas/L1-01-b.json)
RLIMIT_AS_MB = 768          # ≤ 1 GB por ordem do item; rasterio+numpy+GDAL abrem em 67 MB de RSS medido
RLIMIT_CPU_S = 60           # segundos de CPU do filho (SIGXCPU → SIGKILL pelo kernel)
RLIMIT_NOFILE = 256         # um zip legítimo de centenas de rasters não pode morrer de "Too many open files"
TIMEOUT_S = 90              # relógio de parede: o pai mata com SIGKILL
GDAL_CACHEMAX_MB = 64

# --- limites do conteúdo
COTA_DESCOMPACTADO_PADRAO = 4 * 1024 * 1024 * 1024   # 4 GiB quando o chamador não passa a cota do inquilino
BANDAS_MAX = 512
LADO_MAX = 200_000                                    # pixels por lado (500 GB em uint8 para além disso)
ZIP_ENTRADAS_MAX = 1000
ZIP_RAZAO_MAX = 50                                    # a cláusula do portão: 50× declarado = recusa (>=)
ZIP_NOME_MAX = 255
ZIP_VOLUME_FATOR = 8                                  # escrita máxima na extração = 8× o tamanho do ENVIO…
ZIP_VOLUME_PISO = 8 * 1024 * 1024                     # …com piso de 8 MiB, para o envio minúsculo legítimo
VRT_XML_MAX = 16 * 1024 * 1024                        # o XML do VRT é lido INTEIRO até este teto
VRT_PROFUNDIDADE_MAX = 5                              # VRT que aponta para VRT: no máximo 5 níveis
JANELA_LEITURA = 256                                  # janela lida para provar que os dados abrem
BRASIL_BBOX = (-76.0, -34.5, -27.0, 6.0)              # (lonmin, latmin, lonmax, latmax), com folga
TIPOS_SEM_CONVERSAO = ("complex64", "complex128", "complex_int16", "int64", "uint64")
PERFIS = ("dados", "visual")
CAMPOS_RESPOSTA = ("crs", "nodata", "data_aquisicao", "escala")

# --- formatos: extensão → (nome, assinaturas admitidas nos primeiros bytes)
ASSINATURAS: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".tif": ("GeoTIFF", (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")),
    ".tiff": ("GeoTIFF", (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")),
    ".jp2": ("JPEG 2000", (b"\x00\x00\x00\x0cjP  \r\n\x87\n", b"\xff\x4f\xff\x51")),
    ".vrt": ("VRT (GDAL)", (b"<VRTDataset",)),
    ".zip": ("zip com GeoTIFF/JPEG 2000", (b"PK\x03\x04",)),
}
EXTENSOES_RASTER_EM_ZIP = (".tif", ".tiff", ".jp2")
_NOMES_MAGICOS = {b"\x89PNG": "PNG", b"\xff\xd8\xff": "JPEG", b"GIF8": "GIF", b"%PDF": "PDF", b"<?xm": "XML",
                  b"PK\x03\x04": "zip", b"\x00\x00\x00\x0c": "JPEG 2000", b"II*\x00": "TIFF", b"MM\x00*": "TIFF"}

AMBIENTE_FILHO = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_CACHEMAX": str(GDAL_CACHEMAX_MB),
    "GDAL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "GDAL_VRT_ENABLE_PYTHON": "NO",
    "GDAL_VRT_ENABLE_RAWRASTERBAND": "NO",
    "GDAL_HTTP_TIMEOUT": "1",
    "GDAL_HTTP_MAX_RETRY": "0",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".nenhuma-extensao-permitida",
    "GDAL_HTTP_CONNECTTIMEOUT": "1",
    "GDAL_SKIP": "HTTP",          # tira o driver que abre http:// direto (o /vsicurl cai no seccomp)
    "PROJ_NETWORK": "OFF",        # o PROJ não busca grade de transformação na rede
    "GDAL_PAM_ENABLED": "NO",
    "CPL_DEBUG": "OFF",
}


class EntradaInvalida(ValueError):
    """Argumento do chamador errado (perfil, resposta): erro de programação, não do arquivo."""


# =============================================================================================== PAI
def nome_pelo_conteudo(cabecalho: bytes) -> str:
    for assinatura, nome in _NOMES_MAGICOS.items():
        if cabecalho.startswith(assinatura):
            return nome
    if cabecalho.lstrip()[:11] == b"<VRTDataset":
        return "VRT"
    return "desconhecido"


def conferir_assinatura(caminho: Path) -> tuple[str, str | None]:
    """(formato, problema). A extensão diz o que o cliente DECLAROU; os bytes dizem o que o arquivo É."""
    ext = caminho.suffix.lower()
    if ext not in ASSINATURAS:
        return "", (f"extensão {ext or '(sem extensão)'} não é um formato raster aceito; aceitos: "
                    + ", ".join(sorted(ASSINATURAS)))
    nome, assinaturas = ASSINATURAS[ext]
    with caminho.open("rb") as f:
        cabecalho = f.read(64)
    if ext == ".vrt":
        ok = cabecalho.lstrip().startswith(b"<VRTDataset") or (
            cabecalho.lstrip().startswith(b"<?xml") and b"VRTDataset" in caminho.read_bytes()[:4096])
    else:
        ok = any(cabecalho.startswith(a) for a in assinaturas)
    if not ok:
        return nome, (f"o conteúdo não corresponde à extensão {ext}: os primeiros bytes são de "
                      f"{nome_pelo_conteudo(cabecalho)}, não de {nome}")
    return nome, None


# --- bloqueio de rede POR PROCESSO (ADR 0015 seção 6). Variável de ambiente do GDAL não fecha a rede: a lista
# CPL_VSIL_CURL_ALLOWED_EXTENSIONS aceita qualquer extensão que o próprio atacante escreva na URL e o `http://`
# direto nem passa por ela. Aqui o filho recebe um filtro seccomp que faz `socket(AF_INET|AF_INET6, …)` devolver
# EAFNOSUPPORT: nenhum soquete de rede chega a ser criado, e o curl do GDAL falha antes de resolver o nome. O
# filtro é BPF clássico montado à mão (nenhuma dependência nova) e sobrevive ao execve porque vem com
# PR_SET_NO_NEW_PRIVS. AF_UNIX e AF_NETLINK continuam permitidos (a libc precisa deles).
_PR_SET_NO_NEW_PRIVS, _PR_SET_SECCOMP, _SECCOMP_MODE_FILTER = 38, 22, 2
_SECCOMP_ALLOW, _SECCOMP_ERRNO_EAFNOSUPPORT = 0x7FFF0000, 0x00050000 | 97
_ARQUITETURAS = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198)}   # (AUDIT_ARCH, nº de `socket`)


class _FiltroBpf(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class _ProgramaBpf(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_FiltroBpf))]


def _montar_seccomp() -> tuple[object, int] | None:
    """Devolve (ponteiro do sock_fprog, endereço) ou None quando a máquina não é coberta. Montado no PAI, antes do
    fork: o preexec_fn só chama prctl()."""
    par = _ARQUITETURAS.get(platform.machine())
    if par is None:
        return None
    arch, nr_socket = par
    ld, jeq, ret = 0x20, 0x15, 0x06     # BPF_LD|BPF_W|BPF_ABS, BPF_JMP|BPF_JEQ|BPF_K, BPF_RET|BPF_K
    programa = [(ld, 0, 0, 4),                      # 0: carrega seccomp_data.arch
                (jeq, 0, 6, arch),                  # 1: outra arquitetura → permite (nada a filtrar aqui)
                (ld, 0, 0, 0),                      # 2: carrega seccomp_data.nr
                (jeq, 0, 4, nr_socket),             # 3: não é socket() → permite
                (ld, 0, 0, 16),                     # 4: carrega os 32 bits baixos de args[0] (domínio)
                (jeq, 1, 0, 2),                     # 5: AF_INET  → erro
                (jeq, 0, 1, 10),                    # 6: AF_INET6 → erro; qualquer outro → permite
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


def _fechar_a_rede() -> bool:
    """Aplica o filtro seccomp no processo corrente. Devolve se conseguiu; nunca levanta (kernel sem seccomp não
    pode impedir a validação de rodar — nesse caso o relatório diz que a rede está fechada só por variável)."""
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
    _fechar_a_rede()
    os.setsid()


def _isolamento_medido() -> dict:
    """Lido no /proc do PRÓPRIO filho, não declarado: é o que entra no relatório."""
    estado = {"seccomp": None, "no_new_privs": None}
    try:
        for linha in Path("/proc/self/status").read_text().splitlines():
            if linha.startswith("Seccomp:"):
                estado["seccomp"] = int(linha.split()[1])
            elif linha.startswith("NoNewPrivs:"):
                estado["no_new_privs"] = int(linha.split()[1])
    except (OSError, ValueError, IndexError):  # pragma: no cover — /proc sempre existe no alvo
        pass
    estado["rede"] = ("bloqueada no processo (seccomp: socket AF_INET/AF_INET6 devolve EAFNOSUPPORT)"
                      if estado["seccomp"] == 2 else "bloqueada apenas por variável de ambiente do GDAL")
    return estado


def _json_seguro(valor):
    """NaN e ±Infinity são float legítimos (NoData de float32 costuma ser NaN) e NÃO são JSON: `jsonb` do Postgres
    recusa o documento inteiro. Trocamos por texto declarado ('NaN', 'Infinity', '-Infinity') antes de sair do
    relatório — nunca por None, que confundiria 'sem NoData' com 'NoData é NaN'."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return "NaN" if math.isnan(valor) else ("Infinity" if valor > 0 else "-Infinity")
    if isinstance(valor, dict):
        return {k: _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    return valor


_RE_CAMINHO_ABSOLUTO = re.compile(r"(?:/[\w.\-+@]+){2,}")


def _sem_caminho(texto: str) -> str:
    """Tira caminho absoluto do servidor de mensagem vinda do GDAL/SO: o usuário vê o nome do arquivo dele."""
    return _RE_CAMINHO_ABSOLUTO.sub(lambda m: os.path.basename(m.group(0)), texto)


def _detalhe(erro: BaseException) -> str:
    return _sem_caminho(str(erro).splitlines()[0] if str(erro).strip() else type(erro).__name__)[:200]


def _normalizar_respostas(respostas: dict | None) -> dict:
    respostas = dict(respostas or {})
    extras = set(respostas) - set(CAMPOS_RESPOSTA)
    if extras:
        raise EntradaInvalida(f"resposta desconhecida: {sorted(extras)}; admitidas {CAMPOS_RESPOSTA}")
    return {k: v for k, v in respostas.items() if v is not None}


def validar(caminho: str | os.PathLike, *, perfil: str = "dados", respostas: dict | None = None,
            cota_bytes: int = COTA_DESCOMPACTADO_PADRAO, timeout_s: int = TIMEOUT_S,
            dir_trabalho: str | os.PathLike | None = None, _prova: str | None = None) -> dict:
    """Ponto de entrada do worker. Nunca levanta por causa do ARQUIVO (todo defeito dele vira `recusado` com
    mensagem); levanta `EntradaInvalida` só por argumento errado do chamador."""
    if perfil not in PERFIS:
        raise EntradaInvalida(f"perfil {perfil!r} desconhecido; admitidos {PERFIS}")
    respostas = _normalizar_respostas(respostas)
    caminho = Path(caminho)
    relatorio = _vazio(perfil, respostas)
    texto = str(caminho)
    if texto.startswith("/vsi") or "/vsi" in texto:
        return _recusar(relatorio, "caminho virtual do GDAL (/vsi…) não é aceito: só arquivo local já enviado")
    if not caminho.is_file() or caminho.is_symlink():
        return _recusar(relatorio, f"arquivo não encontrado ou não é arquivo comum: {caminho.name}")
    formato, problema = conferir_assinatura(caminho)
    relatorio["info"]["formato"] = formato
    relatorio["info"]["tamanho_bytes"] = caminho.stat().st_size
    if problema:
        return _recusar(relatorio, problema)
    dir_trabalho = Path(dir_trabalho) if dir_trabalho else caminho.parent
    argumentos = {"caminho": str(caminho.resolve()), "perfil": perfil, "respostas": respostas,
                  "cota_bytes": int(cota_bytes), "dir_trabalho": str(dir_trabalho), "prova": _prova}
    saida = _executar_filho(argumentos, timeout_s)
    relatorio["subprocesso"] = saida["subprocesso"]
    if saida["relatorio"] is None:
        return _recusar(relatorio, saida["causa"])
    filho = saida["relatorio"]
    for chave in ("problemas", "avisos", "pendencias"):
        relatorio[chave].extend(filho.get(chave, []))
    relatorio["info"].update(filho.get("info", {}))
    return _fechar(relatorio)



def _executar_filho(argumentos: dict, timeout_s: int) -> dict:
    ambiente = {**os.environ, **AMBIENTE_FILHO}
    ambiente.pop("PLAT_DSN", None)  # o filho nunca fala com o banco
    ambiente.pop("PLAT_SECRET", None)
    argv = [sys.executable, "-m", "app.raster.validacao", json.dumps(argumentos, ensure_ascii=False)]
    inicio = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ambiente,
                            preexec_fn=_preparar_filho, cwd=str(Path(__file__).resolve().parents[2]))
    morte = {"causa": None}

    def matar():
        morte["causa"] = "timeout"
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
    try:
        stdout = proc.stdout.read()      # EOF quando o filho sai (ou é morto); relatório cabe no pipe (< 64 KB)
        stderr = proc.stderr.read()
    finally:
        relogio.cancel()
    _pid, status, uso = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)  # evita o ResourceWarning do Popen sem wait()
    tempo_s = round(time.monotonic() - inicio, 3)
    sub = {"rlimit_as_mb": RLIMIT_AS_MB, "rlimit_cpu_s": RLIMIT_CPU_S, "timeout_s": timeout_s,
           "codigo_saida": proc.returncode, "tempo_s": tempo_s, "ram_pico_kb": int(uso.ru_maxrss), "morte": None}
    if morte["causa"] == "timeout":
        sub["morte"] = "timeout"
        return {"relatorio": None, "subprocesso": sub,
                "causa": f"a validação passou de {timeout_s} s e foi interrompida (arquivo malformado ou grande "
                         f"demais para abrir); nada foi importado"}
    if proc.returncode < 0:
        sinal = -proc.returncode
        nome = signal.Signals(sinal).name if sinal in signal.Signals.__members__.values() else str(sinal)
        sub["morte"] = f"sinal {nome}"
        causa = (f"a validação foi morta por {nome}" +
                 (" (limite de CPU do subprocesso)" if sinal == signal.SIGXCPU else "") + "; nada foi importado")
        return {"relatorio": None, "subprocesso": sub, "causa": causa}
    try:
        relatorio = json.loads(stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        relatorio = None
    if relatorio is None or not isinstance(relatorio, dict):
        ultima = [ln for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
        detalhe = (ultima[-1] if ultima else "sem detalhe")[:300]
        if "MemoryError" in detalhe or "Cannot allocate" in detalhe or "std::bad_alloc" in detalhe:
            sub["morte"] = "memoria"
            causa = (f"a validação excedeu a memória do subprocesso ({RLIMIT_AS_MB} MB): o arquivo exige mais do que "
                     f"o cabeçalho permitiria ler; nada foi importado")
        else:
            sub["morte"] = f"saida {proc.returncode}"
            causa = f"a validação terminou sem relatório (código {proc.returncode}): {detalhe}; nada foi importado"
        return {"relatorio": None, "subprocesso": sub, "causa": causa}
    if relatorio.get("morte") == "memoria":
        sub["morte"] = "memoria"
        return {"relatorio": None, "subprocesso": sub,
                "causa": f"a validação excedeu a memória do subprocesso ({RLIMIT_AS_MB} MB) em "
                         f"'{relatorio.get('etapa', '?')}': {relatorio.get('detalhe', '')[:200]}; nada foi importado"}
    return {"relatorio": relatorio, "subprocesso": sub, "causa": None}


def _vazio(perfil: str, respostas: dict) -> dict:
    return {"versao": VERSAO, "estado": "recusado", "perfil": perfil, "problemas": [], "avisos": [], "pendencias": [],
            "info": {}, "respostas": respostas, "subprocesso": None}


def _recusar(relatorio: dict, problema: str) -> dict:
    relatorio["problemas"].append(problema)
    return _fechar(relatorio)


def _fechar(relatorio: dict) -> dict:
    if relatorio["problemas"]:
        relatorio["estado"] = "recusado"
    elif relatorio["pendencias"]:
        relatorio["estado"] = "pendente"
    else:
        relatorio["estado"] = "aceito"
    # ÚNICA saída do relatório: aqui NaN/±Infinity viram texto declarado, para o `jsonb` do job aceitar (achado 5)
    return _json_seguro(relatorio)


def resumo(relatorio: dict) -> str:
    """Uma linha em português para log/tela: estado + primeira causa."""
    estado = relatorio["estado"]
    if estado == "recusado":
        return f"recusado: {relatorio['problemas'][0]}"
    if estado == "pendente":
        return "pendente: " + "; ".join(p["mensagem"] for p in relatorio["pendencias"])
    info = relatorio["info"]
    return (f"aceito: {info.get('formato')} {info.get('largura')}×{info.get('altura')}, {info.get('bandas')} banda(s) "
            f"{info.get('tipo')}, CRS {info.get('crs', {}).get('rotulo')}")


# =============================================================================================== FILHO
def _filho(argumentos: dict) -> dict:
    """Roda sob RLIMIT_AS/CPU/timeout. Devolve o relatório parcial (problemas/avisos/pendencias/info)."""
    for chave, valor in AMBIENTE_FILHO.items():
        os.environ.setdefault(chave, valor)
    saida: dict = {"problemas": [], "avisos": [], "pendencias": [], "info": {"isolamento": _isolamento_medido()}}
    prova = argumentos.get("prova")
    if prova == "memoria":  # usado pelo teste: prova que o RLIMIT_AS derruba o filho e o pai sobrevive
        bloco = bytearray(2 * 1024 * 1024 * 1024)
        bloco[::4096] = b"\x01" * len(bloco[::4096])
        return saida
    if prova == "tempo":
        while True:
            time.sleep(1)
    caminho = Path(argumentos["caminho"])
    if "/vsi" in str(caminho):
        saida["problemas"].append("caminho virtual do GDAL (/vsi…) não é aceito")
        return saida
    cota = int(argumentos["cota_bytes"])
    dir_trabalho = Path(argumentos["dir_trabalho"])
    perfil = argumentos["perfil"]
    respostas = argumentos.get("respostas") or {}
    ext = caminho.suffix.lower()
    fontes: list[Path]
    if ext == ".zip":
        fontes = _abrir_zip(caminho, cota, dir_trabalho, saida)
        if saida["problemas"]:
            return saida
    elif ext == ".vrt":
        _conferir_vrt(caminho, saida)
        if saida["problemas"]:
            return saida
        fontes = [caminho]
    else:
        fontes = [caminho]
    _inspecionar(fontes, cota, perfil, respostas, saida)
    return saida


def _recusa_generica(saida: dict, erro: BaseException) -> dict:
    saida.setdefault("problemas", []).append(
        f"a validação não conseguiu interpretar o arquivo ({type(erro).__name__.split('.')[-1]}): "
        f"{_detalhe(erro)}; nada foi importado")
    return saida


def _abrir_zip(caminho: Path, cota: int, dir_trabalho: Path, saida: dict) -> list[Path]:
    """Só o diretório central é lido antes de decidir; extrai APENAS os rasters, depois de aprovado."""
    try:
        zf = zipfile.ZipFile(caminho)
        infos = zf.infolist()
    except (zipfile.BadZipFile, OSError) as e:
        saida["problemas"].append(f"zip inválido: {e}")
        return []
    if len(infos) > ZIP_ENTRADAS_MAX:
        saida["problemas"].append(f"zip com {len(infos)} entradas; o máximo é {ZIP_ENTRADAS_MAX}")
        return []
    total_decl = sum(i.file_size for i in infos)
    total_comp = max(1, sum(i.compress_size for i in infos))
    razao = total_decl / total_comp
    if total_decl > cota:
        saida["problemas"].append(f"zip declara {_gb(total_decl)} descompactados, acima da cota de {_gb(cota)}; "
                                  "nada foi descompactado")
        return []
    if razao >= ZIP_RAZAO_MAX:
        saida["problemas"].append(f"zip declara razão de compressão de {razao:.0f}× (limite {ZIP_RAZAO_MAX}×): "
                                  "suspeita de zip-bomba; nada foi descompactado")
        return []
    # teto de VOLUME escrito, ligado ao tamanho do ENVIO (achado 7): a razão de 50× e a cota do inquilino
    # deixavam um envio de 1,4 MB escrever 60 MB no diretório de trabalho do worker.
    enviado = caminho.stat().st_size
    teto = min(cota, ZIP_VOLUME_FATOR * enviado + ZIP_VOLUME_PISO)
    if total_decl > teto:
        saida["problemas"].append(
            f"zip de {_gb(enviado)} declara {_gb(total_decl)} descompactados, acima do teto de {_gb(teto)} para "
            f"um envio desse tamanho ({ZIP_VOLUME_FATOR}× o enviado mais {_gb(ZIP_VOLUME_PISO)}); nada foi "
            "descompactado")
        return []
    rasters = []
    for i in infos:
        nome = i.filename
        if (len(nome.encode("utf-8", "replace")) > ZIP_NOME_MAX or nome.startswith("/") or ".." in nome.split("/")
                or "\\" in nome or any(ord(c) < 32 for c in nome)):
            saida["problemas"].append(f"zip com nome de caminho inválido: {nome[:80]!r}")
            return []
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            saida["problemas"].append(f"zip com link simbólico: {nome[:80]!r}")
            return []
        if nome.lower().endswith(".zip"):
            saida["problemas"].append(f"zip aninhado não é aceito: {nome[:80]!r}")
            return []
        if nome.lower().endswith(EXTENSOES_RASTER_EM_ZIP) and not i.is_dir():
            rasters.append(i)
    if not rasters:
        saida["problemas"].append("o zip não contém nenhum GeoTIFF (.tif/.tiff) nem JPEG 2000 (.jp2)")
        return []
    destino = dir_trabalho / "zip_extraido"
    destino.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i in rasters:
        alvo = destino / Path(i.filename).name
        with zf.open(i) as origem, alvo.open("wb") as f:
            restante = i.file_size
            while True:
                bloco = origem.read(min(1 << 20, max(1, restante)))
                if not bloco:
                    break
                f.write(bloco)
                restante -= len(bloco)
                if restante < 0:  # o cabeçalho mentiu para menos: para antes de encher o disco
                    saida["problemas"].append(f"a entrada {i.filename!r} do zip é maior do que o declarado")
                    return []
        formato, problema = conferir_assinatura(alvo)
        if problema:
            saida["problemas"].append(f"dentro do zip, {i.filename!r}: {problema}")
            return []
        caminhos.append(alvo)
    saida["info"]["zip_entradas"] = [i.filename for i in rasters]
    return caminhos


_RE_FONTE_VRT = re.compile(r"<SourceFilename([^>]*)>(.*?)</SourceFilename>", re.S)
_RE_RELATIVO = re.compile(r'relativeToVRT\s*=\s*["\']?(\d)')


def _conferir_vrt(caminho: Path, saida: dict, raiz: str | None = None, profundidade: int = 0,
                  vistos: set[str] | None = None) -> None:
    """Confere o VRT INTEIRO e, RECURSIVAMENTE, todo VRT que ele referencie (achados 1-3 do adversário). Regra:
    a fonte, depois de resolvida com `os.path.realpath` (o que desfaz ligação simbólica e `..`), tem de cair
    dentro do diretório do envio. O XML é lido inteiro até VRT_XML_MAX — o corte de 1 MiB deixava passar a
    segunda banda escondida atrás de um comentário grande."""
    raiz = raiz if raiz is not None else os.path.realpath(caminho.parent)
    vistos = vistos if vistos is not None else set()
    real = os.path.realpath(caminho)
    if real in vistos:
        saida["problemas"].append(f"VRT com referência circular: {caminho.name!r} aponta de volta para si mesmo")
        return
    vistos.add(real)
    if profundidade > VRT_PROFUNDIDADE_MAX:
        saida["problemas"].append(f"VRT aninhado além de {VRT_PROFUNDIDADE_MAX} níveis: cadeia de fontes longa "
                                  "demais para conferir")
        return
    tamanho = caminho.stat().st_size
    if tamanho > VRT_XML_MAX:
        saida["problemas"].append(f"o XML do VRT {caminho.name!r} tem {_gb(tamanho)}; o máximo aceito é "
                                  f"{_gb(VRT_XML_MAX)}")
        return
    texto = caminho.read_text("utf-8", "replace")
    if "VRTRawRasterBand" in texto:
        saida["problemas"].append("VRT com VRTRawRasterBand (leitura crua de arquivo arbitrário) não é aceito")
        return
    if "PixelFunction" in texto or "VRTDerivedRasterBand" in texto:
        saida["problemas"].append("VRT com banda derivada (função de pixel) não é aceito")
        return
    achados = _RE_FONTE_VRT.findall(texto)
    if not achados:
        saida["problemas"].append("VRT sem SourceFilename: não referencia nenhum raster")
        return
    for atributos, bruto in achados:
        f = bruto.strip()
        marca = _RE_RELATIVO.search(atributos or "")
        relativo = marca.group(1) == "1" if marca else False
        if f.startswith("/vsi") or "://" in f or "\\" in f or not f:
            saida["problemas"].append(f"VRT com fonte fora do diretório do envio ou remota: {f[:120]!r}")
            return
        base = caminho.parent
        alvo = base / f if (relativo or not os.path.isabs(f)) else Path(f)
        destino = os.path.realpath(alvo)
        if not (destino == raiz or destino.startswith(raiz + os.sep)):
            saida["problemas"].append(f"VRT com fonte fora do diretório do envio ou remota: {f[:120]!r}")
            return
        if not os.path.isfile(destino):
            saida["problemas"].append(f"VRT referencia fonte inexistente: {f[:120]!r}")
            return
        if destino.lower().endswith(".vrt"):
            _conferir_vrt(Path(destino), saida, raiz, profundidade + 1, vistos)
            if saida["problemas"]:
                return


def _gb(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    return f"{n / 1024:.0f} kB"


def _inspecionar(fontes: list[Path], cota: int, perfil: str, respostas: dict, saida: dict) -> None:
    """Abre UM arquivo de cada vez (achado 9: o zip legítimo de 200 rasters estourava o RLIMIT_NOFILE porque
    todos ficavam abertos ao mesmo tempo). A 1ª passagem lê só cabeçalho; a 2ª reabre para a janela de prova."""
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import MaskFlags
    from rasterio.errors import RasterioError
    from rasterio.windows import Window

    info = saida["info"]
    problemas, avisos, pendencias = saida["problemas"], saida["avisos"], saida["pendencias"]

    class _Cabecalho:
        pass

    cabecalhos: list[_Cabecalho] = []
    primeiro = None
    for f in fontes:
        try:
            with rasterio.open(str(f)) as d:
                c = _Cabecalho()
                c.width, c.height, c.count, c.dtypes = d.width, d.height, d.count, list(d.dtypes)
                c.colorinterp = [ci.name for ci in d.colorinterp]
                cabecalhos.append(c)
                if primeiro is None:
                    primeiro = c
                    c.driver, c.nodata, c.crs = d.driver, d.nodata, d.crs
                    c.res, c.bounds, c.tags = tuple(d.res), tuple(d.bounds), dict(d.tags())
                    c.alpha = MaskFlags.alpha in d.mask_flag_enums[0]
        except Exception as e:  # noqa: BLE001 — qualquer defeito do ARQUIVO vira recusa em português
            problemas.append(f"o GDAL não abriu {f.name}: {_detalhe(e)}")
            return
    try:
        ds = primeiro
        # --- cabeçalho: dimensões, bandas, tipo — TUDO antes de ler um pixel
        tipos = []
        bandas = 0
        for d in cabecalhos:
            tipos.extend(d.dtypes)
            bandas += d.count
        info.update({"driver": ds.driver, "largura": ds.width, "altura": ds.height, "bandas": bandas,
                     "tipos": sorted(set(tipos)), "tipo": tipos[0] if tipos else None,
                     "arquivos": [f.name for f in fontes]})
        if bandas < 1:
            problemas.append("o arquivo não tem nenhuma banda")
            return
        if bandas > BANDAS_MAX:
            problemas.append(f"{bandas} bandas; o máximo aceito é {BANDAS_MAX}")
            return
        for d in cabecalhos[1:]:
            if (d.width, d.height) != (ds.width, ds.height):
                problemas.append(f"arquivos do zip com dimensões diferentes: {ds.width}×{ds.height} e "
                                 f"{d.width}×{d.height}")
                return
        if len(set(tipos)) > 1:
            problemas.append(f"bandas com tipos de dado diferentes: {', '.join(sorted(set(tipos)))}; "
                             "todas as bandas têm de ter o mesmo tipo")
            return
        itemsize = np.dtype(tipos[0]).itemsize
        estimado = ds.width * ds.height * bandas * itemsize
        info["tamanho_descompactado_estimado_bytes"] = estimado
        if estimado > cota:
            problemas.append(f"tamanho descompactado estimado de {_gb(estimado)} ({ds.width}×{ds.height}×{bandas} "
                             f"bandas {tipos[0]}) acima da cota de {_gb(cota)}; nada foi lido")
            return
        if ds.width > LADO_MAX or ds.height > LADO_MAX:
            problemas.append(f"dimensões {ds.width}×{ds.height} acima do máximo de {LADO_MAX} pixels por lado")
            return
        # --- tipo de dado: aceito aqui, mas a conversão (COG/tile) não serve complex/int64 — fica DECLARADO
        info["tipo_convertivel"] = tipos[0] not in TIPOS_SEM_CONVERSAO
        # --- ColorInterp e NoData
        interp = [nome for d in cabecalhos for nome in d.colorinterp]
        info["colorinterp"] = interp
        tem_alpha = "alpha" in interp or ds.alpha
        nodata = ds.nodata
        if nodata is not None:
            info["nodata"] = {"valor": nodata, "origem": "arquivo"}
        elif "nodata" in respostas:
            info["nodata"] = {"valor": float(respostas["nodata"]), "origem": "informado"}
        elif tem_alpha:
            info["nodata"] = {"valor": None, "origem": "mascara"}
            avisos.append("NoData não declarado; a banda alfa/máscara do arquivo vai marcar as bordas")
        else:
            info["nodata"] = None
            pendencias.append({"campo": "nodata",
                               "mensagem": "NoData não declarado no arquivo: informe o valor que marca 'sem dado' "
                                           "(ou 'nenhum' para não marcar); sem isso as bordas ficam pretas"})
        # --- CRS
        crs = ds.crs
        if crs is None and "crs" in respostas:
            try:
                crs = CRS.from_user_input(respostas["crs"])
            except (RasterioError, ValueError) as e:
                problemas.append(f"o CRS informado não foi reconhecido: {respostas['crs']!r} ({str(e)[:120]})")
                return
            origem = "informado"
        else:
            origem = "arquivo"
        if crs is None:
            info["crs"] = None
            pendencias.append({"campo": "crs",
                               "mensagem": "o arquivo não tem sistema de referência (CRS): informe o código EPSG "
                                           "(ex.: 4674 SIRGAS 2000, 31983 SIRGAS 2000 / UTM 23S); a plataforma "
                                           "nunca assume um"})
        else:
            epsg = crs.to_epsg()
            wkt2 = crs.to_wkt(version="WKT2_2019") if hasattr(crs, "to_wkt") else crs.to_wkt()
            if epsg is not None:
                info["crs"] = {"epsg": epsg, "rotulo": f"EPSG:{epsg}", "origem": origem, "wkt2": wkt2}
            else:
                info["crs"] = {"epsg": None, "rotulo": "WKT2 sem EPSG", "origem": origem, "wkt2": wkt2}
                avisos.append("CRS sem código EPSG resolvível; gravado o WKT2 completo do arquivo "
                              f"('{(crs.to_dict().get('proj') or wkt2[:40])}…') — confira a projeção antes de publicar")
        # --- extensão
        info["resolucao"] = [float(ds.res[0]), float(ds.res[1])]
        info["bbox_nativa"] = [float(x) for x in ds.bounds]
        if crs is not None:
            try:
                from rasterio.warp import transform_bounds
                b = transform_bounds(crs, "EPSG:4326", *ds.bounds, densify_pts=21)
                info["bbox4326"] = [round(float(x), 6) for x in b]
                impossivel = (not all(math.isfinite(x) for x in b) or abs(b[0]) > 180 or abs(b[2]) > 180
                              or abs(b[1]) > 90 or abs(b[3]) > 90)
                dentro = (BRASIL_BBOX[0] <= b[0] and b[2] <= BRASIL_BBOX[2] and BRASIL_BBOX[1] <= b[1]
                          and b[3] <= BRASIL_BBOX[3])
                if impossivel:
                    # não existe latitude fora de [-90, 90] nem longitude fora de [-180, 180]: o CRS está errado,
                    # e a plataforma PERGUNTA em vez de aceitar com um aviso (achado 6)
                    pendencias.append({"campo": "crs",
                                       "mensagem": "a extensão do arquivo no CRS "
                                                   f"{info['crs']['rotulo']} ({origem}) cai fora do planeta "
                                                   f"({info['bbox4326']} em graus): confirme o CRS correto — "
                                                   "coordenada em metros costuma ser UTM (ex.: 31983 SIRGAS 2000 "
                                                   "/ UTM 23S), não um sistema em graus"})
                elif not dentro:
                    avisos.append(f"extensão fora do território esperado (Brasil): {info['bbox4326']} em EPSG:4326 "
                                  "— confira o CRS")
            except Exception as e:  # noqa: BLE001 — CPLE_* do GDAL não é RasterioError (achado 8)
                avisos.append(f"não foi possível projetar a extensão para EPSG:4326: {_detalhe(e)}")
        # --- data de aquisição
        data, origem_data = _data_aquisicao(ds.tags, respostas)
        if data:
            info["data_aquisicao"] = {"valor": data, "origem": origem_data}
        else:
            info["data_aquisicao"] = None
            pendencias.append({"campo": "data_aquisicao",
                               "mensagem": "data de aquisição ausente nos metadados: informe a data da imagem "
                                           "(AAAA-MM-DD)"})
        # --- perfil
        if perfil == "visual":
            if bandas < 3:
                problemas.append(f"perfil visual exige pelo menos 3 bandas (RGB); o arquivo tem {bandas}")
                return
            if tipos[0] != "uint8":
                if "escala" in respostas:
                    esc = respostas["escala"]
                    if not (isinstance(esc, (list, tuple)) and len(esc) == 2 and esc[0] < esc[1]):
                        problemas.append(f"escala informada inválida: {esc!r} (esperado [mínimo, máximo])")
                        return
                    info["escala"] = {"minimo": float(esc[0]), "maximo": float(esc[1]), "origem": "informado"}
                else:
                    pendencias.append({"campo": "escala",
                                       "mensagem": f"perfil visual com dados de {tipos[0]} ({itemsize * 8} bits): "
                                                   "informe [mínimo, máximo] para reescalar a 8 bits"})
        elif bandas == 1 and perfil == "dados":
            info["banda_unica"] = True
        # --- prova de leitura: uma janela pequena de cada arquivo, reaberto um a um (JP2 truncado cai aqui)
        for c, f in zip(cabecalhos, fontes, strict=True):
            janela = Window(0, 0, min(JANELA_LEITURA, c.width), min(JANELA_LEITURA, c.height))
            try:
                with rasterio.open(str(f)) as d:
                    d.read(1, window=janela)
            except Exception as e:  # noqa: BLE001 — inclusive CPLE_* do GDAL, que não é RasterioError
                problemas.append(f"os dados de {f.name} não puderam ser lidos (arquivo truncado ou corrompido): "
                                 f"{_detalhe(e)}")
                return
    except EntradaInvalida:
        raise
    except Exception as e:  # noqa: BLE001 — nenhum defeito do arquivo pode sair como traceback em inglês
        problemas.append(f"o arquivo não pôde ser interpretado pelo GDAL ({type(e).__name__.split('.')[-1]}): "
                         f"{_detalhe(e)}; nada foi importado")


_RE_DATA = re.compile(r"(\d{4})[-:/](\d{2})[-:/](\d{2})")
_CHAVES_DATA = ("ACQUISITIONDATETIME", "ACQUISITION_DATE", "TIFFTAG_DATETIME", "DATETIME", "DATE_ACQUIRED",
                "SENSING_TIME", "PRODUCT_START_TIME", "DATE")


def _data_aquisicao(tags: dict, respostas: dict) -> tuple[str | None, str | None]:
    for chave in _CHAVES_DATA:
        for k, v in tags.items():
            if k.upper() == chave:
                m = _RE_DATA.search(str(v))
                if m:
                    try:
                        return date(int(m[1]), int(m[2]), int(m[3])).isoformat(), f"metadado {k}"
                    except ValueError:
                        pass
    if "data_aquisicao" in respostas:
        try:
            return datetime.strptime(str(respostas["data_aquisicao"])[:10], "%Y-%m-%d").date().isoformat(), "informado"
        except ValueError:
            return None, None
    return None, None


def _principal(argv: list[str]) -> int:
    argumentos = json.loads(argv[1])
    try:
        saida = _filho(argumentos)
    except MemoryError:
        saida = {"morte": "memoria", "etapa": "validacao", "detalhe": "MemoryError"}
    except Exception as erro:  # noqa: BLE001 — o filho NUNCA devolve traceback: devolve relatório em português
        saida = _recusa_generica({"problemas": [], "avisos": [], "pendencias": [], "info": {}}, erro)
    sys.stdout.write(json.dumps(_json_seguro(saida), ensure_ascii=False, default=str, allow_nan=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(_principal(sys.argv))
