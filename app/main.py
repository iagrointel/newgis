"""plat — API da plataforma SIG (FastAPI). Interno. Análise / beta privado.
Cria a aplicação, o middleware de requisição (X-Req-Id + linha JSON de acesso) e monta as rotas.
O nginx serve web/ em /static/ direto do disco (ADR 0001 seção 4.3); a API responde /, /saude e /api/."""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from app import log as plat_log
from app.saude import router as rotas_saude
from app.settings import settings
from app.versao import versao

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SEM_LOG_ACESSO = ("/saude", "/api/versao")

plat_log.configurar(settings.PLAT_LOG_NIVEL)
log = logging.getLogger("plat.acesso")

app = FastAPI(title="plat", version=versao(), docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def requisicao(request: Request, call_next):
    rid = plat_log.req_id()
    request.state.req_id = rid
    inicio = time.perf_counter()
    resposta = await call_next(request)
    tempo_ms = round((time.perf_counter() - inicio) * 1000, 1)
    resposta.headers["X-Req-Id"] = rid
    rota = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    nivel = logging.DEBUG if request.url.path in SEM_LOG_ACESSO else logging.INFO
    log.log(nivel, "acesso", extra={
        "req_id": rid, "metodo": request.method, "rota": rota[:500], "status": resposta.status_code,
        "tempo_ms": tempo_ms, "ip": request.client.host if request.client else None,
    })
    return resposta


app.include_router(rotas_saude)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def inicio():
    return FileResponse(WEB / "index.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})
