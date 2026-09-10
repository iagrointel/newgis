"""plat — API da plataforma SIG (FastAPI). Interno. Análise / beta privado.
Cria a aplicação, instala o contrato de erro (app.erros), o middleware de requisição (X-Req-Id + linha JSON +
plat.log_acesso: app.auth.middleware) e monta os routers. O nginx serve web/ em /static/ direto do disco
(ADR 0001 seção 4.3); a API responde /, as páginas de app.paginas, /saude e /api/.
Cada trilha acrescenta o seu router na lista ROUTERS (uma linha por trilha; ordem = ordem de montagem)."""

import os
import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import erros, limite_corpo, paginas, rotas_qr
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from app import cabecalhos, erros, limite_corpo, paginas
from app import erros, limite_corpo, modo, paginas
from app import log as plat_log
from app.acervo import publicacao as rotas_acervo_publicacao
from app.acervo import rotas as rotas_acervo
from app.amc import rotas as rotas_amc
from app.analise3d.rotas import router as rotas_analise3d
from app.amc.rotas_pareto import router as rotas_amc_pareto
from app.auth import ldap as rotas_ldap
from app.auth import middleware as auth_middleware
from app.auth import (
    rotas_auditoria,
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
    camada_esquema,
    rotas_categorias,
    rotas_compartilhamento,
    rotas_favoritos,
    rotas_itens,
    rotas_lixeira,
    rotas_miniatura,
    rotas_ogc,
    rotas_pastas,
    rotas_presenca,  # L5-13: presença em documento (SSE)
    transferencia,
    vista_camada,
)
from app.chamados import rotas as rotas_chamados
from app.conexao import rotas as rotas_conexao
from app.consulta import cors_servicos
from app.consulta.rotas_diretorio import router as rotas_diretorio_esri
from app.consulta.rotas_edicao_esri import router as rotas_edicao_esri
from app.consulta.rotas_geometria import router as rotas_geometry_server
from app.consulta.rotas_mapserver import router as rotas_mapserver_esri
from app.consulta.rotas_ogc_features import router as rotas_ogc_features
from app.consulta.rotas_query import router as rotas_consulta_esri
from app.consulta.rotas_servico import router as rotas_consulta_servico
from app.consulta.rotas_sync_esri import router as rotas_sync_esri
from app.consulta.rotas_wfs import router as rotas_wfs
from app.correio.rotas_smtp import router as rotas_smtp
from app.dominios import rotas as rotas_dominios
from app.dominios import rotas_featureserver, rotas_feicoes
from app.edicao.rotas import router as rotas_edicao
from app.exportacao.rotas import router as rotas_exportacao
from app.estatistica.rotas import router as rotas_estatistica
from app.estatistica.rotas_graficos import router as rotas_graficos
from app.exportacao.rotas import router as rotas_exportacao
from app.exportacao_inquilino.rotas import router as rotas_exportacao_inquilino
from app.crs.rotas import router as rotas_crs
from app.edicao.rotas import router as rotas_edicao
from app.geocodificador.rotas import router as rotas_geocodificador
from app.geocodificador.rotas_esri import router as rotas_geocodificador_esri
from app.imagens.rotas_imagens import router as rotas_imagens
from app.imagens.rotas_stac import router as rotas_stac
from app.imagens.rotas_tiles import router as rotas_tiles
from app.exportacao.rotas import router as rotas_exportacao
from app.geocodificador.rotas import router as rotas_geocodificador
from app.geocodificador.rotas_esri import router as rotas_geocodificador_esri
from app.geocodificador.rotas_lote import router as rotas_geocodificacao_lote
from app.imagens.rotas_stac import router as rotas_stac
from app.imagens.rotas_tiles import router as rotas_tiles
from app.geocodificador.rotas_lote import router as rotas_geocodificador_lote
from app.ingestao.rotas import router as rotas_ingestao
from app.intercambio.lote_importar import router as rotas_intercambio_lote_importar
from app.intercambio.rotas import router as rotas_intercambio
from app.jobs.rotas import router as rotas_jobs
from app.mapa.proxy_wms import router as rotas_mapa_wms_publico
from app.mapa.rotas import router as rotas_mapa
from app.mapas.rotas import router as rotas_mapas
from app.layout import rotas as rotas_layout
from app.mapa.anotacoes import router as rotas_anotacoes
from app.mapa.exportar import router as rotas_exportar_mapa
from app.mapa.popup import router as rotas_mapa_popup
from app.mapa.promover import router as rotas_promover
from app.mapa.rotas import router as rotas_mapa
from app.mapa.selecao import router as rotas_selecao
from app.migracao.rotas import router as rotas_migracao
from app.multiescala.rotas import router as rotas_multiescala
from app.paineis.rotas import router as rotas_paineis
from app.mapa.rotas import router as rotas_mapa
from app.mapas.rotas import router as rotas_mapas
from app.multiescala.rotas import router as rotas_multiescala
from app.rede.consumidores_rotas import router as rotas_rede_consumidores
from app.multiescala.rotas import router as rotas_multiescala
from app.portal import openapi as portal_openapi
from app.portal.rotas import router as rotas_portal
from app.mapa.selecao import router as rotas_selecao
from app.rede.rotas import router as rotas_rede
from app.rede_utilidades.rotas import router as rotas_rede_utilidades
from app.rede_utilidades.rotas_config_tracado import router as rotas_rede_config_tracado
from app.rede_utilidades.rotas_controladores import router as rotas_rede_controladores
from app.rede_utilidades.rotas_curto import router as rotas_rede_curto
from app.rede_utilidades.rotas_diagrama import router as rotas_rede_diagrama
from app.rede_utilidades.rotas_fluxo import router as rotas_rede_fluxo
from app.rede_utilidades.rotas_matpower import router as rotas_rede_matpower
from app.rede_utilidades.rotas_resultados import router as rotas_rede_resultados
from app.rede_utilidades.rotas_resumos import router as rotas_rede_resumos
from app.rede_utilidades.rotas_simples import router as rotas_rede_simples
from app.rede_utilidades.rotas_subredes import router as rotas_rede_subredes
from app.rede_utilidades.rotas_topologia import router as rotas_rede_topologia
from app.regras.rotas import router as rotas_regras  # L2-10-d: regras de atributo por camada
from app.replica.rotas import router as rotas_replicas
from app.relacionamentos.rotas import router as rotas_relacionamentos
from app.relatorios.rotas import router as rotas_relatorios
from app.mapas.rotas import router as rotas_mapas
from app.migracao.rotas import router as rotas_migracao
from app.multiescala import regioes_rotas as rotas_regioes  # L3-05: localizar regiões
from app.multiescala.rotas import router as rotas_multiescala
from app.rede.rotas import router as rotas_rede
from app.rede_utilidades.rotas import router as rotas_rede_utilidades
from app.mapas.rotas import router as rotas_mapas
from app.rede.rotas import router as rotas_rede
from app.rede_utilidades.rotas import router as rotas_rede_utilidades
from app.render.rotas import router as rotas_render
from app.rede_utilidades.rotas_topologia import router as rotas_rede_topologia
from app.rotas_arquivos import router as rotas_arquivos
from app.rotas_temas import router as rotas_temas
from app.rotas_videos import router as rotas_videos
from app.rotas_notificacoes import router as rotas_notificacoes
from app.saude import router as rotas_saude
from app.saude_profunda import router as rotas_saude_profunda
from app.settings import settings
from app.tiles.exportacao import router as rotas_tiles_exportacao
from app.tiles.rotas import router as rotas_tiles_martin_verificar
from app.tiles.vector_tile_server import router as rotas_vector_tile_server
from app.tabela.rotas import router as rotas_tabela
from app.tiles.rotas import router as rotas_tiles
from app.status import router as rotas_status
from app.uploads.rotas import router as rotas_uploads
from app.versao import versao
from app.widgets.rotas import router as rotas_widgets_externos

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
# Swagger UI servida do disco (web/vendor, sha256 em VERSOES.txt): nada de CDN em produção (ADR 0001 seção 11.4).
SWAGGER_JS = "/static/vendor/swagger-ui-bundle-5.32.15.js"
SWAGGER_CSS = "/static/vendor/swagger-ui-5.32.15.css"
FAVICON = "/static/favicon.svg"

plat_log.configurar(settings.PLAT_LOG_NIVEL)

app = FastAPI(title="plat", version=versao(), docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
erros.instalar(app)
# modo de manutenção (L7-33) ANTES do middleware de log: na pilha do Starlette ele roda DEPOIS dele,
# então a escrita bloqueada sai com X-Req-Id e linha em plat.log_acesso (recusa auditável)
modo.instalar(app)
auth_middleware.instalar(app)
# acrescentado por último: no empilhamento do Starlette isso o torna o mais externo, executando ANTES do
# middleware de log/sessão acima (ADR 0001 seção 12; app/limite_corpo.py) — corpo grande nunca chega à sessão.
limite_corpo.instalar(app)
# CORS aberto só em /svc, /ogc e /tiles (item L2-04-b): lá a credencial é o token da URL, nunca o cookie.
cors_servicos.instalar(app)

if os.environ.get("PLAT_SERVIR_STATIC_DEV") == "1":
    # SÓ para e2e de trilha isolada (uvicorn solto na porta do item, sem nginx na frente): em produção e em
    # homologação o nginx serve web/ em /static/ direto do disco (ADR 0001 seção 4.3) e esta variável nunca
    # é setada. Nunca monta por cima de uma rota /api existente (StaticFiles fica só em /static).
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(WEB)), name="static-dev")

if not settings.producao:
    # Em produção o nginx serve web/ em /static/ direto do disco (comentário do topo deste arquivo). Fora de
    # produção (trilha de teste, `venv/bin/uvicorn app.main:app` sem nginx na frente) não existe esse
    # servidor — o motor de render (L2-12-a) e qualquer e2e de navegador precisam de /static respondendo para
    # a página headless carregar MapLibre/pmtiles/estilo.js. Guardado por `settings.producao`: zero mudança de
    # comportamento em produção, só liga o que já faltava para testar sem nginx.
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(WEB)), name="static_dev")
# o mais externo de todos: toda resposta sai com CSP/nonce, Permissions-Policy, COOP/CORP, Referrer-Policy
# e nosniff, inclusive as que nascem de erro do middleware de corpo (item L7-03-e).
cabecalhos.instalar(app)

ROUTERS = [
    rotas_saude,
    rotas_saude_profunda,  # L7-34-saude-profunda
    rotas_status,  # L0-06-e-status: GET /api/status (aberto, agregado, cache de 30 s) + página /status
    # --- identidade (L0-02)
    rotas_login.router,
    rotas_eu.router,
    rotas_usuarios.router,
    rotas_grupos.router,
    rotas_tokens.router,
    rotas_log.router,
    # --- trilha de auditoria (L7-20): GET /api/auditoria (+ CSV/JSON), GET/PUT /api/auditoria/config
    rotas_auditoria.router,
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
    # --- modo de manutenção (L7-33): GET /api/modo público (a faixa do front consulta o motivo aqui)
    modo.router,
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
    # --- documento de painel (L2-06-a-modelo-painel-fontes): dados por fonte, sessão/token e link anônimo
    rotas_paineis,
    # --- notificações internas (L0-03-k): /api/notificacoes (sino, lista, marcar lida, apagar)
    rotas_notificacoes,
    # --- catálogo externo OGC API Records (L0-09-metadado-catalogo): /ogc/records; token catalogo:ler, nunca aberto
    rotas_ogc.router,
    # --- layout de impressão (L2-12-b): /api/layouts, página headless do quadro e Export Web Map Task (Esri)
    rotas_layout.router,
    rotas_presenca.router,
    # --- acervo da casa (L6-01-a): /api/acervo, /api/acervo/{fonte_id}, /api/acervo/{fonte_id}/adicionar
    # publicacao ANTES de rotas_acervo: /api/acervo/camadas casaria com /api/acervo/{fonte_id} se viesse depois
    rotas_acervo_publicacao.router,
    rotas_acervo.router,
    # --- conexão externa (L6-02-a): /api/conexoes, /api/conexoes/{id}, /api/conexoes/{id}/testar
    rotas_conexao.router,
    # --- chamados de suporte (L7-13-a): /api/chamados (cliente, com captura e anexos) e
    # /api/plataforma/chamados (painel do operador superadmin, fila de todos os inquilinos)
    rotas_chamados.router,
    rotas_chamados.router_operador,
    # --- arquivos/objetos (L0-11): /api/arquivos genérico por inquilino; /api/objetos/{chave} já vem do catálogo
    # (rotas_compartilhamento, entrega por URL assinada)
    rotas_arquivos,
    # --- upload retomável (L0-04-a): /api/uploads (partes, retomada, tipo x conteúdo) -- antes de /api/itens
    # na ordem de import só por clareza (FastAPI resolve por path completo, sem colisão de prefixo)
    rotas_uploads,
    # --- ingestão vetorial (L0-04): /api/importacoes (upload -> inspeção -> confirmação -> carga -> camada)
    rotas_ingestao,
    # --- construtor de camada por esquema (L5-31): /api/camadas/esquema, /api/camadas/{id}/esquema[/plano],
    # /api/camadas/{id}/campos (fields no formato FeatureServer)
    camada_esquema.router,
    # --- vista de camada (L5-32): POST /api/camadas/{id}/vistas, GET/PUT /api/vistas/{id} (view PostgreSQL
    # com filtro congelado e campos ocultos; servida pelo mesmo FeatureServer/OGC da camada-mãe)
    vista_camada.router,
    # --- edição transacional de feições (L2-03-a): POST /api/camadas/{id}/edicoes (adicionar/atualizar/apagar
    # numa transação; única porta de escrita de feição — FeatureServer/OGC futuros chamam este mesmo caminho)
    rotas_edicao,
    # --- mapa (L2-01-a-documento-mapa): /api/mapas (lista, criar, ler, editar) e /api/mapas/{id}/completo
    rotas_mapas,
    # --- exportação de camada (L0-04-h) e do mapa (L2-01-l): /api/exportacoes (15 formatos por ogr2ogr
    # mais o pacote de mapa; arquivo com validade de 7 dias)
    rotas_exportacao,
    rotas_regras,
    rotas_replicas,   # L2-13-b: réplicas para trabalho desconectado
    # --- domínios de atributo e subtipos (L2-10-a): /api/dominios, /api/camadas/{id}/dominios e /subtipos
    rotas_dominios.router,
    # --- gravação de UMA feição pelo formulário de atributos (L2-10-a; edição em lote é da linha L2-08)
    rotas_feicoes.router,
    # --- metadado de FeatureServer com domains/types (L2-10-a; /query e /applyEdits são da linha L2-08)
    rotas_featureserver.router,
    # --- edição transacional de feições (L2-03-a): POST /api/camadas/{id}/edicoes (adicionar/atualizar/apagar
    # numa transação; única porta de escrita de feição — FeatureServer/OGC futuros chamam este mesmo caminho)
    rotas_edicao,
    # --- classes de relacionamento entre camadas (L2-10-b): /api/relacionamentos, /api/camadas/{id}/
    # relacionados/{rel}, .../ligar, .../desligar; queryRelatedRecords no FeatureServer
    rotas_relacionamentos,
    # --- edição transacional de feições (L2-03-a): POST /api/camadas/{id}/edicoes (adicionar/atualizar/apagar
    # numa transação; única porta de escrita de feição — FeatureServer/OGC futuros chamam este mesmo caminho)
    # --- exportação de camada (L0-04-h): /api/exportacoes (11 formatos por ogr2ogr, arquivo com validade de 7 dias)
    rotas_exportacao,
    rotas_exportacao_inquilino,
    # --- exportação de camada (L0-04-h): /api/exportacoes (11 formatos por ogr2ogr, arquivo com validade de 7 dias)
    rotas_exportacao,
    # --- mapa (L2-01-a-documento-mapa): /api/mapas (lista, criar, ler, editar) e /api/mapas/{id}/completo
    rotas_mapas,
    # --- domínios de atributo e subtipos (L2-10-a, trazido do ramo wt/garage): /api/dominios,
    # /api/camadas/{id}/dominios e /subtipos; a ingestão de FileGDB escreve nestas tabelas (L0-04-f)
    rotas_dominios.router,
    rotas_feicoes.router,
    rotas_featureserver.router,
    # --- intercâmbio em lote (L6-02-o): /api/intercambio (formatos extra: filegdb.zip, mbtiles, pmtiles,
    # geojsonseq; exportação do inquilino inteiro em GeoPackage + manifesto; importação em lote sobre L0-04)
    rotas_intercambio,
    rotas_intercambio_lote_importar,
    # --- mapa (L2-01-a-documento-mapa): /api/mapas (lista, criar, ler, editar) e /api/mapas/{id}/completo
    rotas_mapas,
    # --- motor de render no servidor (L2-12-a-motor-render-servidor): /api/render/mapa (PNG/PDF), token
    # interno de curta duração e /api/render/saude (fila, execução, falhas do pool de chromium)
    rotas_render,
    # --- edição transacional de feições (L2-03-a): POST /api/camadas/{id}/edicoes (adicionar/atualizar/apagar
    # numa transação; única porta de escrita de feição — FeatureServer/OGC futuros chamam este mesmo caminho)
    rotas_edicao,
    # --- rede de rota (L2-11-c): /api/rota, /api/matriz, /api/isocrona sobre o OSRM de teste plat-osrm-guarulhos
    rotas_rede,
    # --- rede de utilidades (L4-01-a): /api/rede (redes do inquilino), /api/rede/{rede_id}/pacote (importa e
    # exporta o pacote de ativos) e /api/rede/pacotes (os pacotes entregues com a instalação)
    rotas_rede_utilidades,
    rotas_rede_matpower,
    # --- topologia derivada da rede de utilidades (L4-01-b): /api/rede/{rede_id}/feicoes/{pontos,linhas}
    # (as camadas de rede, editáveis) e /api/rede/{rede_id}/topologia/{habilitar,nos,arestas} (o índice derivado)
    rotas_rede_topologia,
    # --- configuração de traçado (L4-02-e): /api/rede/{rede_id}/config_tracado (CRUD) e o campo `config_id`
    # do POST /api/rede/{rede_id}/tracar, que faz o traçado ler o pedido salvo em vez do corpo
    rotas_rede_config_tracado,
    # --- resultado do traçado (L4-02-f): /api/rede/{rede_id}/tracar/{exportar,camada} e o histórico em
    # /api/rede/{rede_id}/tracados (+ .../{execucao_id}/repetir)
    rotas_rede_resultados,
    # --- rede simples (L4-18): /api/rede/simples (cria a partir de 2 camadas do inquilino),
    # /api/rede/{rede_id}/simples (a configuração) e /api/rede/{rede_id}/promover (pacote mínimo)
    rotas_rede_simples,
    # --- controlador de subrede e tiers (L4-04-a): /api/rede/{rede_id}/controlador,
    # /api/rede/{rede_id}/{subredes,tiers} e /api/rede/{rede_id}/controladores/importar
    rotas_rede_controladores,
    # --- atualizar e exportar subrede (L4-04-b): /api/rede/{rede_id}/subredes/atualizar (job),
    # /api/rede/{rede_id}/subredes/conferencia, /api/rede/{rede_id}/subrede/{nome}/exportar e os propagadores
    rotas_rede_subredes,
    # --- sumário por subrede (L4-04-c): /api/rede/{rede_id}/subredes/resumos (tabela e CSV) e
    # /api/rede/{rede_id}/subredes/resumos/calcular
    rotas_rede_resumos,
    # --- curto-circuito e coordenação de proteção (L4-27): /api/rede/{rede_id}/subrede/{nome}/curto
    # (POST calcula com as premissas declaradas, GET a tabela) e .../curto/camada
    rotas_rede_curto,
    # --- diagrama de rede (L4-04-d): /api/rede/{rede_id}/diagrama (gerar), /diagramas, /diagrama/{id},
    # .../layout, .../exportar (json|svg|png) e os modelos em /diagrama-modelos
    rotas_rede_diagrama,
    # --- fluxo de potência do alimentador (L4-07): /api/rede/{rede_id}/subrede/{nome}/fluxo
    # (POST analisa no OpenDSS com os parâmetros declarados, GET a tabela) e .../fluxo/camada
    rotas_rede_fluxo,
    # --- consumidores e endereços da rede (L4-20): camada de endereços sem rede próxima, ficha de
    # unidade consumidora (sem campo identificável) e consumidores a jusante por trecho de média tensão
    rotas_rede_consumidores,
    # --- topologia derivada da rede de utilidades (L4-01-b): /api/rede/{rede_id}/feicoes/{pontos,linhas}
    # (as camadas de rede, editáveis) e /api/rede/{rede_id}/topologia/{habilitar,nos,arestas} (o índice derivado)
    rotas_rede_topologia,
    # --- geocodificador (L2-11-b): /api/geocodificar, /api/reverso, /api/sugerir + GeocodeServer compatível
    # Esri em /rest/services/Geocodificador/GeocodeServer/*, sobre o CNEFE 2022 do IBGE instalado por UF
    rotas_geocodificador,
    rotas_geocodificador_esri,
    # --- catálogo de imagens STAC por inquilino (L1-01-a): /svc/<token>/stac/*, token de serviço no PATH
    # (pgstac + convenção de nome de coleção `<tenant_id>-<slug>`; plat.raster_item com RLS)
    rotas_imagens,
    rotas_stac,
    # --- ladrilho raster por token no caminho (L1-02): /svc/<token>/raster/<item>/{z}/{x}/{y}, WMTS,
    # TileJSON e mosaico por coleção; motor rio-tiler lendo COG no Garage por /vsis3
    rotas_tiles,
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
    # --- casca do SIG (L2-01-a-casca-sig): GET /api/publico/wms/{fonte} — proxy WMS público sem sessão,
    # allowlist fixa em app/settings.py (geosampa, ibge, inde)
    rotas_mapa_wms_publico,
    # --- tiles vetoriais (L2-01-b): /internal/tiles/verificar (auth_request do nginx antes do Martin)
    rotas_tiles_martin_verificar,
    # --- motor multicritério, grades aninhadas (L3-19-multiescala): /api/multiescala/conjuntos, /fatores,
    # /fatores/{id}/amostras, /conjuntos/{id}/macro, /execucoes/{id}/micro, /execucoes
    rotas_multiescala,
    # --- visualizador de mapa (L2-01-mapa-web): /api/mapa/camadas, TileJSON com token curto, repasse /tiles
    rotas_mapa,
    # --- seleção e filtro (L2-01-h): /valores, /filtrar (CQL2-JSON), /selecionar, /selecao-espacial
    rotas_selecao,
    # --- tiles vetoriais (L2-01-b): /internal/tiles/verificar (auth_request do nginx antes do Martin)
    rotas_tiles,
    # --- motor multicritério, grades aninhadas (L3-19-multiescala): /api/multiescala/conjuntos, /fatores,
    # /fatores/{id}/amostras, /conjuntos/{id}/macro, /execucoes/{id}/micro, /execucoes
    rotas_multiescala,
    # --- migração de Portal/AGOL (L2-08-a): /api/migracao/inventarios (leitura só-leitura do portal do cliente)
    rotas_migracao,
    # --- motor multicritério, grades aninhadas (L3-19-multiescala): /api/multiescala/conjuntos, /fatores,
    # /fatores/{id}/amostras, /conjuntos/{id}/macro, /execucoes/{id}/micro, /execucoes
    rotas_multiescala,
    # --- operação query do FeatureServer (L2-04-c): /rest/services/{item}/FeatureServer/{camada}/query
    # --- diretório/metadados do FeatureServer + OGC API Features Part 1 + WFS 2.0 (item
    # L2-04-servicos-esri-ogc, construído EM VOLTA da query acima, sem reescrevê-la): descritor de
    # serviço/camada (`?f=json`), `/ogc/features/{item}` e `/wfs/{item}`. applyEdits/attachments/
    # relationships ficam de fora (dependem de L2-03-edicao e L2-10-b, nenhum construído).
    rotas_consulta_esri,
    # --- escrita compatível Esri (L2-04-d): applyEdits/addFeatures/updateFeatures/deleteFeatures, calculate,
    # anexos e uploads sobre a MESMA porta de escrita do L2-03-a
    rotas_edicao_esri,
    # --- sincronização de réplica no protocolo Esri (L2-04-k): createReplica/synchronizeReplica/
    # extractChanges/replicas/unRegisterReplica sobre o mecanismo de réplica do L2-13-b
    rotas_sync_esri,
    rotas_consulta_servico,
    # --- diretório de serviços Esri por token (L2-04-b): /svc/{token}/rest/info|generateToken|services
    rotas_diretorio_esri,
    # --- MapServer e GeometryServer compatíveis com Esri (L2-04-f), sob o MESMO diretório por token:
    # export/identify/legend/find/generateKml por mapa do catálogo e as operações de geometria sobre PostGIS
    rotas_mapserver_esri,
    rotas_geometry_server,
    rotas_ogc_features,
    rotas_wfs,
    # --- escrita compatível Esri (L2-04-d): applyEdits/addFeatures/updateFeatures/deleteFeatures, calculate,
    # anexos e uploads sobre a MESMA porta de escrita do L2-03-a
    rotas_edicao_esri,
    # --- motor de análise multicritério (L3-01-a): /api/amc/modelos, /api/amc/conjuntos, /api/amc/execucoes
    rotas_amc.router,
    rotas_tiles_exportacao,
    rotas_tiles,
    # --- tabela de atributos da camada (L2-01-g): /api/camadas/{item_id}/tabela/{colunas,vista,linhas,estatisticas}
    rotas_tabela,
    # --- desenho e anotações do mapa (L2-01-k): /api/mapa/{id}/desenho/promover, /api/anotacoes
    rotas_promover,
    rotas_anotacoes,
    # --- popup em tempo de execução (L2-01-d): /api/camadas/{id}/feicoes/{fid}/popup (campos servidor + expressão)
    rotas_mapa_popup,
    # --- seleção e filtro (L2-01-h): /valores, /filtrar (CQL2-JSON), /selecionar, /selecao-espacial
    rotas_selecao,
    # --- exportação a partir do mapa (L2-01-l): cópia de feição, estilo (MapLibre/SLD) e import de pacote
    rotas_exportar_mapa,
    # --- tiles vetoriais (L2-01-b): /internal/tiles/verificar (auth_request do nginx antes do Martin)
    # --- QR local para o widget compartilhar (L5-01-d)
    rotas_qr.router,
    # --- agregação estatística (L2-06-e): POST /api/camadas/{id}/estatisticas
    rotas_estatistica,
    # --- gráficos por camada (L2-01-i): POST /api/camadas/{id}/grafico
    rotas_graficos,
    # --- widgets externos por inquilino (L5-36-widgets-personalizados-sdk): /api/widgets/externos instala
    # (admin, org.configurar), lista e serve o módulo same-origin com sha256 — o SDK do parceiro carrega daqui
    rotas_widgets_externos,
    # --- catálogo de imagens STAC por inquilino (L1-01-a): /svc/<token>/stac/*, token de serviço no PATH
    # (pgstac + convenção de nome de coleção `<tenant_id>-<slug>`; plat.raster_item com RLS)
    rotas_stac,
    # --- imagens por sessão (L1-01, ciclo de vida): GET /api/imagens/{id} (painel do raster) e
    # /api/imagens/{id}/tiles/{z}/{x}/{y}.png — as URLs que o Conteúdo e o mapa consomem com cookie;
    # a exclusão na lixeira esconde o item pela RLS e os tiles passam a responder 404 (cláusula L1-01-i)
    rotas_imagens,
    # --- análise 3D (L2-09-d): /api/analise3d/visada, /viewshed, /perfil, /sombra sobre terreno inline
    rotas_analise3d,
    # --- relatórios do admin e painel Atividade (L0-07-e-relatorios): /api/relatorios, /api/atividade
    rotas_relatorios,
    # --- motor multicritério, fronteira de Pareto (L3-08-pareto): /api/amc/pareto e /api/amc/pareto/camada
    rotas_amc_pareto,
    # --- temas de marca (L5-10): GET /api/temas (padrões + tema do inquilino); PUT /api/org/tema
    rotas_temas,
    # --- catálogo de imagens STAC por inquilino (L1-01-a): /svc/<token>/stac/*, token de serviço no PATH
    # (pgstac + convenção de nome de coleção `<tenant_id>-<slug>`; plat.raster_item com RLS)
    rotas_stac,
    # --- ladrilho raster por token no caminho (L1-02): /svc/<token>/raster/<item>/{z}/{x}/{y}, WMTS,
    # TileJSON e mosaico por coleção; motor rio-tiler lendo COG no Garage por /vsis3
    rotas_tiles,
    # --- geocodificação de tabela (L2-11-a): /api/geocodificacoes (mapear colunas -> lote ->
    # camada de pontos com colunas de qualidade -> revisão manual do que ficou pendente)
    rotas_geocodificacao_lote,
    # --- vídeos por tarefa (L7-04-d): /api/videos (manifesto) e /videos/arquivo/{caminho}
    rotas_videos,
    # --- geocodificação de tabela (L2-11-a): /api/geocodificador/lote/* — a criação em si é POST /api/jobs
    # (tipo geocodificador.lote_csv); aqui só a tela de revisão (pendentes, arrasto manual, re-geocodificar)
    rotas_geocodificador_lote,
    # --- motor multicritério, grades aninhadas (L3-19-multiescala): /api/multiescala/conjuntos, /fatores,
    # /fatores/{id}/amostras, /conjuntos/{id}/macro, /execucoes/{id}/micro, /execucoes
    rotas_multiescala,
    # --- portal de API (L7-08-d): /portal (página, CSP própria) e /api/portal/exemplos
    rotas_portal,
    # --- migração de Portal/AGOL (L2-08-a): /api/migracao/inventarios (leitura só-leitura do portal do cliente)
    rotas_migracao,
    # --- sistema de referência (L2-17-crs-transformacoes): /api/crs (lista, detalhe, proj4, transformar);
    # grades NTv2 do IBGE em grades_ibge/, escolhidas por área (app/crs/grades.py)
    rotas_crs,
    rotas_regioes.router,
    # --- páginas (cada trilha acrescenta a sua em app/paginas.py)
    paginas.router,
]
for _router in ROUTERS:
    app.include_router(_router)

# item L7-08-d: `x-plat-escopo` em toda operação, derivado da dependência de autenticação da própria rota
# (app/portal/openapi.py explica por que derivado e não declarado à mão). Tem de vir DEPOIS do include_router.
portal_openapi.instalar(app)

# /static/ é do nginx em produção (ADR 0001 seção 4.3) e assim continua. PLAT_SERVIR_ESTATICO=1 monta o
# diretório na própria aplicação para o caso em que não há nginx na frente: o e2e de uma trilha do laço sobe
# só o uvicorn numa porta sua, e sem isto toda folha e todo módulo da página dariam 404 no navegador (achado
# do 1º turno, registrado em scripts/homolog_e2e.sh, que resolveu o mesmo problema pondo um nginx no meio).
# Recusado em produção mesmo que a variável apareça: lá o nginx é a origem do estático e do Cache-Control.
if os.environ.get("PLAT_SERVIR_ESTATICO") == "1" and not settings.producao:
    app.mount("/static", StaticFiles(directory=WEB), name="estatico")


# /static/ é do nginx em produção (ADR 0001 seção 4.3) e assim continua. PLAT_SERVIR_ESTATICO=1 monta o
# diretório na própria aplicação para o caso em que não há nginx na frente: o e2e de uma trilha do laço sobe
# só o uvicorn numa porta sua, e sem isto toda folha e todo módulo da página dariam 404 no navegador (achado
# do 1º turno, registrado em scripts/homolog_e2e.sh, que resolveu o mesmo problema pondo um nginx no meio).
# Recusado em produção mesmo que a variável apareça: lá o nginx é a origem do estático e do Cache-Control.
if os.environ.get("PLAT_SERVIR_ESTATICO") == "1" and not settings.producao:
    app.mount("/static", StaticFiles(directory=WEB), name="estatico")


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


if not settings.producao:
    # Fora de produção (trilha de teste, servidor local sem nginx) não há quem sirva /static: o motor de render
    # (L2-12-a/L2-12-b) e a página headless do quadro precisam de /static respondendo para carregar MapLibre,
    # pmtiles e estilo.js. Guardado por `settings.producao`: zero mudança em produção, onde o nginx serve web/.
    from fastapi.staticfiles import StaticFiles

    if not any(getattr(r, "name", "") == "static" for r in app.routes):
        app.mount("/static", StaticFiles(directory=str(WEB)), name="static_dev")


@app.on_event("shutdown")
async def _fechar_motor_render():
    """O pool de chromium (L2-12-a) nasce só no primeiro render; quando nasceu, fecha aqui para não vazar processo."""
@app.on_event("shutdown")
async def _fechar_motor_render():
    """O pool de chromium (L2-12-a-motor-render-servidor) nasce SÓ no primeiro `POST /api/render/mapa` (nunca
    no startup — a suíte inteira sobe esta app centenas de vezes por sessão de teste, e um chromium por
    instância derrubaria a máquina). Quando ele nasceu, fecha aqui para não vazar processo do navegador."""
    from app.render.motor import motor

    m = motor()
    if m.ativo:
        await m.parar()
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
