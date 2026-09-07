"""plat — API da plataforma SIG (FastAPI). Interno. Análise / beta privado.
Cria a aplicação, instala o contrato de erro (app.erros), o middleware de requisição (X-Req-Id + linha JSON +
plat.log_acesso: app.auth.middleware) e monta os routers. O nginx serve web/ em /static/ direto do disco
(ADR 0001 seção 4.3); a API responde /, as páginas de app.paginas, /saude e /api/.
Cada trilha acrescenta o seu router na lista ROUTERS (uma linha por trilha; ordem = ordem de montagem)."""

import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from app import cabecalhos, erros, limite_corpo, paginas
from app import log as plat_log
from app.acervo import rotas as rotas_acervo
from app.auth import ldap as rotas_ldap
from app.auth import middleware as auth_middleware
from app.auth import (
    rotas_convites,
    rotas_eu,
    rotas_grupos,
    rotas_log,
    rotas_login,
    rotas_org,
    rotas_plataforma,
    rotas_redefinicao,
    rotas_tokens,
    rotas_usuarios,
)
from app.catalogo import (
    rotas_categorias,
    rotas_compartilhamento,
    rotas_favoritos,
    rotas_itens,
    rotas_lixeira,
    rotas_miniatura,
    rotas_ogc,
    rotas_pastas,
    transferencia,
)
from app.conexao import rotas as rotas_conexao
from app.correio.rotas_smtp import router as rotas_smtp
from app.geocodificador.rotas import router as rotas_geocodificador
from app.geocodificador.rotas_esri import router as rotas_geocodificador_esri
from app.ingestao.rotas import router as rotas_ingestao
from app.jobs.rotas import router as rotas_jobs
from app.rede.rotas import router as rotas_rede
from app.rotas_arquivos import router as rotas_arquivos
from app.saude import router as rotas_saude
from app.settings import settings
from app.uploads.rotas import router as rotas_uploads
from app.versao import versao

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
# Swagger UI servida do disco (web/vendor, sha256 em VERSOES.txt): nada de CDN em produção (ADR 0001 seção 11.4).
SWAGGER_JS = "/static/vendor/swagger-ui-bundle-5.32.15.js"
SWAGGER_CSS = "/static/vendor/swagger-ui-5.32.15.css"
FAVICON = "/static/favicon.svg"

plat_log.configurar(settings.PLAT_LOG_NIVEL)

app = FastAPI(title="plat", version=versao(), docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
erros.instalar(app)
auth_middleware.instalar(app)
# acrescentado por último: no empilhamento do Starlette isso o torna o mais externo, executando ANTES do
# middleware de log/sessão acima (ADR 0001 seção 12; app/limite_corpo.py) — corpo grande nunca chega à sessão.
limite_corpo.instalar(app)
# o mais externo de todos: toda resposta sai com CSP/nonce, Permissions-Policy, COOP/CORP, Referrer-Policy
# e nosniff, inclusive as que nascem de erro do middleware de corpo (item L7-03-e).
cabecalhos.instalar(app)

ROUTERS = [
    rotas_saude,
    # --- identidade (L0-02)
    rotas_login.router,
    rotas_eu.router,
    rotas_usuarios.router,
    rotas_grupos.router,
    rotas_tokens.router,
    rotas_log.router,
    rotas_plataforma.router,
    # --- configurações da organização (L0-07-a-configuracoes-org): GET/PUT /api/org; POST/DELETE /api/org/logo
    rotas_org.router,
    # --- LDAP/Active Directory (L0-08-d): POST /api/login/ldap; GET/PUT /api/org/ldap; POST /api/org/ldap/importar
    rotas_ldap.router,
    # --- SMTP, convite de membro e redefinição de senha (L0-07-d-smtp-convites): GET/PUT /api/org/smtp,
    # POST /api/org/smtp/testar; /api/convites (+ /resolver e /aceitar públicos); /api/senha/redefinir/*
    rotas_smtp,
    rotas_convites.router,
    rotas_redefinicao.router,
    # --- fila de jobs (L0-05): /api/jobs, /api/agendas, /tarefas
    rotas_jobs,
    # --- catálogo (L0-03): /api/itens, /api/pastas, /api/categorias, /api/favoritos, /api/lixeira, /api/compartilhado
    transferencia.router,  # /api/itens/transferir antes de /api/itens/{id}
    rotas_miniatura.router,
    rotas_itens.router,
    rotas_compartilhamento.router,
    rotas_pastas.router,
    rotas_categorias.router,
    rotas_favoritos.router,
    rotas_lixeira.router,
    # --- catálogo externo OGC API Records (L0-09-metadado-catalogo): /ogc/records; token catalogo:ler, nunca aberto
    rotas_ogc.router,
    # --- acervo da casa (L6-01-a): /api/acervo, /api/acervo/{fonte_id}, /api/acervo/{fonte_id}/adicionar
    rotas_acervo.router,
    # --- conexão externa (L6-02-a): /api/conexoes, /api/conexoes/{id}, /api/conexoes/{id}/testar
    rotas_conexao.router,
    # --- arquivos/objetos (L0-11): /api/arquivos genérico por inquilino; /api/objetos/{chave} já vem do catálogo
    # (rotas_compartilhamento, entrega por URL assinada)
    rotas_arquivos,
    # --- upload retomável (L0-04-a): /api/uploads (partes, retomada, tipo x conteúdo) -- antes de /api/itens
    # na ordem de import só por clareza (FastAPI resolve por path completo, sem colisão de prefixo)
    rotas_uploads,
    # --- ingestão vetorial (L0-04): /api/importacoes (upload -> inspeção -> confirmação -> carga -> camada)
    rotas_ingestao,
    # --- rede de rota (L2-11-c): /api/rota, /api/matriz, /api/isocrona sobre o OSRM de teste plat-osrm-guarulhos
    rotas_rede,
    # --- geocodificador (L2-11-b): /api/geocodificar, /api/reverso, /api/sugerir + GeocodeServer compatível
    # Esri em /rest/services/Geocodificador/GeocodeServer/*, sobre o CNEFE 2022 do IBGE instalado por UF
    rotas_geocodificador,
    rotas_geocodificador_esri,
    # --- páginas (cada trilha acrescenta a sua em app/paginas.py)
    paginas.router,
]
for _router in ROUTERS:
    app.include_router(_router)


@app.get("/api/docs", include_in_schema=False)
def documentacao_api(request: Request):
    """Swagger UI com todos os recursos locais; validatorUrl=None desliga a consulta ao validador externo.
    O único <script> em linha da casa é o de arranque da Swagger UI: recebe o nonce desta resposta, para que
    a CSP siga sendo `script-src 'self' 'nonce-...'`, sem 'unsafe-inline' (item L7-03-e)."""
    html = get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="plat — API",
        swagger_js_url=SWAGGER_JS,
        swagger_css_url=SWAGGER_CSS,
        swagger_favicon_url=FAVICON,
        swagger_ui_parameters={"validatorUrl": None},
    )
    corpo = html.body.decode("utf-8").replace("<script>", f'<script nonce="{request.state.csp_nonce}">')
    return HTMLResponse(corpo, headers={"Cache-Control": "no-store"})


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def inicio():
    return FileResponse(
        WEB / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"}
    )


SEGURANCA_TXT_DIAS = 90


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt():
    """RFC 9116. Gerado a cada leitura porque o campo Expires é obrigatório e um arquivo com data fixa
    envelhece em silêncio: aqui a validade é sempre a de hoje mais SEGURANCA_TXT_DIAS dias."""
    expira = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=SEGURANCA_TXT_DIAS)
    linhas = [
        f"Contact: {settings.PLAT_SEGURANCA_CONTATO}",
        f"Expires: {expira.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "Preferred-Languages: pt-BR, pt, en",
        f"Canonical: {settings.PLAT_URL_PUBLICA}/.well-known/security.txt",
        "",
    ]
    return PlainTextResponse("\n".join(linhas), media_type="text/plain; charset=utf-8")
