"""GET /saude/profunda (item L7-34-saude-profunda; ADR REST-server-status/E11-ha-patch): sonda por componente
(banco, fila, martin, titiler, garage, nginx, certificado, disco, ram) com estado `ok|degradado|erro` e tempo
individual. Cada sonda roda num pool de threads PRÓPRIO com tempo limite: uma sonda pendurada (Garage atrás de
`iptables`, por exemplo) vira `erro` em `TEMPO_LIMITE_SONDA_S` e NUNCA trava o endpoint inteiro.

Duas versões da MESMA leitura: anônima (para balanceador/CDN, sem sessão) só tem nome+estado+tempo de cada
componente; autenticada por sessão de superadmin acrescenta o alvo sondado (host:porta, nunca a query nem
credencial da URL) e o motivo do erro. NENHUMA das duas versões inclui DSN, token do Garage/admin ou o nome de
um inquilino — essas três coisas nunca atravessam esta rota, sob nenhuma condição.

Componente sem infraestrutura real nesta topologia (réplica de banco, backup, licença, último HIT de CDN)
declara `ausente` com o motivo — não é mock nem dado fixo, é a ausência honesta do subsistema."""

from __future__ import annotations

import logging
import socket
import ssl
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeoutError
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app import db
from app.auth.sessao import opcional as auth_opcional
from app.migracoes import chave_migracao
from app.saude import agora_iso, sondar_servico
from app.settings import settings

router = APIRouter()
log = logging.getLogger("plat.saude_profunda")

TEMPO_LIMITE_SONDA_S = 2.0
LIMITE_DISCO_DEGRADADO_PCT = 10.0
LIMITE_DISCO_ERRO_PCT = 3.0
LIMITE_RAM_DEGRADADO_PCT = 10.0
LIMITE_RAM_ERRO_PCT = 3.0
LIMITE_CERTIFICADO_DEGRADADO_DIAS = 21
LIMITE_CERTIFICADO_ERRO_DIAS = 7
VOLUMES_DISCO = ("/", "/mnt/pgdata")

# tabela declarada (cláusula do portão de pronto): "ausente" nunca degrada o geral; "erro" no banco é sempre
# erro geral; qualquer outro "erro" ou qualquer "degradado" (inclusive do próprio banco por migração
# pendente) vira "degradado" geral. Ordem de severidade usada para escolher o pior estado de um grupo.
_SEVERIDADE = {"ok": 0, "ausente": 0, "degradado": 1, "erro": 2}

# um pool com folga para as sondas rodarem em paralelo sem fila entre si; uma sonda que estoura o tempo
# limite continua rodando na sua thread (Future não cancela código já em execução) mas o endpoint NÃO a
# aguarda — ela só ocupa uma vaga do pool até o SO derrubar a ligação pendurada.
_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="saude-profunda-sonda")


def pior_estado(estados: list[str]) -> str:
    return max(estados, key=lambda e: _SEVERIDADE.get(e, 2)) if estados else "ok"


def _alvo_seguro(url: str | None) -> str | None:
    """scheme://host:porta da URL, sem path/query/credencial — o único pedaço de uma URL interna que não é
    segredo. Nunca chame isto com uma DSN de banco nem com uma URL que carregue token na query."""
    if not url:
        return None
    p = urlsplit(url)
    if not p.hostname:
        return None
    porta = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{p.hostname}{porta}"


def _sondar(fn: Callable[[], dict]) -> dict:
    """Roda fn() no pool próprio com TEMPO_LIMITE_SONDA_S; nunca deixa uma sonda travar o chamador."""
    inicio = time.perf_counter()
    fut: Future = _executor.submit(fn)
    try:
        resultado = fut.result(timeout=TEMPO_LIMITE_SONDA_S)
    except FuturoTimeoutError:
        resultado = {"estado": "erro", "motivo": "tempo_limite"}
    except Exception as e:  # noqa: BLE001 — qualquer sonda vira "erro", nunca derruba o endpoint
        log.warning("saude/profunda: sonda em erro: %s", type(e).__name__)
        resultado = {"estado": "erro", "motivo": type(e).__name__}
    resultado["tempo_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
    return resultado


# ---------------------------------------------------------------- sondas de banco e fila (uma conexão só)


def _banco_e_fila() -> dict:
    """UMA conexão para banco+migrações+fila: o pool da trilha nasce com PLAT_POOL_MAX=2 (laco/trilha_ambiente.sh);
    abrir uma conexão por sub-sonda esgotaria o pool sozinho. Réplica: esta topologia não tem réplica de
    Postgres configurada -> `ausente` (não é erro; é a ausência honesta do subsistema)."""
    with db.db() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
        conexao = "ok"

        cur.execute("SELECT nome FROM plat.versao_migracao")
        aplicadas = sorted((r["nome"] for r in cur.fetchall()), key=chave_migracao)
        pendentes = [n for n in db.migracoes_em_disco() if n not in aplicadas]
        migracoes = "ok" if not pendentes else "degradado"

        cur.execute("SELECT * FROM plat.fila_estado()")
        f = cur.fetchone()
        cur.execute("SELECT plat.fila_job_mais_antigo_pendente_s() AS s")
        idade_s = cur.fetchone()["s"]

    banco_estado = pior_estado([conexao, migracoes])
    workers_vivos = f["workers_vivos"]
    fila_estado = "ok" if workers_vivos >= 1 else "degradado"
    return {
        "banco": {
            "estado": banco_estado,
            "conexao": conexao,
            "migracoes": migracoes,
            "migracoes_pendentes": len(pendentes),
            "replica": "ausente",
        },
        "fila": {
            "estado": fila_estado,
            "workers_vivos": workers_vivos,
            "pendentes": f["pendentes"],
            "rodando": f["rodando"],
            "job_pendente_mais_antigo_s": round(float(idade_s), 1) if idade_s is not None else None,
        },
    }


# ---------------------------------------------------------------- sondas de serviço HTTP


def _servico_simples(url: str | None) -> dict:
    return {"estado": sondar_servico(url), "alvo": _alvo_seguro(url)}


def _garage() -> dict:
    """S3 (sondar_servico, já usado por /saude) + Admin API v2 GetClusterHealth quando configurada. O token
    de admin nunca entra na resposta — só o resultado da chamada."""
    s3 = sondar_servico(settings.PLAT_GARAGE_URL)
    saida = {"estado": s3, "alvo": _alvo_seguro(settings.PLAT_GARAGE_URL), "s3": s3}
    if not settings.PLAT_GARAGE_ADMIN_URL or not settings.PLAT_GARAGE_ADMIN_TOKEN:
        saida["nos"] = "ausente"
        return saida
    import requests

    try:
        r = requests.get(
            f"{settings.PLAT_GARAGE_ADMIN_URL.rstrip('/')}/v2/GetClusterHealth",
            headers={"Authorization": f"Bearer {settings.PLAT_GARAGE_ADMIN_TOKEN}"},
            timeout=TEMPO_LIMITE_SONDA_S,
        )
        if r.status_code != 200:
            saida["nos"] = "erro"
        else:
            j = r.json()
            nos_ok = j.get("storageNodesUp", 0) >= j.get("storageNodes", 1)
            saida["nos"] = "ok" if nos_ok else "degradado"
            saida["nos_conectados"] = j.get("connectedNodes")
            saida["nos_total"] = j.get("knownNodes")
    except Exception as e:  # noqa: BLE001
        saida["nos"] = "erro"
        saida["nos_motivo"] = type(e).__name__
    saida["estado"] = pior_estado([saida["s3"], saida["nos"]])
    return saida


def _nginx() -> dict:
    """`systemctl is-active nginx`: leitura de estado da unidade, não exige privilégio. Sem systemd/sem a
    unidade instalada (ambiente de trilha, por exemplo) -> ausente, nunca erro fabricado."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "nginx"], capture_output=True, text=True, timeout=TEMPO_LIMITE_SONDA_S
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"estado": "ausente", "motivo": "systemctl indisponível nesta máquina/ambiente"}
    saida = r.stdout.strip() or r.stderr.strip()
    return {"estado": "ok" if saida == "active" else "erro", "unidade_systemd": saida}


def _certificado() -> dict:
    """Dias restantes do certificado TLS de PLAT_URL_PUBLICA. Domínio que não resolve/não fala TLS nesta
    topologia (trilha de teste, por exemplo) -> ausente: não é aplicável aqui, não é o certificado caído."""
    p = urlsplit(settings.PLAT_URL_PUBLICA)
    if p.scheme != "https" or not p.hostname:
        return {"estado": "ausente", "motivo": "PLAT_URL_PUBLICA não é https"}
    porta = p.port or 443
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.create_connection((p.hostname, porta), timeout=TEMPO_LIMITE_SONDA_S),
                              server_hostname=p.hostname) as s:
            cert = s.getpeercert()
        import datetime as _dt

        venc = _dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=_dt.UTC)
        dias = (venc - _dt.datetime.now(_dt.UTC)).days
        if dias < LIMITE_CERTIFICADO_ERRO_DIAS:
            estado = "erro"
        elif dias < LIMITE_CERTIFICADO_DEGRADADO_DIAS:
            estado = "degradado"
        else:
            estado = "ok"
        return {"estado": estado, "dias_restantes": dias}
    except (OSError, ssl.SSLError, TimeoutError, ValueError, KeyError):
        return {"estado": "ausente", "motivo": "TLS não verificável nesta topologia (host não resolve ou não fala TLS)"}


def _disco() -> dict:
    import os

    piores = []
    volumes = {}
    for v in VOLUMES_DISCO:
        if not os.path.isdir(v):
            continue
        st = os.statvfs(v)
        livre_pct = 100.0 * st.f_bavail / st.f_blocks if st.f_blocks else 0.0
        if livre_pct < LIMITE_DISCO_ERRO_PCT:
            e = "erro"
        elif livre_pct < LIMITE_DISCO_DEGRADADO_PCT:
            e = "degradado"
        else:
            e = "ok"
        volumes[v] = {"estado": e, "livre_pct": round(livre_pct, 1)}
        piores.append(e)
    if not volumes:
        return {"estado": "ausente", "motivo": "nenhum dos volumes declarados existe nesta máquina"}
    return {"estado": pior_estado(piores), "volumes": volumes}


def _ram() -> dict:
    info = {}
    with open("/proc/meminfo", encoding="ascii") as fh:
        for linha in fh:
            chave, _, resto = linha.partition(":")
            if chave in ("MemTotal", "MemAvailable"):
                info[chave] = int(resto.strip().split()[0])
    if "MemTotal" not in info or "MemAvailable" not in info or not info["MemTotal"]:
        return {"estado": "ausente", "motivo": "/proc/meminfo sem MemAvailable"}
    disponivel_pct = 100.0 * info["MemAvailable"] / info["MemTotal"]
    if disponivel_pct < LIMITE_RAM_ERRO_PCT:
        estado = "erro"
    elif disponivel_pct < LIMITE_RAM_DEGRADADO_PCT:
        estado = "degradado"
    else:
        estado = "ok"
    return {"estado": estado, "disponivel_pct": round(disponivel_pct, 1)}


def _ausente(motivo: str) -> Callable[[], dict]:
    return lambda: {"estado": "ausente", "motivo": motivo}


# ---------------------------------------------------------------- montagem da resposta


def _componentes() -> dict:
    """Dispara todas as sondas de uma vez (o pool as roda em paralelo) e só então coleta os resultados —
    cada `_sondar` já é bloqueante até o seu próprio tempo limite, então a submissão continua sequencial
    aqui, mas como cada sonda tem no máximo TEMPO_LIMITE_SONDA_S, o pior caso do endpoint inteiro é
    N * TEMPO_LIMITE_SONDA_S, nunca uma sonda travando as outras."""
    banco_fila = _sondar(_banco_e_fila)
    if banco_fila.get("estado") == "erro":
        # a sonda combinada falhou inteira (ex.: banco fora do ar): banco e fila herdam o mesmo erro
        banco = {"estado": "erro", "motivo": banco_fila.get("motivo")}
        fila = {"estado": "erro", "motivo": banco_fila.get("motivo")}
    else:
        banco = banco_fila["banco"]
        fila = banco_fila["fila"]
    banco["tempo_ms"] = banco_fila["tempo_ms"]
    fila["tempo_ms"] = banco_fila["tempo_ms"]

    return {
        "banco": banco,
        "fila": fila,
        "martin": _sondar(lambda: _servico_simples(settings.PLAT_MARTIN_URL)),
        "titiler": _sondar(lambda: _servico_simples(settings.PLAT_TITILER_URL)),
        "garage": _sondar(_garage),
        "worker": _sondar(lambda: _servico_simples(settings.PLAT_WORKER_URL)),
        "nginx": _sondar(_nginx),
        "certificado": _sondar(_certificado),
        "disco": _sondar(_disco),
        "ram": _sondar(_ram),
        "cdn_ultimo_hit": _sondar(_ausente("sem log de CDN acessível a partir do processo da API")),
        "backup": _sondar(_ausente("sem rotina de backup instrumentada nesta topologia")),
        "licenca": _sondar(_ausente("pilha aberta, sem licença a verificar")),
    }


def _resumir_anonimo(componentes: dict) -> dict:
    """Só nome + estado + tempo — nunca alvo, motivo detalhado ou qualquer campo específico do componente
    (isso já bastaria para revelar host/porta/versão em alguns casos)."""
    return {nome: {"estado": c["estado"], "tempo_ms": c["tempo_ms"]} for nome, c in componentes.items()}


@router.get("/saude/profunda")
def saude_profunda(request: Request, auth=Depends(auth_opcional)):
    inicio = time.perf_counter()
    componentes = _componentes()
    geral = pior_estado([c["estado"] for c in componentes.values()])

    eh_admin = bool(auth and auth.superadmin and auth.modo == "sessao")
    corpo = {
        "estado": geral,
        "componentes": componentes if eh_admin else _resumir_anonimo(componentes),
        "tempo_ms": round((time.perf_counter() - inicio) * 1000, 1),
        "em": agora_iso(),
    }
    return JSONResponse(corpo, status_code=200 if geral == "ok" else 503, headers={"Cache-Control": "no-store"})


router.add_api_route("/saude/profunda", saude_profunda, methods=["HEAD"], include_in_schema=False)
