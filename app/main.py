"""plat — API da plataforma SIG (FastAPI). Interno. Análise / beta privado.
Cria a aplicação, o middleware de requisição (X-Req-Id + linha JSON de acesso) e monta as rotas.
O nginx serve web/ em /static/ direto do disco (ADR 0001 seção 4.3); a API responde /, /saude e /api/."""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse

from app import log as plat_log
from app.saude import router as rotas_saude
from app.settings import settings
from app.versao import versao

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SEM_LOG_ACESSO = ("/saude", "/api/versao")
# Swagger UI servida do disco (web/vendor, sha256 em VERSOES.txt): nada de CDN em produção (ADR 0001 seção 11.4).
SWAGGER_JS = "/static/vendor/swagger-ui-bundle-5.32.15.js"
SWAGGER_CSS = "/static/vendor/swagger-ui-5.32.15.css"
FAVICON = "/static/favicon.svg"

plat_log.configurar(settings.PLAT_LOG_NIVEL)
log = logging.getLogger("plat.acesso")

app = FastAPI(title="plat", version=versao(), docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")


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


@app.get("/api/docs", include_in_schema=False)
def documentacao_api():
    """Swagger UI com todos os recursos locais; validatorUrl=None desliga a consulta ao validador externo."""
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json", title="plat — API", swagger_js_url=SWAGGER_JS, swagger_css_url=SWAGGER_CSS,
        swagger_favicon_url=FAVICON, swagger_ui_parameters={"validatorUrl": None},
    )


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def inicio():
    return FileResponse(WEB / "index.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})
