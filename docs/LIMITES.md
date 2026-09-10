# Limites da plataforma

Gerado de `app/limites.py` por `docs/gerar_limites.py` (`make limites`); não editar à mão — `tests/unit/test_limites_doc.py` falha se este arquivo divergir do código, e a coluna "valor" é o `repr()` do que o Python leu do módulo, nunca um número digitado de novo (ADR 0001 seção 12, regra 1). O comentário ao lado da constante no código é a explicação, quando houver.


## identidade (L0-02)

| nome | valor | explicação |
|---|---|---|
| `AUTH_PADROES` | *(dicionário; ver subtabela abaixo)* | — |
| `SENHA_MAX` | `128` | fixo: pbkdf2 sobre 128 bytes evita DoS por senha longa |
| `SENHA_EXPIRA_MIN_DIAS` | `30` | — |
| `BLOQUEIO_JANELA_MIN` | `15` | fixo (ADR 0002 seção 6.2) |
| `DESAFIO_2FA_MIN` | `5` | — |
| `TOTP_JANELA_PASSOS` | `1` | — |
| `CODIGOS_RECUPERACAO` | `8` | — |
| `SENHA_TEMPORARIA_TAMANHO` | `12` | — |
| `TOKENS_POR_USUARIO` | `20` | — |
| `GRUPOS_POR_USUARIO` | `512` | — |
| `GRUPO_TAGS_MAX` | `50` | — |
| `GRUPO_NOME_MAX` | `128` | — |
| `GRUPO_RESUMO_MAX` | `2048` | — |
| `PAPEL_NOME_MAX` | `128` | — |
| `PAPEL_DESCRICAO_MAX` | `250` | — |
| `LOTE_MAX` | `100` | — |
| `LOG_JANELA_DIAS` | `92` | — |
| `LOG_LIMITE_MAX` | `1000` | — |
| `LOG_CSV_MAX` | `100000` | — |
| `LOG_RETENCAO_MESES` | `12` | — |
| `PAGINA_PADRAO` | `50` | — |
| `PAGINA_MAX` | `1000` | — |
| `RESTRICAO_MAX` | `20` | — |
| `TOKEN_ROTACAO_HORAS` | `24` | — |

### `AUTH_PADROES`

| chave | padrão | mínimo | máximo |
|---|---|---|---|
| `senha_min` | `8` | `8` | `64` |
| `senha_maiuscula` | `False` | `None` | `None` |
| `senha_minuscula` | `False` | `None` | `None` |
| `senha_simbolo` | `False` | `None` | `None` |
| `senha_historico` | `5` | `0` | `24` |
| `senha_expira_dias` | `0` | `0` | `365` |
| `bloqueio_tentativas` | `5` | `3` | `10` |
| `bloqueio_minutos` | `15` | `5` | `60` |
| `sessao_ociosa_horas` | `12` | `1` | `24` |
| `sessao_max_dias` | `7` | `1` | `30` |
| `exigir_2fa` | `False` | `None` | `None` |
| `token_max_dias` | `365` | `1` | `365` |
| `token_padrao_dias` | `90` | `1` | `365` |
| `dominios_email` | `[]` | `0` | `20` |
| `compartilhar_publico` | `False` | `None` | `None` |

## catálogo (L0-03; ADR 0004 seção 14)

| nome | valor | explicação |
|---|---|---|
| `ITEM_TITULO_MAX` | `250` | — |
| `ITEM_RESUMO_MAX` | `2048` | snippet da Esri, limite literal |
| `ITEM_DESCRICAO_MAX` | `65536` | — |
| `ITEM_CREDITOS_MAX` | `2048` | — |
| `ITEM_TAGS_MAX` | `50` | — |
| `TAG_MAX` | `128` | — |
| `ITEM_CATEGORIAS_MAX` | `20` | — |
| `CATEGORIAS_POR_INQUILINO` | `(200, 50, 900)` | (padrão, mínimo, máximo) em tenant.config.catalogo.categorias_max |
| `CATEGORIA_NIVEIS` | `3` | — |
| `CATEGORIA_NOME_MAX` | `100` | — |
| `PASTA_PROFUNDIDADE_MAX` | `5` | — |
| `PASTA_NOME_MAX` | `128` | — |
| `MINIATURA_BYTES_MAX` | `10485760` | — |
| `MINIATURA_PIXELS_MAX` | `25000000` | — |
| `MINIATURA_LARGURA` | `600` | — |
| `MINIATURA_ALTURA` | `400` | — |
| `LINKS_POR_ITEM` | `100` | — |
| `LINK_VALIDADE_MAX_DIAS` | `365` | — |
| `LINK_TOKEN_BYTES` | `32` | 64 hex |
| `RELACOES_POR_ORIGEM` | `5000` | — |
| `RELACOES_POR_DESTINO` | `50000` | — |
| `RELACAO_PROFUNDIDADE_MAX` | `20` | — |
| `VERSOES_VIVAS` | `50` | — |
| `VERSOES_BLOCO_COMPACTACAO` | `10` | — |
| `VERSAO_COMENTARIO_MAX` | `500` | — |
| `FAVORITOS_POR_USUARIO` | `500` | — |
| `DESTAQUES_POR_GRUPO` | `24` | — |
| `BUSCA_Q_MAX` | `1000` | — |
| `BUSCA_TERMOS_MAX` | `200` | — |
| `BUSCA_TRGM_LIMIAR` | `0.3` | — |
| `BUSCA_REFORCO_STATUS` | `0.25` | — |
| `ITENS_PAGINA_MAX` | `200` | — |
| `ITENS_DESLOCAMENTO_MAX` | `10000` | — |
| `LIXEIRA_DIAS` | `30` | — |
| `COTA_ITENS` | `100000` | padrão por inquilino, tenant.config.catalogo.cota_itens |
| `USADO_POR_PROFUNDIDADE_MAX` | `5` | — |

## contrato de API e limites transversais (L0-12; docs/CONTRATO_API.md e docs/LIMITES.md nascem daqui)

| nome | valor | explicação |
|---|---|---|
| `CORPO_MAX_PADRAO_BYTES` | `10485760` | 10 MiB; toda rota /api,/svc,/ogc,/tiles fora da lista de upload |
| `CORPO_MAX_UPLOAD_BYTES` | `2147483648` | 2 GiB (hipótese do item); sem rota isenta ainda (upload = L1-01-e) |

## arquivos/objetos (L0-11; ADR 0006). PLAT_ARQUIVO_BYTES_MAX bem abaixo de CORPO_MAX_UPLOAD_BYTES de propósito:

| nome | valor | explicação |
|---|---|---|
| `ARQUIVO_BYTES_MAX` | `536870912` | — |
| `ARQUIVO_PARTE_BYTES` | `8388608` | 8 MiB por parte S3 (mínimo do protocolo é 5 MiB, exceto a última) |
| `ARQUIVO_BUFFER_UNICO_BYTES` | `8388608` | até aqui: 1 PUT só, sem abrir multipart |

## upload retomável (L0-04-a-upload-arquivo; ADR 0005 seção 3): parte de 16 MiB fixa (não cresce com o

| nome | valor | explicação |
|---|---|---|
| `UPLOAD_BYTES_MAX` | `2147483648` | 2 GiB |
| `UPLOAD_PARTE_BYTES` | `16777216` | 16 MiB (ADR 0005 seção 3.1; distinto de ARQUIVO_PARTE_BYTES acima, |
| `UPLOAD_EXPIRA_HORAS` | `24` | — |
| `UPLOAD_NOME_MAX` | `255` | — |

## rede de rota (L2-11-c): OSRM isolado `plat-osrm-guarulhos` (:5010; recorte de teste ≤ 50 MB — nunca os

| nome | valor | explicação |
|---|---|---|
| `ROTA_MATRIZ_MAX_PADRAO` | `625` | N×M <= isto por pedido de /api/matriz |
| `ROTA_ISOCRONA_MAX_PONTOS_PADRAO` | `400` | pontos de grade por pedido de /api/isocrona (1 fonte + N destinos) |
| `ROTA_PERFIS` | `('carro',)` | só car.lua está carregado nesta instância de teste (D-osrm-perfis) |
| `ROTA_MINUTOS_MAX` | `180` | 3 h; acima disso o polígono satura no limite do recorte de teste |
| `ROTA_ISOCRONA_RATIO_PADRAO` | `0.3` | parâmetro do casco côncavo (shapely.concave_hull); 0 = casco convexo |

## LDAP/Active Directory (L0-08-d; app/auth/ldap.py): provedor externo por inquilino, sem servidor de

| nome | valor | explicação |
|---|---|---|
| `LDAP_TIMEOUT_S` | `5` | connect_timeout e receive_timeout do ldap3 (bind de serviço e bind do usuário) |
| `LDAP_BUSCA_MAX` | `1` | a busca por login casa EXATAMENTE 1 entrada; 0 ou 2+ = credenciais inválidas |
| `LDAP_IMPORTAR_MAX` | `2000` | tamanho máximo de uma importação de grupo em massa (POST /api/org/ldap/importar) |

## conexão externa e SSRF (L6-02-a-modelo-conexao-e-seguranca; app/conexao/): modelo genérico de conexão

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_TIPOS` | `('wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'postgres_fdw', 's3', 'http')` | — |
| `CONEXAO_MODOS` | `('referenciada', 'copiada')` | — |
| `CONEXAO_NOME_MAX` | `200` | — |
| `CONEXAO_URL_MAX` | `2048` | — |
| `CONEXAO_CONFIG_MAX_BYTES` | `8192` | tamanho máximo do JSON de `config` (json.dumps, utf-8) |
| `CONEXAO_DNS_TIMEOUT_S` | `3.0` | socket.getaddrinfo (validação do host antes de qualquer conexão) |
| `CONEXAO_CONECTAR_TIMEOUT_S` | `3.0` | — |
| `CONEXAO_LER_TIMEOUT_S` | `6.0` | teste de saúde: curto de propósito (POST /api/conexoes/{id}/testar) |
| `CONEXAO_REDIRECT_MAX` | `5` | cada hop é revalidado do zero (host novo pode ser interno) |
| `CONEXAO_RESPOSTA_MAX_BYTES` | `1048576` | 1 MiB: o teste de saúde confere status/corpo curto |

## descoberta de camada (item L6-02-conectores-vivos; app/conexao/descoberta.py): GetCapabilities de um

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_DESCOBERTA_MAX_BYTES` | `25165824` | 24 MiB |
| `CONEXAO_DESCOBERTA_TIMEOUT_S` | `15.0` | — |
| `CONEXAO_DESCOBERTA_CAMADAS_MAX` | `2000` | teto de linhas gravadas por descoberta (corta, não trava) |

## proxy de tile/imagem por conexão cadastrada (mesmo item): generaliza `app/mapa/proxy_wms.py` (allowlist

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_PROXY_TIPOS` | `('wms', 'wmts', 'esri_rest')` | — |
| `CONEXAO_PROXY_CONECTAR_TIMEOUT_S` | `3.0` | — |
| `CONEXAO_PROXY_LER_TIMEOUT_S` | `20.0` | uma base pública lenta não pode travar o mapa de quem espera |
| `CONEXAO_PROXY_MAX_BYTES` | `12582912` | 12 MiB: teto de 1 tile/imagem (ortofoto 10-20 cm inclusa) |
| `CONEXAO_PROXY_CACHE_TTL_S` | `600` | mesmos 10 min do proxy público de hoje |
| `CONEXAO_PROXY_CACHE_MAX_ITENS` | `500` | cache em processo; LRU simples por ordem de inserção |

## ingestão vetorial (L0-04; ADR 0005, reduzido a 4 formatos: shapefile.zip, gpkg, geojson, csv)

| nome | valor | explicação |
|---|---|---|
| `INGESTAO_AMOSTRA_VALIDADE` | `1000` | feições lidas na amostra de ST_IsValid (ogr2ogr -limit, MEDIDO no ADR) |
| `INGESTAO_MEMORIA_MB` | `768` | job ingestao.inspecionar (cobre GeoJSON de 64 MiB, ADR seção 0.4) |
| `INGESTAO_TIMEOUT_S` | `300` | — |
| `CARGA_MEMORIA_MB` | `1024` | job ingestao.carregar (ogr2ogr + ST_MakeValid) |
| `CARGA_TIMEOUT_S` | `3600` | — |
| `CARGA_FATOR_COTA` | `3` | estimativa = bytes do arquivo × 3 (MEDIDO: shapefile 14 MB -> tabela 45 MB) |
| `INGESTAO_CAMPOS_MAX` | `500` | mesmo teto do JSON Schema de camada_vetorial (ADR 0004/0005) |
| `INGESTAO_FIDS_RELATORIO_MAX` | `1000` | fids corrigidos listados no relatório de ST_MakeValid |

## configurações da organização (L0-07-a-configuracoes-org; GET/PUT /api/org): nome, identidade visual

| nome | valor | explicação |
|---|---|---|
| `ORG_NOME_MAX` | `55` | mesmo teto do "Organization name" da Esri (portão do item-pai L0-07-a) |
| `ORG_COR_PADRAO` | `'#2463a8'` | mesmo azul de app/catalogo/miniatura.py TRACO, cor de marca padrão |
| `ORG_IDIOMAS` | `('pt-BR',)` | só o que existe em web/js/i18n/; L7-10 acrescenta idioma novo aqui |
| `ORG_ZOOM_MAX` | `24` | teto de zoom de um webmap (padrão MapLibre/Leaflet) |
| `ORG_BASEMAP_MAX` | `100` | — |
| `ORG_LOGO_BYTES_MAX` | `1048576` | 1 MiB (portão do item-pai: "logo > 1 MB recusado") |
| `ORG_LOGO_PIXELS_MAX` | `25000000` | mesma defesa de bomba de descompressão de app/catalogo/miniatura.py |
| `ORG_LOGO_LADO` | `300` | canvas quadrado 300×300 (portão do item-pai) |
| `ORG_COTA_BYTES_MIN` | `104857600` | 100 MiB: abaixo disso o próprio inquilino de demonstração não sobe |
| `ORG_COTA_USUARIOS_MIN` | `1` | — |
| `ORG_COTA_USUARIOS_PADRAO` | `2000` | bem acima do maior lote (LOTE_MAX=100) e do uso medido em demo (T3: 59) |

## perfil próprio do usuário (L0-02-g-perfil-usuario; POST/PUT /api/eu, app/auth/rotas_eu.py): idioma,

| nome | valor | explicação |
|---|---|---|
| `PERFIL_IDIOMAS` | `('pt-BR', 'en', 'es')` | — |
| `PERFIL_UNIDADES` | `('metrico', 'imperial')` | — |
| `PERFIL_FORMATOS_DATA` | `('dd/mm/aaaa', 'mm/dd/aaaa', 'aaaa-mm-dd')` | — |
| `PERFIL_VISIBILIDADES` | `('privado', 'inquilino')` | — |
| `PERFIL_FOTO_BYTES_MAX` | `1048576` | 1 MiB (portão do item: "foto > 1 MB recusada") |
| `PERFIL_FOTO_PIXELS_MAX` | `25000000` | mesma defesa de bomba de descompressão do org_logo/miniatura |
| `PERFIL_FOTO_LADO` | `200` | canvas quadrado 200×200 (hipótese do item) |

## SMTP, convite de membro e redefinição de senha por e-mail (L0-07-d-smtp-convites; privilégio

| nome | valor | explicação |
|---|---|---|
| `SMTP_HOST_MAX` | `255` | — |
| `SMTP_USUARIO_MAX` | `255` | — |
| `SMTP_SENHA_MAX` | `1024` | antes de cifrar; a cifra em si (AES-GCM) é maior no banco |
| `SMTP_REMETENTE_MAX` | `255` | — |
| `SMTP_ROTULO_MAX` | `100` | — |
| `SMTP_PORTA_MIN` | `1` | — |
| `SMTP_PORTA_MAX` | `65535` | — |
| `SMTP_CONECTAR_TIMEOUT_S` | `6.0` | teste de envio: curto de propósito, nunca prende a requisição |
| `SMTP_ENVIAR_TIMEOUT_S` | `15.0` | dentro do job (worker), pode ser mais folgado que o teste síncrono |
| `SMTP_ASSUNTO_MAX` | `200` | — |
| `SMTP_TEXTO_MAX` | `20000` | — |
| `CONVITE_VALIDADE_DIAS` | `7` | portão do item: link após 7 dias = 410 |
| `CONVITE_LOGIN_MAX` | `128` | — |
| `CONVITE_NOME_MAX` | `128` | — |
| `CONVITE_LISTA_MAX` | `200` | — |
| `REDEFINICAO_VALIDADE_HORAS` | `1` | portão do item-pai (ADR 0002 seção 6.3): token de 1 hora |
| `REDEFINICAO_JANELA_MIN` | `15` | limite de taxa (refutação do item: 1.000 pedidos/min p/ o mesmo e-mail) |
| `REDEFINICAO_MAX_JANELA` | `5` | no máximo 5 pedidos por (inquilino, e-mail) a cada REDEFINICAO_JANELA_MIN |
| `AVISO_EXPIRACAO_DIAS` | `(90, 30, 7, 1)` | avisos de expiração de token de serviço (hipótese do item; como a Esri) |

## imagens/STAC (L1-01-a-pgstac-e-stac-api-por-inquilino; app/imagens/): catálogo é o pgstac (schema

| nome | valor | explicação |
|---|---|---|
| `STAC_SLUG_MAX` | `58` | — |
| `STAC_ITEM_ID_MAX` | `256` | — |
| `STAC_PAGINA_PADRAO` | `10` | `limit` padrão da busca (mesmo padrão da spec STAC API Item Search) |
| `STAC_PAGINA_MAX` | `1000` | `limit` máximo aceito por pedido (pgstac pagina por token, não por offset) |
| `STAC_COLECOES_POR_INQUILINO` | `500` | — |
| `STAC_LOTE_ITENS_MAX` | `10000` | POST .../items:lote (semeadura de teste/ingestão em massa; ADR do item L1-01-h) |

## ingestão de raster (L1-01-ingest-raster; ADR 20260906T2127): validação isolada + COG dois perfis +

| nome | valor | explicação |
|---|---|---|
| `RASTER_DIMENSAO_MAX` | `200000` | pixels por eixo (linhas ou colunas) — acima: recusa na validação |
| `RASTER_BANDAS_MAX` | `64` | bandas por raster — acima: recusa na validação |
| `RASTER_BYTES_MAX` | `2147483648` | bruto aceito para ingestão (igual a UPLOAD_BYTES_MAX) |
| `RASTER_VISUAL_MAX_LADO` | `1024` | miniatura PNG (lado maior) |
| `RASTER_ESTATISTICA_AMOSTRA` | `100000` | pixels amostrados por banda para percentis do perfil visual |
| `RASTER_TILE_CACHE_DATASET_MAX` | `8` | datasets abertos por processo no handler de tiles (LRU) |
| `RASTER_TILE_TIMEOUT_S` | `30` | teto de renderização de um tile (mata a requisição, não o worker) |

## COG direto por HTTPS (L1-02-e): uma requisição Range é mantida pequena para que clientes analíticos

| nome | valor | explicação |
|---|---|---|
| `COG_FAIXA_MAX_BYTES` | `16777216` | 16 MiB por Range; GDAL/QGIS normalmente pede blocos muito menores |

## WMS 1.3.0 (L1-02-g-wms-1-3-0-raster; app/imagens/wms.py, rotas_wms.py): camada fina sobre o mesmo

| nome | valor | explicação |
|---|---|---|
| `WMS_LARGURA_MAX` | `4096` | WIDTH máximo aceito no GetMap — acima: ServiceExceptionReport |
| `WMS_ALTURA_MAX` | `4096` | HEIGHT máximo aceito no GetMap — acima: ServiceExceptionReport |
| `WMS_PIXELS_MAX` | `16777216` | teto de WIDTH×HEIGHT (é o que de fato protege a memória) |
| `WMS_CAMADAS_MAX` | `500` | <Layer> por GetCapabilities (itens além disso não aparecem) |
| `WMS_TIMEOUT_S` | `30` | teto de renderização de um GetMap (mesma ordem do tile) |

## ImageServer compatível Esri (L1-25-servico-de-imagem-esri-compativel; app/imagens/rotas_imageserver.py):

| nome | valor | explicação |
|---|---|---|
| `IMAGESERVER_EXPORT_LADO_MAX` | `4096` | largura/altura máximas aceitas no exportImage, em pixels |
| `IMAGESERVER_EXPORT_LADO_PADRAO` | `400` | tamanho quando `size` não vem — mesmo default do ArcGIS Server |

## ingestão de modelo 3D (L1-03-modelo3d, 10/09/2026): IFC bruto enviado pelo usuário antes da conversão

| nome | valor | explicação |
|---|---|---|
| `MODELO3D_IFC_BYTES_MAX` | `536870912` | — |
| `MODELO3D_XKT_BYTES_MAX` | `536870912` | — |
| `MODELO3D_CONVERSAO_TIMEOUT_S` | `1500` | teto do ssh+scp+convert2xkt no conversor remoto (job todo tem mais margem) |
| `FOTO360_BYTES_MAX` | `67108864` | — |
| `MODELO3D_URL_VALIDADE_S` | `3600` | validade da URL assinada do .xkt/.jpg entregue ao visualizador |

## grades aninhadas do motor multicritério (L3-19-multiescala; migração 20260906T1640_multiescala.sql):

| nome | valor | explicação |
|---|---|---|
| `ESCALA_AREA_VERTICES_MAX` | `5000` | vértices do polígono de estudo (mesma ordem de grandeza de INGESTAO_*) |
| `ESCALA_RESOLUCAO_MIN_M` | `1.0` | — |
| `ESCALA_RESOLUCAO_MAX_M` | `100000.0` | — |
| `ESCALA_CELULAS_MAX` | `250000` | — |
| `ESCALA_FATORES_MAX` | `20` | — |
| `ESCALA_LIGACOES_MAX` | `2000000` | — |
| `ESCALA_APROVACAO_TIPOS` | `('limiar', 'top_pct')` | — |
| `ESCALA_NOME_MAX` | `200` | mesmo teto de CHECK(length(nome)<=200) da migração |
| `ESCALA_UNIDADE_MAX` | `40` | CHECK(length(unidade)<=40) |
| `ESCALA_FONTE_MAX` | `500` | CHECK(length(fonte)<=500) |
| `ESCALA_AMOSTRAS_LOTE_MAX` | `20000` | amostras de fator por chamada de POST (streaming não é o item; teto direto) |

## edição transacional de feições (L2-03-a-api-edicao-transacional; POST /api/camadas/{id}/edicoes, única

| nome | valor | explicação |
|---|---|---|
| `EDICAO_LOTE_MAX` | `2000` | — |
| `EDICAO_ATRIBUTOS_MAX` | `500` | campos por feição num único pedido (mesmo teto de INGESTAO_CAMPOS_MAX) |
| `EDICAO_TEXTO_MAX` | `65536` | 64 KiB por valor de campo texto (mesma ordem de ITEM_DESCRICAO_MAX) |
| `EDICAO_REGRA_CAMPO_MAX` | `500` | entradas em dados.regras_campo (mesmo teto de campos da camada) |
| `EDICAO_DOMINIO_VALORES_MAX` | `1000` | valores aceitos por regra de domínio codificado |
| `EDICAO_SRID_MAX` | `999999` | mesmo teto do esquema de camada_vetorial (029_ingestao_vetor.sql) |

## edição no mapa: histórico/restauração e anexos por feição (item L2-03-edicao)

| nome | valor | explicação |
|---|---|---|
| `HISTORICO_LISTA_MAX` | `500` | entradas devolvidas por consulta (mais recentes primeiro) |
| `ANEXO_TAMANHO_MAX` | `7340032` | 7 MiB por anexo — NÃO 10: o envio é JSON com o conteúdo em base64 |
| `ANEXO_TIPOS_PERMITIDOS` | `('application/pdf', 'image/gif', 'image/jpeg', 'image/png', 'image/webp')` | — |

## motor multicritério, modelo (L3-01-a-modelo-dado; laco/decomposicao/L3L6_CONCEITO.md decisões A1/A4/A10).

| nome | valor | explicação |
|---|---|---|
| `AMC_NOME_MAX` | `250` | mesmo teto de ITEM_TITULO_MAX |
| `AMC_FATORES_MAX` | `50` | mesmo teto de docs/esquemas/amc_modelo.v1.json fatores.maxItems |
| `AMC_CAMADAS_MAX` | `50` | camadas de entrada declaradas por execução (A10) |

## integração ArcGIS Online do cliente (item L2-08-migracao-agol): credencial por inquilino em

| nome | valor | explicação |
|---|---|---|
| `AGOL_PORTAL_MAX` | `300` | — |
| `AGOL_USUARIO_MAX` | `128` | — |
| `AGOL_CREDENCIAL_MAX` | `1024` | senha ou token, antes de cifrar |
| `AGOL_ROTULO_MAX` | `100` | — |
| `AGOL_TITULO_MAX` | `250` | — |
| `AGOL_CONECTAR_TIMEOUT_S` | `6.0` | — |
| `AGOL_LER_TIMEOUT_S` | `20.0` | teste de credencial: curto de propósito (rota síncrona) |
| `AGOL_PUBLICAR_TIMEOUT_S` | `300.0` | addItem/publish dentro do job: upload pode ser grande |
| `AGOL_POLL_INTERVALO_S` | `4.0` | espera do job assíncrono de publish (mesmo valor do script original) |
| `AGOL_POLL_TENTATIVAS_MAX` | `90` | 90 x 4 s = 6 min (mesmo teto do script original: `for _ in range(90)`) |
| `AGOL_FEICOES_MAX` | `200000` | teto de segurança do export GeoJSON (fetchall bounded; camada maior |

## campo: fila de trabalho, roteiro e visita com foto (item L2-07-campo), portado de rs-coop/certaja/sig

| nome | valor | explicação |
|---|---|---|
| `CAMPO_FILA_ALVOS_MAX` | `5000` | feições por fila (mesma ordem de grandeza de EDICAO_LOTE_MAX x2) |
| `CAMPO_ROTEIRO_PARADAS_MAX` | `60` | mesmo teto do sistema de origem ("no máximo 60 paradas por rota") |
| `CAMPO_FOTO_BYTES_MAX` | `10485760` | mesmo teto de MINIATURA_BYTES_MAX; a foto é reamostrada abaixo disso |
| `CAMPO_FOTO_PIXELS_MAX` | `40000000` | contra bomba de descompressão (mesma técnica de MINIATURA_PIXELS_MAX) |
| `CAMPO_FOTO_LADO_MAX` | `2400` | px do maior lado após redimensionar (mesmo valor do sistema de origem) |
| `CAMPO_ROTA_VELOCIDADE_KMH` | `35` | estimativa de fallback (linha reta) quando não há motor de rota real; |

## backup lógico por inquilino e ensaio de restauração (item L0-06-backup-status; app/backup/), portado de

| nome | valor | explicação |
|---|---|---|
| `BACKUP_DUMP_BYTES_MAX` | `2147483648` | 2 GiB |
| `BACKUP_DUMP_TIMEOUT_S` | `3600` | pg_dump -Fc do schema do inquilino |
| `BACKUP_DRILL_TIMEOUT_S` | `3600` | download + pg_restore em schema temporário + COUNT(*) |
| `BACKUP_LISTA_MAX` | `200` | linhas por página em GET /api/backup/backups e /ensaios |
