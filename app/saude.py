"""GET /saude, GET /api/versao e GET /metrics (ADR 0001 seção 7; item L7-06-a-metricas-exporters).
200 só com banco = ok; 503 em desatualizado e erro. /metrics não exige sessão nem token: a porta 8150
só escuta em 127.0.0.1 (systemd `plat-api.service`), o Prometheus da casa é o único cliente local, e o
conteúdo em si nunca carrega segredo (contrato de cardinalidade em app/metricas.py)."""

import datetime
import logging
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app import db, metricas
from app.settings import settings
from app.versao import git_sha_curto, versao

router = APIRouter()
log = logging.getLogger("plat.saude")
TIMEOUT_SERVICO_S = 1.0
metricas.registrar_coletor_fila(db.db)


def agora_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sondar_servico(url: str | None) -> str:
    """ausente sem URL; ok com status < 500 (o Garage responde 403 sem assinatura); erro caso contrário."""
    if not url:
        return "ausente"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SERVICO_S) as resp:  # noqa: S310 — URL vem do .env
            return "ok" if resp.status < 500 else "erro"
    except urllib.error.HTTPError as e:
        return "ok" if e.code < 500 else "erro"
    except (urllib.error.URLError, OSError, ValueError):
        return "erro"


def estado_fila() -> dict:
    """plat.fila_estado() (ADR 0003 seção 4.6): informativo neste item, não muda o status HTTP."""
    try:
        with db.db() as cur:
            cur.execute("SELECT * FROM plat.fila_estado()")
            r = cur.fetchone()
    except Exception:
        log.exception("saude: fila em erro")
        return {"erro": True}
    hb = r["ultimo_heartbeat"]
    return {"pendentes": r["pendentes"], "rodando": r["rodando"], "workers_vivos": r["workers_vivos"],
            "ultimo_heartbeat": hb.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if hb else None}


def estado_banco() -> tuple[str, int, int, str | None]:
    try:
        aplicadas, pendentes, ultima = db.migracoes_estado()
    except Exception:
        log.exception("saude: banco em erro")
        return "erro", 0, 0, None
    return ("desatualizado" if pendentes else "ok"), aplicadas, pendentes, ultima


@router.get("/saude")
def saude():
    inicio = time.perf_counter()
    banco, aplicadas, pendentes, ultima = estado_banco()
    servicos = {nome: sondar_servico(url) for nome, url in settings.servicos().items()}
    corpo = {
        "versao": versao(),
        "git_sha": git_sha_curto(),
        "ambiente": settings.PLAT_AMBIENTE,
        "banco": banco,
        "migracoes_aplicadas": aplicadas,
        "migracoes_pendentes": pendentes,
        "ultima_migracao": ultima,
        "servicos": servicos,
        "fila": estado_fila() if banco == "ok" else {"erro": True},
        "tempo_ms": round((time.perf_counter() - inicio) * 1000, 1),
        "em": agora_iso(),
    }
    return JSONResponse(corpo, status_code=200 if banco == "ok" else 503, headers={"Cache-Control": "no-store"})


@router.get("/api/versao")
def api_versao():
    return {"versao": versao(), "git_sha": git_sha_curto(), "ambiente": settings.PLAT_AMBIENTE, "em": agora_iso()}


# HEAD (curl -sI, sondas) fora do esquema OpenAPI: mesma função, sem operationId duplicado
router.add_api_route("/saude", saude, methods=["HEAD"], include_in_schema=False)
router.add_api_route("/api/versao", api_versao, methods=["HEAD"], include_in_schema=False)


@router.get("/metrics", include_in_schema=False)
def metricas_prometheus():
    corpo, tipo_conteudo = metricas.expor()
    return Response(content=corpo, media_type=tipo_conteudo, headers={"Cache-Control": "no-store"})
