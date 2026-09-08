"""plat — API da plataforma SIG (FastAPI). Interno. Análise / beta privado.
Cria a aplicação, instala o contrato de erro (app.erros), o middleware de requisição (X-Req-Id + linha JSON +
plat.log_acesso: app.auth.middleware) e monta os routers. O nginx serve web/ em /static/ direto do disco
(ADR 0001 seção 4.3); a API responde /, as páginas de app.paginas, /saude e /api/.
Cada trilha acrescenta o seu router na lista ROUTERS (uma linha por trilha; ordem = ordem de montagem)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse

from app import erros, limite_corpo, paginas
from app import log as plat_log
from app.acervo import rotas as rotas_acervo
from app.amc import rotas as rotas_amc
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
from app.consulta import cors_servicos
from app.consulta.rotas_diretorio import router as rotas_diretorio_esri
from app.consulta.rotas_edicao_esri import router as rotas_edicao_esri
from app.consulta.rotas_ogc_features import router as rotas_ogc_features
from app.consulta.rotas_query import router as rotas_consulta_esri
from app.consulta.rotas_servico import router as rotas_consulta_servico
from app.consulta.rotas_wfs import router as rotas_wfs
from app.correio.rotas_smtp import router as rotas_smtp
from app.edicao.rotas import router as rotas_edicao
from app.geocodificador.rotas import router as rotas_geocodificador
from app.geocodificador.rotas_esri import router as rotas_geocodificador_esri
from app.ingestao.rotas import router as rotas_ingestao
from app.jobs.rotas import router as rotas_jobs
from app.multiescala.rotas import router as rotas_multiescala
from app.mapa.rotas import router as rotas_mapa
from app.mapas.rotas import router as rotas_mapas
from app.rede.rotas import router as rotas_rede
from app.rede_utilidades.rotas import router as rotas_rede_utilidades
from app.render.rotas import router as rotas_render
from app.rotas_arquivos import router as rotas_arquivos
from app.saude import router as rotas_saude
from app.settings import settings
from app.tiles.exportacao import router as rotas_tiles_exportacao
from app.tiles.rotas import router as rotas_tiles
from app.tiles.vector_tile_server import router as rotas_vector_tile_server
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
# CORS aberto só em /svc, /ogc e /tiles (item L2-04-b): lá a credencial é o token da URL, nunca o cookie.
cors_servicos.instalar(app)

if not settings.producao:
    # Em produção o nginx serve web/ em /static/ direto do disco (comentário do topo deste arquivo). Fora de
    # produção (trilha de teste, `venv/bin/uvicorn app.main:app` sem nginx na frente) não existe esse
    # servidor — o motor de render (L2-12-a) e qualquer e2e de navegador precisam de /static respondendo para
    # a página headless carregar MapLibre/pmtiles/estilo.js. Guardado por `settings.producao`: zero mudança de
    # comportamento em produção, só liga o que já faltava para testar sem nginx.
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(WEB)), name="static_dev")

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
    # --- edição transacional de feições (L2-03-a): POST /api/camadas/{id}/edicoes (adicionar/atualizar/apagar
    # numa transação; única porta de escrita de feição — FeatureServer/OGC futuros chamam este mesmo caminho)
    rotas_edicao,
    # --- mapa (L2-01-a-documento-mapa): /api/mapas (lista, criar, ler, editar) e /api/mapas/{id}/completo
    rotas_mapas,
    # --- mapa (L2-01-a-documento-mapa): /api/mapas (lista, criar, ler, editar) e /api/mapas/{id}/completo
    rotas_mapas,
    # --- motor de render no servidor (L2-12-a-motor-render-servidor): /api/render/mapa (PNG/PDF), token
    # interno de curta duração e /api/render/saude (fila, execução, falhas do pool de chromium)
    rotas_render,
    # --- rede de rota (L2-11-c): /api/rota, /api/matriz, /api/isocrona sobre o OSRM de teste plat-osrm-guarulhos
    rotas_rede,
    # --- rede de utilidades (L4-01-a): /api/rede (redes do inquilino), /api/rede/{rede_id}/pacote (importa e
    # exporta o pacote de ativos) e /api/rede/pacotes (os pacotes entregues com a instalação)
    rotas_rede_utilidades,
    # --- geocodificador (L2-11-b): /api/geocodificar, /api/reverso, /api/sugerir + GeocodeServer compatível
    # Esri em /rest/services/Geocodificador/GeocodeServer/*, sobre o CNEFE 2022 do IBGE instalado por UF
    rotas_geocodificador,
    rotas_geocodificador_esri,
    # --- motor multicritério, grades aninhadas (L3-19-multiescala): /api/multiescala/conjuntos, /fatores,
    # /fatores/{id}/amostras, /conjuntos/{id}/macro, /execucoes/{id}/micro, /execucoes
    rotas_multiescala,
    # --- servidor de tiles vetoriais em 3 contratos (L2-04-e): TileJSON+XYZ, VectorTileServer Esri
    # (descritor, estilo, sprites/fontes, tile z/y/x) e exportação por URL (geojson/kml/csv/fgb/gpkg).
    # ORDEM IMPORTA: tem de vir ANTES de `rotas_mapa`. As duas famílias moram em /tiles/, e o repasse
    # do visualizador (`/tiles/{esquema}/{funcao}/{z}/{x}/{y}`) casa, por forma de caminho, com o tile
    # vetorial (`/tiles/{token}/{item}/{z}/{x}/{y}.pbf`); quem casa primeiro responde, e como o
    # visualizador exige `y` inteiro, o `.pbf` do tile vetorial virava 422 em vez de tile. O tile
    # vetorial exige o sufixo `.pbf` no caminho, então as URLs do visualizador (sem sufixo) continuam
    # caindo nele normalmente.
    rotas_vector_tile_server,
    # --- visualizador de mapa (L2-01-mapa-web): /api/mapa/camadas, TileJSON com token curto, repasse /tiles
    rotas_mapa,
    # --- tiles vetoriais (L2-01-b): /internal/tiles/verificar (auth_request do nginx antes do Martin)
    rotas_tiles,
    # --- operação query do FeatureServer (L2-04-c): /rest/services/{item}/FeatureServer/{camada}/query
    # --- diretório/metadados do FeatureServer + OGC API Features Part 1 + WFS 2.0 (item
    # L2-04-servicos-esri-ogc, construído EM VOLTA da query acima, sem reescrevê-la): descritor de
    # serviço/camada (`?f=json`), `/ogc/features/{item}` e `/wfs/{item}`. applyEdits/attachments/
    # relationships ficam de fora (dependem de L2-03-edicao e L2-10-b, nenhum construído).
    rotas_consulta_esri,
    rotas_consulta_servico,
    # --- diretório de serviços Esri por token (L2-04-b): /svc/{token}/rest/info|generateToken|services
    rotas_diretorio_esri,
    rotas_ogc_features,
    rotas_wfs,
    # --- escrita compatível Esri (L2-04-d): applyEdits/addFeatures/updateFeatures/deleteFeatures, calculate,
    # anexos e uploads sobre a MESMA porta de escrita do L2-03-a
    rotas_edicao_esri,
    # --- motor de análise multicritério (L3-01-a): /api/amc/modelos, /api/amc/conjuntos, /api/amc/execucoes
    rotas_amc.router,
    rotas_tiles_exportacao,
    # --- páginas (cada trilha acrescenta a sua em app/paginas.py)
    paginas.router,
]
for _router in ROUTERS:
    app.include_router(_router)


@app.get("/api/docs", include_in_schema=False)
def documentacao_api():
    """Swagger UI com todos os recursos locais; validatorUrl=None desliga a consulta ao validador externo."""
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="plat — API",
        swagger_js_url=SWAGGER_JS,
        swagger_css_url=SWAGGER_CSS,
        swagger_favicon_url=FAVICON,
        swagger_ui_parameters={"validatorUrl": None},
    )


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def inicio():
    return FileResponse(
        WEB / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"}
    )


@app.on_event("shutdown")
async def _fechar_motor_render():
    """O pool de chromium (L2-12-a-motor-render-servidor) nasce SÓ no primeiro `POST /api/render/mapa` (nunca
    no startup — a suíte inteira sobe esta app centenas de vezes por sessão de teste, e um chromium por
    instância derrubaria a máquina). Quando ele nasceu, fecha aqui para não vazar processo do navegador."""
    from app.render.motor import motor

    m = motor()
    if m.ativo:
        await m.parar()
