"""Modo somente-leitura/manutenção global e por inquilino (item L7-33-modo-somente-leitura; ADR deste item;
paridade com o `mode` do Portal e o site mode READ_ONLY do ArcGIS Server).

A bandeira vive em `plat.sistema` (chave/valor com quem/quando/motivo, escrita só pelas funções
`plat.modo_ligar/modo_desligar` via CLI `plat modo`, role do worker) e é lida AQUI pelo middleware:
todo verbo de escrita (POST/PUT/PATCH/DELETE) recebe 503 com `Retry-After` (RFC 9110 seção 10.2.3) e o
contrato de erro da casa (ADR 0002 seção 14 — é o "problem details" da plataforma: código curto, mensagem
em português, detalhe com motivo/escopo/desde/quem e req_id). Leitura, tiles e exportação (GET/HEAD)
nunca passam por aqui.

Isenções fixas do portão do item, nunca bloqueadas: `/saude` e `/status` (o monitoramento tem de continuar
vendo a plataforma durante a manutenção), `/api/logout` (ninguém fica preso numa sessão) e `GET /api/modo`
(a própria consulta do estado, usada pela faixa do front).

Escopo: global vence sempre; sem flag global, vale a do inquilino da credencial (cookie de sessão ou
Bearer). Pedido anônimo só enxerga o modo global — a rota segue e responde o 401/400 dela, como antes.

Instalado em app/main.py ANTES de app.auth.middleware.instalar(app): no empilhamento do Starlette o
middleware acrescentado por último é o mais externo, então este roda DEPOIS do de log — a escrita
bloqueada sai com X-Req-Id, Cache-Control e linha em plat.log_acesso com status 503 (a recusa fica
auditável no mesmo lugar de qualquer outra resposta). Erro aqui é RESPOSTA montada na hora, nunca
exceção: middleware de usuário fica fora do ExceptionMiddleware do Starlette (ver app/limite_corpo.py).
"""

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import db
from app.erros import ErroAPI, corpo_erro

log = logging.getLogger("plat.modo")

VERBOS_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ISENTOS = frozenset({"/saude", "/status", "/api/logout", "/api/modo"})
RETRY_AFTER_PADRAO_S = 300

router = APIRouter(tags=["modo"])


def estado(tenant_id: int | None) -> dict:
    """Estado efetivo do modo para o inquilino (None = anônimo: só o global)."""
    with db.db() as cur:
        cur.execute("SELECT plat.modo_ler(%s) AS m", (tenant_id,))
        return dict(cur.fetchone()["m"])


def _tenant_da_requisicao(request: Request) -> int | None:
    """Inquilino da credencial, quando houver; credencial ruim NÃO é assunto deste middleware
    (a rota responde o 401/400 dela como sempre respondeu)."""
    from app.auth import sessao

    try:
        auth = sessao.resolver(request)
    except ErroAPI:
        return None
    return auth.tenant_id if auth is not None else None


def _resposta_503(request: Request, m: dict) -> JSONResponse:
    retry = int(m.get("retry_after_s") or RETRY_AFTER_PADRAO_S)
    escopo = "a plataforma" if m.get("escopo") == "global" else "este inquilino"
    mensagem = f"{escopo} está em manutenção (somente leitura): {m.get('motivo')}"
    detalhe = {k: m.get(k) for k in ("motivo", "escopo", "desde", "quem", "tenant_id") if m.get(k) is not None}
    detalhe["retry_after_s"] = retry
    corpo = corpo_erro(request, "modo_manutencao", mensagem, detalhe)
    log.info("escrita bloqueada pelo modo de manutenção: %s %s (%s)",
             request.method, request.url.path, m.get("motivo"))
    return JSONResponse(corpo, status_code=503, headers={"Retry-After": str(retry)})


def _bloqueio(request: Request) -> JSONResponse | None:
    m = estado(_tenant_da_requisicao(request))
    return _resposta_503(request, m) if m.get("ativo") else None


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def modo_manutencao(request: Request, call_next):
        if request.method in VERBOS_ESCRITA and request.url.path not in ISENTOS:
            resposta = await run_in_threadpool(_bloqueio, request)
            if resposta is not None:
                return resposta
        return await call_next(request)


@router.get("/api/modo", summary="estado do modo de manutenção (global ou do inquilino da sessão)")
def modo_estado(request: Request) -> dict:
    """Público e sempre 200: é o que a faixa do front consulta para mostrar o motivo da manutenção."""
    return estado(_tenant_da_requisicao(request))
