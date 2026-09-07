"""Middleware de requisição: X-Req-Id, linha JSON no journal (redigida) e, para /api|/svc|/ogc|/tiles, uma linha em
plat.log_acesso gravada DEPOIS de o corpo ser enviado, com os bytes contados no body_iterator (ADR 0002 seção 9.1).
Rotas excluídas: /saude, /api/versao, /, /api/docs, /api/openapi.json (ruído do driver) e páginas.

Item L7-06-c: se o nginx já mandou `X-Req-Id` (config do item, `$request_id` do próprio nginx — NUNCA o que o
cliente mandou, o `proxy_set_header` sobrescreve), a API adota o MESMO id em vez de cunhar outro, para que a
linha de acesso do nginx e a linha JSON da API casem por igual em `plat logs --req-id`. Só aceita o formato
hexadecimal (8-40 chars); qualquer coisa fora disso é ignorada e a API cunha o dela, como sempre — como o
processo só escuta em 127.0.0.1 (só o nginx chega lá), o cabeçalho de entrada já é confiável, mas o formato
ainda é conferido para nunca deixar caractere de controle entrar numa linha de log JSON."""

import logging
import re
import time

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app import db
from app import log as plat_log
from app.auth.redigir import rota_redigida

log = logging.getLogger("plat.acesso")
PREFIXOS_COM_LOG = ("/api/", "/svc/", "/ogc/", "/tiles/")
SEM_LOG_ACESSO = frozenset({"/saude", "/api/versao", "/", "/api/docs", "/api/openapi.json"})
_REQ_ID_ENTRANTE = re.compile(r"^[0-9a-f]{8,40}$")


def gera_log(caminho: str) -> bool:
    return caminho not in SEM_LOG_ACESSO and caminho.startswith(PREFIXOS_COM_LOG)


def gravar_log_acesso(
    tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes_, tempo_ms, agente, resultado, req_id
):
    """Conexão própria do pool, sem contexto (a função confere p_tenant quando há contexto)."""
    try:
        with db.db() as cur:
            cur.execute(
                "SELECT plat.log_registrar(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (tenant_id, usuario_id, token_id, ip, metodo, rota, status, bytes_, tempo_ms, agente, resultado,
                 req_id),
            )
    except Exception:  # noqa: BLE001 — o log nunca derruba a resposta; a falha vai para o journal
        log.exception("log_acesso: falha ao gravar")


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def requisicao(request: Request, call_next):
        entrante = request.headers.get("x-req-id")
        rid = entrante if entrante and _REQ_ID_ENTRANTE.match(entrante) else plat_log.req_id()
        request.state.req_id = rid
        inicio = time.perf_counter()
        token_ctx = plat_log.definir_req_id_atual(rid)
        try:
            resposta = await call_next(request)
        finally:
            # o contexto só cobre a chamada da rota (onde o application_name do Postgres importa); a
            # escrita de log_acesso depois do corpo (contado(), abaixo) manda o req_id explícito.
            plat_log.limpar_req_id_atual(token_ctx)
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
                rid,
            )

        resposta.body_iterator = contado()
        return resposta
