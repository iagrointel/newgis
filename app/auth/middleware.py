"""Middleware de requisição: X-Req-Id, linha JSON no journal (redigida) e, para /api|/svc|/ogc|/tiles, uma linha em
plat.log_acesso gravada DEPOIS de o corpo ser enviado, com os bytes contados no body_iterator (ADR 0002 seção 9.1).
Rotas excluídas: /saude, /api/versao, /, /api/docs, /api/openapi.json (ruído do driver) e páginas."""

import logging
import time

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app import log as plat_log
from app.auth.redigir import rota_redigida

log = logging.getLogger("plat.acesso")
PREFIXOS_COM_LOG = ("/api/", "/svc/", "/ogc/", "/tiles/")
SEM_LOG_ACESSO = frozenset({"/saude", "/api/versao", "/", "/api/docs", "/api/openapi.json"})


def gera_log(caminho: str) -> bool:
    return caminho not in SEM_LOG_ACESSO and caminho.startswith(PREFIXOS_COM_LOG)


def gravar_log_acesso(tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes_, tempo_ms, agente, resultado):
    """Conexão própria do pool, sem contexto (a função confere p_tenant quando há contexto)."""
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT plat.log_registrar(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes_, tempo_ms, agente, resultado),
            )
    except Exception:  # noqa: BLE001 — o log nunca derruba a resposta; a falha vai para o journal
        log.exception("log_acesso: falha ao gravar")


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def requisicao(request: Request, call_next):
        rid = plat_log.req_id()
        request.state.req_id = rid
        inicio = time.perf_counter()
        resposta = await call_next(request)
        resposta.headers["X-Req-Id"] = rid
        # Cache-Control com UMA origem só (decisão T2): a aplicação. O nginx não acrescenta o dele nas rotas
        # proxiadas (add_header ACRESCENTA, nunca substitui: saíam dois cabeçalhos, e uma rota que precisa de
        # cache — miniatura `private, max-age=300` — sairia contradita). Aqui fica o PISO; a rota que declara o
        # seu vence, porque setdefault não sobrescreve.
        resposta.headers.setdefault("Cache-Control", "no-store, must-revalidate")
        caminho = request.url.path
        rota = rota_redigida(caminho, request.url.query)
        estado = request.state

        def campos(bytes_: int = 0) -> dict:
            return {
                "req_id": rid,
                "metodo": request.method,
                "rota": rota,
                "status": resposta.status_code,
                "tempo_ms": round((time.perf_counter() - inicio) * 1000, 1),
                "ip": request.client.host if request.client else None,
                "tenant_id": getattr(estado, "tenant_id", None),
                "usuario_id": getattr(estado, "usuario_id", None),
                "token_id": getattr(estado, "token_id", None),
                "bytes": bytes_,
            }

        if not gera_log(caminho):
            nivel = logging.DEBUG if caminho in SEM_LOG_ACESSO else logging.INFO
            log.log(nivel, "acesso", extra=campos())
            return resposta

        original = resposta.body_iterator

        async def contado():
            total = 0
            async for pedaco in original:
                total += len(pedaco)
                yield pedaco
            c = campos(total)
            log.info("acesso", extra=c)
            await run_in_threadpool(
                gravar_log_acesso,
                c["tenant_id"],
                c["usuario_id"],
                c["token_id"],
                c["ip"],
                request.method,
                rota,
                resposta.status_code,
                total,
                int(c["tempo_ms"]),
                request.headers.get("user-agent", ""),
                getattr(estado, "resultado", None),
            )

        resposta.body_iterator = contado()
        return resposta
