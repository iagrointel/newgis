"""GET /saude e GET /api/versao (ADR 0001 seção 7). 200 só com banco ok E serviços obrigatórios ok
(garage quando configurado — ADR 20260908T2125); 503 em banco desatualizado, erro ou obrigatório doente."""

import datetime
import logging
import time
import urllib.error
import urllib.request

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db
from app.settings import settings
from app.versao import git_sha_curto, versao

router = APIRouter()
log = logging.getLogger("plat.saude")
TIMEOUT_SERVICO_S = 1.0

# Portão do L0-11 (achado G4-19): o Garage é OBRIGATÓRIO quando configurado — a plataforma guarda os
# objetos nele, então instalação com PLAT_GARAGE_URL apontando para um objeto-store que não responde é
# instalação doente (503), como banco fora. Fronteira: sem PLAT_GARAGE_URL o sonda fica "ausente"
# (desenvolvimento sem objetos) e NÃO derruba o status; martin/titiler/worker continuam informativos
# (worker vivo já é conferido por plat.fila_estado() na mesma resposta).
OBRIGATORIOS = ("garage",)


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
    urls = settings.servicos()
    servicos = {nome: sondar_servico(url) for nome, url in urls.items()}
    doentes = [nome for nome in OBRIGATORIOS if urls.get(nome) and servicos[nome] != "ok"]
    corpo = {
        "versao": versao(),
        "git_sha": git_sha_curto(),
        "ambiente": settings.PLAT_AMBIENTE,
        "banco": banco,
        "migracoes_aplicadas": aplicadas,
        "migracoes_pendentes": pendentes,
        "ultima_migracao": ultima,
        "servicos": servicos,
        "servicos_obrigatorios": list(OBRIGATORIOS),
        "fila": estado_fila() if banco == "ok" else {"erro": True},
        "tempo_ms": round((time.perf_counter() - inicio) * 1000, 1),
        "em": agora_iso(),
    }
    saudavel = banco == "ok" and not doentes
    return JSONResponse(corpo, status_code=200 if saudavel else 503, headers={"Cache-Control": "no-store"})


@router.get("/api/versao")
def api_versao():
    return {"versao": versao(), "git_sha": git_sha_curto(), "ambiente": settings.PLAT_AMBIENTE, "em": agora_iso()}


# HEAD (curl -sI, sondas) fora do esquema OpenAPI: mesma função, sem operationId duplicado
router.add_api_route("/saude", saude, methods=["HEAD"], include_in_schema=False)
router.add_api_route("/api/versao", api_versao, methods=["HEAD"], include_in_schema=False)
