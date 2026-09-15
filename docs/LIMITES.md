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
| `TOKEN_PREFIXO_TAMANHO` | `8` | "plat_" + 3 do segredo; o portão do L0-02-d declara 8 (achado G1-d1) |
| `TOKENS_POR_USUARIO` | `20` | — |
| `CAMPO_MAPAS_MAX` | `200` | item L2-07-a-pwa-instalavel-cache: teto do que /api/campo/mapas devolve por chamada |
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

### `AUTH_PADROES`

| chave | padrão | mínimo | máximo |
|---|---|---|---|
| `senha_min` | `10` | `8` | `64` |
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

## trilha de auditoria (L7-20). Padrão de 2 anos porque a trilha responde por ATO DE NEGÓCIO, não por

| nome | valor | explicação |
|---|---|---|
| `AUDITORIA_RETENCAO_PADRAO_DIAS` | `730` | — |
| `AUDITORIA_RETENCAO_MIN_DIAS` | `90` | — |
| `AUDITORIA_RETENCAO_MAX_DIAS` | `3650` | — |
| `AUDITORIA_EXPORTA_MAX` | `100000` | — |
| `PAGINA_PADRAO` | `50` | — |
| `PAGINA_MAX` | `1000` | — |
| `RESTRICAO_MAX` | `20` | — |
| `TOKEN_ROTACAO_HORAS` | `24` | — |

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
| `METADADO_ISO_BYTES_MAX` | `1048576` | item L0-09-b-editor-iso-mgb: refutação exige recusar 5 MB (limite 1 MB) |
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
| `NOTIFICACOES_POR_MINUTO` | `60` | — |
| `NOTIFICACOES_DIAS` | `90` | — |
| `NOTIFICACOES_PAGINA_MAX` | `100` | — |
| `DESTAQUES_POR_GRUPO` | `24` | — |
| `BUSCA_Q_MAX` | `1000` | — |
| `BUSCA_TERMOS_MAX` | `200` | — |
| `BUSCA_TRGM_LIMIAR` | `0.3` | — |
| `BUSCA_REFORCO_STATUS` | `0.25` | — |
| `ITENS_PAGINA_MAX` | `200` | — |
| `ITENS_DESLOCAMENTO_MAX` | `10000` | — |
| `LIXEIRA_DIAS` | `30` | — |
| `RASTER_LIXEIRA_DIAS` | `7` | retenção da lixeira do item de IMAGEM: os objetos ficam no balde 7 dias após a |
| `COTA_ITENS` | `100000` | padrão por inquilino, tenant.config.catalogo.cota_itens |
| `USADO_POR_PROFUNDIDADE_MAX` | `5` | — |

## publicação de documento de construtor (L5-14-publicacao-links-embed)

| nome | valor | explicação |
|---|---|---|
| `PUBLICACAO_SLUG_MIN` | `2` | — |
| `PUBLICACAO_SLUG_MAX` | `60` | — |
| `PUBLICACAO_DOMINIOS_MAX` | `20` | — |
| `PUBLICACAO_CAMADAS_PROFUNDIDADE` | `4` | app -> mapa -> camada; folga para um nível extra de vista_de_camada |
| `PUBLICACAO_VISUALIZACOES_DIAS_MAX` | `366` | — |

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
| `UPLOAD_BYTES_MAX` | `68719476736` | 64 GiB. Eram 2 GiB, e 2 GiB não cabe uma ortofoto: 100 km² a |
| `UPLOAD_PARTE_BYTES` | `16777216` | 16 MiB (ADR 0005 seção 3.1; distinto de ARQUIVO_PARTE_BYTES acima, |
| `UPLOAD_EXPIRA_HORAS` | `24` | — |
| `UPLOAD_NOME_MAX` | `255` | — |

## upload grande retomável (L1-01-e; ADR 20260908T1600): o corpo de `PUT /api/uploads/{id}/partes/{n}` NUNCA

| nome | valor | explicação |
|---|---|---|
| `UPLOAD_PEDACO_BYTES` | `1048576` | 1 MiB por leitura do socket e escrita no disco de trabalho |
| `UPLOAD_DISCO_LIVRE_MIN_BYTES` | `2147483648` | 2 GiB livres exigidos no disco de trabalho, além da parte |
| `UPLOAD_RAM_MAX_MB` | `512` | teto declarado de pico de memória do processo que recebe partes |
| `UPLOAD_CABECALHO_INICIO_BYTES` | `65536` | bytes da parte 1 usados para recusar tipo errado antes do fim |

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

## SSO OIDC/SAML 2.0 (L0-08-sso; app/auth/sso.py): login federado por inquilino, sem biblioteca de SAML

| nome | valor | explicação |
|---|---|---|
| `SSO_TIMEOUT_S` | `5` | timeout de TODA chamada HTTP ao IdP (descoberta, JWKS, troca de código) |
| `SSO_TRANSACAO_MINUTOS` | `10` | validade do state/nonce/PKCE (OIDC) e do pedido (SAML) em plat.sso_transacao |
| `SSO_DESVIO_RELOGIO_S` | `60` | folga de relógio aceita em exp/iat (OIDC) e NotBefore/NotOnOrAfter (SAML) |
| `SSO_DESCOBERTA_CACHE_S` | `600` | cache em memória do documento de descoberta OIDC e das chaves JWKS |
| `SSO_RESPOSTA_MAX` | `262144` | teto do corpo SAMLResponse decodificado (256 KB; assertion típica < 30 KB) |

## conexão externa e SSRF (L6-02-a-modelo-conexao-e-seguranca; app/conexao/): modelo genérico de conexão

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_TIPOS` | `('wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'xyz', 'postgres_fdw', 's3', 'http', 'wms', 'wmts', 'wfs', 'ogc_api', 'esri_rest', 'stac', 'geoparquet', 'pmtiles', 'postgres_fdw', 's3', 'http', 'odk_central', 'google_sheets')` | — |
| `CONEXAO_MODOS` | `('referenciada', 'copiada')` | — |
| `CONEXAO_NOME_MAX` | `200` | — |
| `CONEXAO_URL_MAX` | `2048` | — |
| `CONEXAO_CONFIG_MAX_BYTES` | `8192` | tamanho máximo do JSON de `config` (json.dumps, utf-8) |
| `CONEXAO_DNS_TIMEOUT_S` | `3.0` | socket.getaddrinfo (validação do host antes de qualquer conexão) |
| `CONEXAO_CONECTAR_TIMEOUT_S` | `3.0` | — |
| `CONEXAO_LER_TIMEOUT_S` | `6.0` | teste de saúde: curto de propósito (POST /api/conexoes/{id}/testar) |
| `CONEXAO_REDIRECT_MAX` | `5` | cada hop é revalidado do zero (host novo pode ser interno) |
| `CONEXAO_RESPOSTA_MAX_BYTES` | `1048576` | 1 MiB: o teste de saúde confere status/corpo curto |

## conectores de feição externa WFS 2.0 / OGC API - Features (L6-02-c-wfs-ogcapi; app/conexao/vetor_externo.py

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_VETOR_LER_TIMEOUT_S` | `30.0` | página de feições é maior que o teste de saúde (6 s), |
| `CONEXAO_VETOR_METADADO_MAX_BYTES` | `33554432` | GetCapabilities/DescribeFeatureType/collections. |
| `CONEXAO_VETOR_PAGINA_MAX_BYTES` | `50331648` | corpo de UMA página de feições |
| `CONEXAO_VETOR_PAGINA_PADRAO` | `1000` | feições por página quando quem chama não escolhe |
| `CONEXAO_VETOR_PAGINA_MAX` | `10000` | teto do que se pede por página (COUNT / limit) |
| `CONEXAO_VETOR_PAGINAS_MAX` | `2000` | teto de requisições de UMA cópia (com 10 mil/página dá 20 mi) |
| `CONEXAO_VETOR_LIMITE_PADRAO` | `100000` | feições que a cópia aceita quando quem chama não declara |
| `CONEXAO_VETOR_LIMITE_MAX` | `2000000` | teto absoluto do limite declarável numa cópia |
| `CONEXAO_VETOR_PREVIA_MAX` | `1000` | feições que a consulta REFERENCIADA devolve por vez |
| `CONEXAO_VETOR_CACHE_TTL_S` | `30.0` | cache curto da consulta referenciada (item: "cache curto") |
| `CONEXAO_VETOR_CACHE_ENTRADAS` | `128` | entradas guardadas no processo; a mais velha sai |
| `COPIA_MEMORIA_MB` | `1024` | job conexao.copiar_vetor (ogr2ogr + reprojeção) |
| `COPIA_TIMEOUT_S` | `3600` | — |

## fonte de dado registrada: conector postgres_fdw (L0-04-i-fonte-registrada; ver

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_PG_CATEGORIAS_BLOQUEADAS` | `frozenset({'link_local', 'multicast', 'nao_especificado'})` | — |
| `CONEXAO_PG_BANCOS_PROIBIDOS` | `frozenset({'iagro_sat'})` | nome do banco de produção da casa, em qualquer host |
| `CONEXAO_PG_CONECTAR_TIMEOUT_S` | `5` | — |
| `CONEXAO_PG_ESTATEMENT_TIMEOUT_MS` | `8000` | listar tabelas/colunas nunca trava a rota |
| `CONEXAO_PG_TABELAS_MAX` | `500` | teto de tabelas devolvidas por GET .../tabelas |
| `CONEXAO_PG_COLUNAS_MAX` | `300` | teto de colunas por tabela publicada |
| `CONEXAO_PG_PUBLICAR_LOTE_MAX` | `50` | teto de tabelas por chamada de publicar-em-massa |

## agendamento de camada copiada (L6-02-k-agendamento; app/conexao/tarefas_agendamento.py): não é outro

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_COPIA_MAX_BYTES` | `8388608` | bem maior que o teste de saúde, mas pequeno de propósito |

## PMTiles/XYZ/TileJSON (L6-02-g-pmtiles-xyz-tilejson; app/conexao/ladrilhos.py): dois `CONEXAO_TIPOS` novos

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_PMTILES_RANGE_BYTES` | `16384` | bytes pedidos no Range de prova (cobre o cabeçalho fixo do PMTiles v3, |
| `CONEXAO_TILE_ZOOM_MAX` | `24` | teto de bom senso (WebMercator raramente passa de 22-23 na prática) |
| `CONEXAO_ATRIBUICAO_MAX` | `500` | `config.atribuicao`: texto curto de legenda, nunca um parágrafo |

## ArcGIS REST externo (L6-02-d-arcgis-rest-externo; ADR 0020): FeatureServer (query paginado),

| nome | valor | explicação |
|---|---|---|
| `ESRI_REST_TIMEOUT_S` | `15.0` | descrição do serviço (?f=json) e cada página de query |
| `ESRI_REST_IMAGEM_TIMEOUT_S` | `20.0` | export/exportImage: pode gerar imagem grande no servidor |
| `ESRI_REST_DESCRICAO_MAX_BYTES` | `5242880` | 5 MiB: JSON de descrição do serviço/camada |
| `ESRI_REST_PAGINA_MAX_BYTES` | `8388608` | 8 MiB: uma página de feições (geojson/pbf) |
| `ESRI_REST_MAX_RECORD_COUNT_PADRAO` | `1000` | quando o serviço não declara `maxRecordCount` |
| `ESRI_REST_PAGINAS_MAX` | `50` | teto de segurança mesmo com maxRecordCount hostil (ex.: 1) |
| `ESRI_REST_FEICOES_MAX` | `20000` | teto de segurança do modo referenciado (consulta ao vivo) |
| `ESRI_REST_IMAGEM_MAX_BYTES` | `8388608` | 8 MiB: uma única imagem export/exportImage |
| `ESRI_REST_IMAGEM_LADO_MAX` | `2048` | largura/altura máximas pedidas ao serviço (px) |

## WMS/WMTS externo (L6-02-b-wms-wmts): GetCapabilities pode ser grande (catálogo com centenas de camadas);

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_WMS_CAPACIDADES_MAX_BYTES` | `20971520` | 20 MiB |
| `CONEXAO_WMS_CAPACIDADES_TIMEOUT_S` | `15.0` | — |
| `CONEXAO_WMS_MAPA_MAX_BYTES` | `8388608` | 8 MiB: uma única imagem GetMap/tile, nunca um mosaico |
| `CONEXAO_WMS_MAPA_TIMEOUT_S` | `20.0` | — |
| `CONEXAO_WMS_FEICAO_MAX_BYTES` | `2097152` | 2 MiB: resposta de GetFeatureInfo (texto/GML/JSON) |
| `CONEXAO_WMS_LARGURA_MAX` | `2048` | — |
| `CONEXAO_WMS_ALTURA_MAX` | `2048` | — |
| `CONEXAO_WMTS_TILE_MAX_BYTES` | `4194304` | 4 MiB: um único tile (256/512 px), nunca a pirâmide |

## ponte com o ODK Central (L2-07-e-odk-central-ponte; app/odk/): conexão do tipo `odk_central`, publicação do

| nome | valor | explicação |
|---|---|---|
| `ODK_LER_TIMEOUT_S` | `30.0` | — |
| `ODK_PAGINA_ENVIOS` | `100` | $top do OData por página (o Central aceita até 1000; 100 é o padrão dele) |
| `ODK_ENVIOS_MAX_POR_EXECUCAO` | `1000` | teto de envios lidos numa sincronização (o resto fica para a próxima) |
| `ODK_PAGINAS_MAX` | `50` | trava contra paginação que nunca termina (página sempre cheia) |
| `ODK_RESPOSTA_MAX_BYTES` | `8388608` | página de OData / lista de entidades |
| `ODK_ENTIDADES_MAX` | `5000` | entidades lidas de um dataset para virar lista de escolhas |

## arquivo por URL (L6-02-h-csv-url-geojson-kml; app/conexao/arquivo_url.py): CSV/GeoJSON/KML/KMZ/GeoRSS/GPX

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_ARQUIVO_FORMATOS` | `('csv', 'geojson', 'kml', 'kmz', 'georss', 'gpx')` | — |
| `CONEXAO_ARQUIVO_MAX_BYTES` | `67108864` | teto geral do download (mesmo teto de GeoJSON do ADR 0005) |
| `CONEXAO_ARQUIVO_XML_MAX_BYTES` | `41943040` | ~480 MiB de pico medido, dentro do orçamento do job |
| `CONEXAO_ARQUIVO_LER_TIMEOUT_S` | `60.0` | baixar arquivo é mais lento que testar saúde (6 s lá) |
| `CONEXAO_ARQUIVO_INTERVALO_MIN_S` | `900` | atualização agendada: 15 min é o mínimo do agendador (L0-05) |
| `CONEXAO_ARQUIVO_INTERVALO_PADRAO_S` | `86400` | padrão: uma vez por dia |
| `CONEXAO_ARQUIVO_INTERVALO_MAX_S` | `2592000` | — |
| `CONEXAO_ARQUIVO_LOTE_PERIODICO` | `20` | conexões sincronizadas por execução do periódico |
| `CONEXAO_ARQUIVO_LAT_MAX` | `90.0` | — |
| `CONEXAO_ARQUIVO_LON_MAX` | `180.0` | — |

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
| `INGESTAO_EPSILON_ENVOLTORIA` | `1e-07` | — |

## intercâmbio de formatos em lote (L6-02-o): exportação por camada nos formatos extra, escrow do inquilino

| nome | valor | explicação |
|---|---|---|
| `INTERCAMBIO_EXPORTACAO_BYTES_MAX` | `2147483648` | 2 GiB: pacote final guardado no Garage |
| `INTERCAMBIO_DISCO_FOLGA` | `3` | disco livre exigido = estimativa do pacote × 3 (disco a 98%) |
| `INTERCAMBIO_CAMADAS_ESCROW_MAX` | `500` | teto de camadas vetoriais num escrow (job único, timeout 3600 s) |
| `INTERCAMBIO_XLSX_LINHAS_MAX` | `500000` | importação XLSX: acima disso a conversão p/ CSV estoura a memória |
| `INTERCAMBIO_DBF_LARGURA_MAX` | `254` | largura máxima de campo texto em DBF (limite do formato) |
| `INTERCAMBIO_MVT_ZOOM` | `14` | zoom de geração/leitura de mbtiles/pmtiles (declarado no relatório) |
| `INTERCAMBIO_MEMORIA_MB` | `1024` | job intercambio.exportar_camada / exportar_inquilino / importacoes_lote |
| `INTERCAMBIO_TIMEOUT_S` | `3600` | relógio do job de intercâmbio (EXPORTACAO_TIMEOUT_S é do L0-04-h) |
| `INTERCAMBIO_LOTE_ITENS_MAX` | `200` | teto de arquivos/camadas por chamada de lote (import ou export) |

## configurações da organização (L0-07-a-configuracoes-org; GET/PUT /api/org): nome, identidade visual

| nome | valor | explicação |
|---|---|---|
| `ORG_NOME_MAX` | `55` | mesmo teto do "Organization name" da Esri (portão do item-pai L0-07-a) |
| `ORG_COR_PADRAO` | `'#2463a8'` | mesmo azul de app/catalogo/miniatura.py TRACO, cor de marca padrão |
| `ORG_IDIOMAS` | `('pt-BR', 'en', 'es')` | só o que existe em web/js/i18n/ (UX-02: en e es com paridade de chaves) |
| `ORG_ZOOM_MAX` | `24` | teto de zoom de um webmap (padrão MapLibre/Leaflet) |
| `ORG_BASEMAP_MAX` | `100` | — |
| `ORG_LOGO_BYTES_MAX` | `1048576` | 1 MiB (portão do item-pai: "logo > 1 MB recusado") |
| `ORG_LOGO_PIXELS_MAX` | `25000000` | mesma defesa de bomba de descompressão de app/catalogo/miniatura.py |
| `ORG_LOGO_LADO` | `300` | canvas quadrado 300×300 (portão do item-pai) |
| `ORG_COTA_BYTES_MIN` | `104857600` | 100 MiB: abaixo disso o próprio inquilino de demonstração não sobe |
| `ORG_COTA_USUARIOS_MIN` | `1` | — |
| `ORG_COTA_BYTES_TETO_MAX` | `1099511627776` | 1 TiB |
| `ORG_COTA_USUARIOS_TETO_MAX` | `100000` | — |
| `ORG_COTA_USUARIOS_PADRAO` | `2000` | bem acima do maior lote (LOTE_MAX=100) e do uso medido em demo (T3: 59) |
| `ORG_COTA_ITENS_MIN` | `1` | cota de itens do catálogo (tenant.config.catalogo.cota_itens, D16 da 011) |
| `ORG_USO_DIAS_PADRAO` | `30` | período padrão da tela/relatório de uso (L0-07-admin-org) |
| `ORG_USO_DIAS_MAX` | `366` | acima disso = 422 (a série é diária; um ano basta para o console) |

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

## motor multicritério (L3-01-a/b; ADR 0016, decisões A1/A3/A7 do L3L6_CONCEITO). Os tetos de unidade e de

| nome | valor | explicação |
|---|---|---|
| `AMC_LADO_M_MIN` | `10.0` | abaixo disso a grade deixa de ser unidade de análise e vira pixel |
| `AMC_LADO_M_MAX` | `100000.0` | 100 km: célula maior que isto não cabe em nenhuma zona UTM sem distorcer |
| `AMC_AREA_ESTUDO_KM2_MAX` | `2000000.0` | ~1/4 do Brasil: acima disso a zona UTM única do centróide perde sentido |
| `AMC_UNIDADES_MAX` | `1000000` | unidades por conjunto (grade ou feições) |
| `AMC_FEICOES_INLINE_MAX` | `20000` | feições por envio síncrono de conjunto do tipo 'feicoes' |
| `AMC_MODELOS_POR_INQUILINO` | `500` | modelos vivos (apagado_em IS NULL) por inquilino |
| `AMC_CONJUNTOS_POR_INQUILINO` | `200` | conjuntos de unidades por inquilino |
| `AMC_VERSOES_POR_MODELO` | `500` | versões de um modelo (cada edição cria uma; imutáveis, nunca apagadas) |
| `AMC_UNIDADES_PAGINA_MAX` | `5000` | unidades por página em GET /api/amc/conjuntos/{id}/unidades |
| `AMC_RESULTADOS_PAGINA_MAX` | `5000` | linhas por página em GET /api/amc/execucoes/{id}/resultados |

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
| `RASTER_BYTES_MAX` | `68719476736` | bruto aceito para ingestão: amarrado ao teto de envio, para os |
| `RASTER_VISUAL_MAX_LADO` | `1024` | miniatura PNG (lado maior) |
| `RASTER_ESTATISTICA_AMOSTRA` | `100000` | pixels amostrados por banda para percentis do perfil visual |
| `RASTER_TILE_CACHE_DATASET_MAX` | `8` | datasets abertos por processo no handler de tiles (LRU) |
| `RASTER_GDAL_CACHE_MB` | `256` | — |
| `RASTER_UPLOAD_TRANSACAO_PARADA` | `'10min'` | — |
| `RASTER_TILE_TIMEOUT_S` | `30` | teto de renderização de um tile (mata a requisição, não o worker) |
| `RASTER_TILE_NIVEIS_ABAIXO_DO_MINIMO` | `3` | — |

## geocodificação de tabela enviada pelo usuário (L2-11-a-geocodificacao-csv). O teto de tamanho é medido

| nome | valor | explicação |
|---|---|---|
| `GEOCOD_ARQUIVO_BYTES_MAX` | `33554432` | 32 MiB do arquivo enviado (D21: o laço trabalha com <= 3 GB) |
| `GEOCOD_LINHAS_MAX` | `200000` | linhas de dado (sem o cabeçalho) |
| `GEOCOD_AMOSTRA_COLUNAS_BYTES` | `262144` | só este pedaço é lido para propor o mapeamento de colunas |
| `GEOCOD_LOTE_GRAVACAO` | `500` | linhas por INSERT em lote (execute_values) |
| `GEOCOD_CAMPO_TEXTO_MAX` | `300` | valor de célula acima disso é truncado com aviso na linha |
| `GEOCOD_LINHAS_PAGINA_MAX` | `500` | teto da listagem da tela de revisão |
| `GEOCOD_CAMPOS` | `('endereco', 'logradouro', 'numero', 'bairro', 'municipio', 'uf', 'cep')` | — |

## exportação de camada (L0-04-h-exportar; ADR 0016). Os tempos e tetos abaixo saem de MEDIÇÃO nesta

| nome | valor | explicação |
|---|---|---|
| `EXPORTACAO_VALIDADE_DIAS` | `7` | arquivo gerado some depois disso (periódico exportacao.expirar) |
| `EXPORTACAO_POR_USUARIO_EM_CURSO` | `3` | exportações pendentes/gerando por usuário (refutação: 5 em paralelo) |
| `EXPORTACAO_MEMORIA_MB` | `1024` | job exportacao.gerar (mesmo teto de ingestao.carregar) |
| `EXPORTACAO_TIMEOUT_S` | `3600` | — |
| `EXPORTACAO_DISCO_MIN_LIVRE_BYTES` | `2147483648` | nunca começa com menos que isto livre (disco a 98%) |
| `EXPORTACAO_FATOR_DISCO` | `3` | arquivo temporário estimado = tamanho da tabela x isto (GML mede 3,4x |
| `EXPORTACAO_CAMPOS_MAX` | `500` | mesmo teto de INGESTAO_CAMPOS_MAX (a lista vem do mesmo item) |
| `EXPORTACAO_WHERE_MAX` | `4000` | caracteres do filtro `where` (o parser do L2-04-b recusa o resto) |
| `EXPORTACAO_NOME_MAX` | `120` | nome do arquivo pedido pelo usuário (sem extensão) |
| `EXPORTACAO_ERRO_BANCO_MAX` | `300` | tamanho do erro do banco depois de saneado, no corpo do 400 |
| `EXPORTACAO_CODIFICACOES` | `('UTF-8', 'ISO-8859-1')` | — |
| `EXPORTACAO_CSV_SEPARADORES` | `(',', ';', '\t', '|')` | — |
| `EXPORTACAO_CSV_DECIMAIS` | `('.', ',')` | — |
| `EXPORTACAO_BLOCO_LEITURA_BYTES` | `8388608` | leitura do arquivo pronto em blocos (sha256 e envio); NUNCA |

## exportação COMPLETA do inquilino (L0-06-d-exportar-inquilino): "Exportar meu inquilino" do admin. Reusa

| nome | valor | explicação |
|---|---|---|
| `EXPORTACAO_INQUILINO_TIMEOUT_S` | `14400` | inquilino inteiro pode ter muitas camadas; 4x o de uma só |
| `EXPORTACAO_INQUILINO_POR_DIA_MAX` | `1` | portão do item: pedir a 2ª no mesmo dia UTC devolve 429 |

## SAML 2.0 Web SSO por inquilino (L0-08-b-saml; app/auth/saml.py)

| nome | valor | explicação |
|---|---|---|
| `SAML_DESVIO_RELOGIO_S` | `300` | tolerância de relógio IdP x SP (o portão manda recusar 10 min à frente) |
| `SAML_RESPOSTA_MAX` | `262144` | SAMLResponse/LogoutRequest acima disto = 413 (asserção real tem poucos KiB) |
| `SAML_METADADO_MAX` | `524288` | metadado do IdP lido por URL/arquivo |
| `SAML_METADADO_TIMEOUT_S` | `8.0` | leitura do metadado do IdP por URL |
| `SAML_TRANSACAO_MIN` | `10` | validade do AuthnRequest/LogoutRequest emitido (plat.saml_transacao) |

## ferramentas de análise (L2-05-a; L2_CONCEITO C8): job por padrão, síncrono só abaixo do custo declarado

| nome | valor | explicação |
|---|---|---|
| `FERRAMENTA_SINCRONO_CUSTO_MAX` | `5000` | custo = feições × complexidade declarada no manifesto; acima disso só job |
| `FERRAMENTA_JOB_MEMORIA_MB` | `1024` | RLIMIT_DATA do filho que roda uma ferramenta |
| `FERRAMENTA_JOB_TIMEOUT_S` | `1800` | 30 min por execução; ferramenta mais longa é outro tipo de job |
| `BUFFER_DISTANCIA_M_MAX` | `100000` | 100 km: acima disso o buffer geodésico deixa de fazer sentido em camada |

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
| `ESCALA_CELULAS_GEOJSON_MAX` | `50000` | feições de GET /api/multiescala/execucoes/{id}/celulas (UX-08); além = truncado |
| `ESCALA_AMOSTRAS_LOTE_MAX` | `20000` | amostras de fator por chamada de POST (streaming não é o item; teto direto) |

## - L2-10-d-regras-de-atributo: regras por camada (cálculo, restrição, validação) e campos virtuais, avaliadas

| nome | valor | explicação |
|---|---|---|
| `REGRAS_POR_CAMADA_MAX` | `100` | entradas em dados.regras (cálculo + restrição + validação) |
| `REGRAS_CAMPOS_VIRTUAIS_MAX` | `50` | entradas em dados.campos_virtuais (só leitura, avaliados na leitura) |
| `REGRAS_EXPRESSAO_TEXTO_MAX` | `4000` | caracteres por expressão de regra (bem abaixo de MAX_TEXTO do avaliador) |
| `REGRAS_MENSAGEM_MAX` | `500` | mensagem configurada da restrição/validação |
| `REGRAS_VALIDACAO_LOTE` | `5000` | feições por lote do job camadas.validar (cursor no servidor) |
| `REGRAS_VALIDACAO_ERROS_MAX` | `1000000` | teto de erros gravados por execução (acima disso o job para e avisa) |
| `REGRAS_FEICOES_LEITURA_MAX` | `1000` | linhas por chamada de GET /api/camadas/{id}/feicoes |
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

## tabela de atributos da camada (L2-01-g-tabela-atributos): paginação no servidor, busca em texto, filtro

| nome | valor | explicação |
|---|---|---|
| `TABELA_PAGINAS` | `(50, 200, 1000)` | — |
| `TABELA_BUSCA_MAX` | `200` | termo de busca (ILIKE + unaccent) — acima disso é ataque, não busca |
| `TABELA_FIDS_MAX` | `5000` | seleção vinda do mapa: identificadores enviados de uma vez |
| `TABELA_COLUNAS_MAX` | `500` | mesmo teto de `campos` no esquema do tipo camada_vetorial (029) |
| `TABELA_ALIAS_MAX` | `200` | mesmo teto de `alias` no esquema do tipo camada_vetorial (029) |
| `TABELA_LARGURA_MIN` | `40` | pixels; abaixo disso a coluna some da tela e não dá para arrastar |
| `TABELA_LARGURA_MAX` | `2000` | — |
| `TABELA_DOMINIO_ITENS_MAX` | `1000` | pares código -> descrição por coluna |
| `TABELA_DOMINIO_TEXTO_MAX` | `250` | — |
| `TABELA_GEOMETRIA_LIMITE` | `2000` | feições com geometria devolvidas para desenhar no mapa (por página) |

## exportação de camada (L0-04-h-exportar; ADR 0018). Os tempos e tetos abaixo saem de MEDIÇÃO nesta

| nome | valor | explicação |
|---|---|---|
| `EXPORTACAO_VALIDADE_DIAS` | `7` | arquivo gerado some depois disso (periódico exportacao.expirar) |
| `EXPORTACAO_POR_USUARIO_EM_CURSO` | `3` | exportações pendentes/gerando por usuário (refutação: 5 em paralelo) |
| `EXPORTACAO_MEMORIA_MB` | `1024` | job exportacao.gerar (mesmo teto de ingestao.carregar) |
| `EXPORTACAO_TIMEOUT_S` | `3600` | — |
| `EXPORTACAO_DISCO_MIN_LIVRE_BYTES` | `2147483648` | nunca começa com menos que isto livre (disco a 98%) |
| `EXPORTACAO_FATOR_DISCO` | `3` | arquivo temporário estimado = tamanho da tabela x isto (GML mede 3,4x |
| `PACOTE_CAMADAS_MAX` | `50` | camadas num pacote de mapa (item L2-01-l) |
| `PACOTE_IMPORTAR_MAX_BYTES` | `209715200` | pacote enviado para reimportação (acima disso, 413) |
| `PACOTE_OGR_TIMEOUT_S` | `900` | ogr2ogr de UMA camada do pacote na reimportação |
| `EXPORTACAO_IDS_MAX` | `200000` | fids de uma seleção exportada (mesmo teto do tipo de item `selecao`) |
| `EXPORTACAO_CAMPOS_MAX` | `500` | mesmo teto de INGESTAO_CAMPOS_MAX (a lista vem do mesmo item) |
| `EXPORTACAO_WHERE_MAX` | `4000` | caracteres do filtro `where` (o parser do L2-04-b recusa o resto) |
| `EXPORTACAO_NOME_MAX` | `120` | nome do arquivo pedido pelo usuário (sem extensão) |
| `EXPORTACAO_ERRO_BANCO_MAX` | `300` | tamanho do erro do banco depois de saneado, no corpo do 400 |
| `EXPORTACAO_CODIFICACOES` | `('UTF-8', 'ISO-8859-1')` | — |
| `EXPORTACAO_CSV_SEPARADORES` | `(',', ';', '\t', '|')` | — |
| `EXPORTACAO_CSV_DECIMAIS` | `('.', ',')` | — |
| `EXPORTACAO_BLOCO_LEITURA_BYTES` | `8388608` | leitura do arquivo pronto em blocos (sha256 e envio); NUNCA |

## widgets de página e de menu (L5-01-d)

| nome | valor | explicação |
|---|---|---|
| `QR_TEXTO_MAX` | `2048` | conteúdo máximo do QR de compartilhar (uma URL longa cabe) |

## layout de impressão (item L2-12-b-layouts-elementos-exportacao)

| nome | valor | explicação |
|---|---|---|
| `LAYOUT_ELEMENTOS_MAX` | `200` | elementos por documento de layout |
| `LAYOUT_QUADROS_MAX` | `6` | quadros de mapa por layout (principal + localização + auxiliares) |
| `LAYOUT_ESCALA_MIN` | `100` | 1:N mínimo aceito no quadro por escala fixa |
| `LAYOUT_ESCALA_MAX` | `50000000` | 1:N máximo (o mundo cabe em A4) |
| `LAYOUT_TEXTO_MAX` | `4000` | caracteres de um título/texto do layout |
| `LAYOUT_TABELA_LINHAS_MAX` | `200` | linhas da tabela de atributos num layout |
| `LAYOUT_DPI_MIN` | `72` | DPI mínimo de exportação |
| `LAYOUT_DPI_MAX` | `300` | DPI máximo de exportação (o portão do item pede 96-300) |
| `LAYOUT_QUADRO_PIXELS_MAX` | `4096` | maior lado do quadro em pixels no motor de render; acima, o quadro é |
| `LAYOUT_INLINE_BYTES_MAX` | `262144` | documento de layout inline num pedido/job (JSON) |

## resultado de traçado de rede de utilidades (L4-02-f-resultados-e-exportacao)

| nome | valor | explicação |
|---|---|---|
| `TRACADO_EXPORTACAO_MAX` | `50000` | elementos por exportação ou por camada salva |
| `TRACADO_HISTORICO_MAX` | `20` | "os 20 últimos traçados do usuário" (portão do item) |

## gráficos por camada (L2-01-i-graficos-de-camada; rota POST /api/camadas/{id}/grafico): a agregação é

| nome | valor | explicação |
|---|---|---|
| `GRAFICO_CATEGORIAS_PADRAO` | `50` | barras/pizza: categorias maiores mostradas; o resto vira UM grupo "outros" |
| `GRAFICO_CATEGORIAS_MAX` | `500` | — |
| `GRAFICO_FAIXAS_MAX` | `200` | histograma: faixas de largura igual |
| `GRAFICO_AMOSTRA_PADRAO` | `2000` | dispersão: pontos desenhados (a regressão usa TODAS as linhas) |
| `GRAFICO_AMOSTRA_MAX` | `5000` | — |
| `GRAFICO_RESPOSTA_BYTES_MAX` | `1000000` | teto declarado (refutação do item); conferido por teste, não por corte |

## MapServer compatível com Esri (item L2-04-f): export/identify/legend/find e o GeometryServer.

| nome | valor | explicação |
|---|---|---|
| `MAPSERVER_LADO_MAX` | `4096` | — |
| `MAPSERVER_PIXELS_MAX` | `16777216` | — |
| `MAPSERVER_DPI_MAX` | `600` | acima disso o traço em pixel passa a não caber na memória prometida |
| `MAPSERVER_FEICOES_POR_CAMADA` | `50000` | teto de feições desenhadas por camada num único export |
| `MAPSERVER_CAMADAS_MAX` | `50` | camadas desenhadas por pedido (o documento de mapa aceita 200) |
| `MAPSERVER_IDENTIFY_MAX` | `100` | resultados por identify (`maxAllowableOffset` da doc Esri é outro eixo) |
| `MAPSERVER_FIND_MAX` | `100` | resultados por find |
| `GEOMETRIA_FEICOES_MAX` | `1000` | geometrias por chamada do GeometryServer (project/buffer/...) |
| `GEOMETRIA_VERTICES_MAX` | `200000` | vértices somados por chamada (mesmo teto do filtro espacial da query) |

## réplicas para trabalho desconectado (item L2-13-b-replicas-sincronizacao)

| nome | valor | explicação |
|---|---|---|
| `REPLICA_VALIDADE_DIAS` | `30` | — |
| `REPLICA_RASTREIO_RETENCAO_DIAS` | `45` | — |
| `REPLICA_CAMADAS_MAX` | `20` | camadas por réplica (o pacote é um arquivo só, baixado por rede de campo) |
| `REPLICA_FEICOES_MAX` | `100000` | feições por camada no pacote; acima disso o recorte tem de ser menor |
| `REPLICA_SINCRONIZAR_LOTE_MAX` | `2000` | mudanças por camada num pedido (mesmo teto de EDICAO_LOTE_MAX) |
| `REPLICA_BAIXAR_MAX` | `5000` | mudanças do servidor devolvidas por camada por sincronização |
| `REPLICA_ANEXOS_BYTES_MAX` | `67108864` | 64 MiB de anexo embutido no pacote (acima disso o pacote é recusado) |
| `REPLICA_POR_USUARIO` | `20` | réplicas vivas por usuário (cada uma segura um pacote no armazenamento) |
| `REPLICA_NOME_MAX` | `200` | CHECK(length(nome) BETWEEN 1 AND 200) da migração |
| `REPLICA_FILTRO_MAX` | `2000` | CHECK(length(filtro) <= 2000) da migração |

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
| `RASTER_BYTES_MAX` | `68719476736` | bruto aceito para ingestão: amarrado ao teto de envio, para os |
| `RASTER_VISUAL_MAX_LADO` | `1024` | miniatura PNG (lado maior) |
| `RASTER_ESTATISTICA_AMOSTRA` | `100000` | pixels amostrados por banda para percentis do perfil visual |
| `RASTER_TILE_CACHE_DATASET_MAX` | `8` | datasets abertos por processo no handler de tiles (LRU) |
| `RASTER_GDAL_CACHE_MB` | `256` | — |
| `RASTER_UPLOAD_TRANSACAO_PARADA` | `'10min'` | — |
| `RASTER_TILE_TIMEOUT_S` | `30` | teto de renderização de um tile (mata a requisição, não o worker) |
| `RASTER_TILE_NIVEIS_ABAIXO_DO_MINIMO` | `3` | — |

## classes de relacionamento entre camadas (L2-10-b-relacionamentos; plat.relacionamento/_junc,

| nome | valor | explicação |
|---|---|---|
| `RELACIONAMENTO_NOME_MAX` | `120` | — |
| `RELACIONAMENTO_VALOR_MAX` | `200` | tamanho do valor de chave guardado em relacionamento_junc (texto) |
| `RELACIONAMENTO_LIMITE_PADRAO` | `2000` | teto de relacionados por consulta quando a classe não declara outro |
| `RELACIONAMENTO_LIMITE_MAX` | `100000` | teto absoluto (refutação do item: "100 mil relacionados numa origem") |

## clonagem de camadas hospedadas da Esri (L2-08-b-clonar-camadas-hospedadas; app/migracao/clonar.py)

| nome | valor | explicação |
|---|---|---|
| `CLONE_PAGINA` | `1000` | feições por página de query e por lote de INSERT (maxRecordCount 1000-2000) |
| `CLONE_ANEXO_MAX` | `52428800` | bytes por anexo lido do portal (acima: aviso no relatório, feição segue) |
| `CLONE_CAMADAS_MAX` | `200` | camadas + tabelas por serviço numa execução |
| `CLONE_AMOSTRA` | `100` | feições da amostra comparada por sha256 (geometria normalizada + atributos) |

## análise 3D sobre terreno e extrusões (L2-09-d-analise-3d-visibilidade): terreno chega INLINE na

| nome | valor | explicação |
|---|---|---|
| `ANALISE3D_CELULAS_MAX` | `250000` | mesma ordem do teto multiescala (proteção de RAM/disco) |
| `ANALISE3D_ALTURA_MAX_M` | `10000.0` | altura de terreno/observador/alvo/sólido; Everest × 1 sobra |
| `ANALISE3D_DISTANCIA_MAX_M` | `30000.0` | visada e viewshed recusam alvo além disso (refutação: 200 km) |
| `ANALISE3D_AMOSTRAS_MAX` | `20000` | pontos de perfil/visada por chamada |
| `ANALISE3D_GDAL_TIMEOUT_S` | `120` | gdal_viewshed por subprocesso, sempre com relógio |
| `ANALISE3D_SOLIDOS_MAX` | `500` | sólidos (extrusões) por análise de sombra |
| `ANALISE3D_SOLIDO_VERTICES_MAX` | `200` | vértices do polígono de cada sólido |

## ------------------------------------------------------------- console da plataforma (item L0-07-f)

| nome | valor | explicação |
|---|---|---|
| `PLATAFORMA_SUSPENSAO_MENSAGEM_MAX` | `300` | mensagem mostrada aos membros do inquilino suspenso (503); cabe num aviso |

## edição em lote (L2-03-f-edicao-em-lote-calculo-campo; `POST /api/camadas/{id}/lote`)

| nome | valor | explicação |
|---|---|---|
| `LOTE_SINCRONO_MAX` | `5000` | hipótese do item: acima disto roda como job (L0-05), com progresso |
| `LOTE_TRANSACAO` | `1000` | feições por sub-lote dentro da transação única (progresso a cada sub-lote) |
| `LOTE_PREVIA` | `10` | linhas da pré-visualização (antes/depois), hipótese do item |
| `LOTE_IDS_MAX` | `50000` | ids explícitos numa seleção (acima disto use `onde` ou `todas`) |
| `LOTE_FALHAS_MAX` | `100` | falhas por feição devolvidas no modo parcial (o resto vira contagem) |
| `LOTE_EXPRESSAO_MS` | `500` | orçamento do avaliador POR LINHA (mesmo teto do servidor do L2-10-c) |
| `LOTE_JOB_TIMEOUT_S` | `1800` | teto do job (refutação: "mede se o job respeita o timeout") |
| `LOTE_MAPEAMENTO_MAX` | `500` | pares campo_destino: campo_origem em copiar/mover (teto de campos da camada) |

## ------------------------------------------------------------- relatórios do admin (item L0-07-e; limites iguais aos

| nome | valor | explicação |
|---|---|---|
| `RELATORIO_JANELA_DIAS` | `366` | janela máxima de um relatório: 12 meses |
| `RELATORIO_LINHAS_MAX` | `10000` | linhas por relatório; acima disso o CSV é cortado e o resultado diz truncado |
| `RELATORIO_POR_TIPO_HORA` | `1` | pedidos por tipo por hora pela API (agenda disparada pelo worker não conta) |

## fronteira de Pareto do motor multicritério (L3-08-pareto): análise sem agregação, 2 a 4 objetivos.

| nome | valor | explicação |
|---|---|---|
| `PARETO_UNIDADES_MAX` | `50000` | — |

## chamados de suporte (L7-13-a-chamados; migração 20260908T2230_chamados_suporte.sql). O contexto vem do

| nome | valor | explicação |
|---|---|---|
| `CHAMADO_TITULO_MAX` | `200` | — |
| `CHAMADO_DESCRICAO_MAX` | `20000` | — |
| `CHAMADO_COMENTARIO_MAX` | `10000` | — |
| `CHAMADO_SEVERIDADES` | `('baixa', 'media', 'alta', 'critica')` | — |
| `CHAMADO_ESTADOS` | `('aberto', 'em_analise', 'aguardando_cliente', 'resolvido', 'fechado')` | — |
| `CHAMADO_CONTEXTO_BYTES_MAX` | `64000` | contexto inteiro serializado; o que passa é cortado com marca |
| `CHAMADO_REQ_IDS_MAX` | `20` | as últimas 20 requisições (hipótese do item) |
| `CHAMADO_REQ_ID_TAM` | `16` | req_id são 16 hex (app/log.py::req_id); o que não casa é descartado |
| `CHAMADO_CAPTURA_BYTES_MAX` | `2000000` | PNG decodificado; 2 MiB cobre tela 1280×800 com folga |
| `CHAMADO_ANEXO_BYTES_MAX` | `8000000` | anexo comum; acima disso o upload retomável (L0-04-a) é o caminho |
| `CHAMADO_DOM_ENTRADAS_MAX` | `60` | estrutura do DOM capturada: nº de elementos descritos |
| `CHAMADO_DOM_TEXTO_MAX` | `120` | e o texto de cada entrada, cortado aqui |
| `CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS` | *(dicionário; ver subtabela abaixo)* | — |

### `CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS`

| chave | valor |
|---|---|
| `alta` | `8` |
| `baixa` | `72` |
| `critica` | `4` |
| `media` | `24` |

## recurso partilhado com dimensão de inquilino (conserto de classe 06/09, laudos ataque-g2/g3/g4/g6).

| nome | valor | explicação |
|---|---|---|
| `SSE_POR_USUARIO` | `10` | conexões de eventos abertas por usuário (era 10 POR PROCESSO = 20 na unidade) |
| `SSE_POR_INQUILINO` | `40` | teto novo: sem ele um inquilino com muitos usuários consome a máquina inteira |
| `SSE_TOTAL` | `200` | teto novo: orçamento da instalação, independente de quantos inquilinos existem |
| `CEIFA_API_INTERVALO_S` | `30` | a API ceifa os jobs sem sinal do PRÓPRIO inquilino no máximo a cada 30 s |
| `CEIFA_LIMITE_S` | `60` | mesmo LIMITE_SEM_SINAL_S do worker (app/jobs/worker.py); piso na função SQL |
| `CHAVE_RESERVADA` | `'sys:'` | espaço de nome das chaves de trinco dos periódicos da plataforma |

## regras de atributo de rede (L4-29-regras-de-atributo-de-rede; migração 20260908T1934_regras_atributo_rede.sql):

| nome | valor | explicação |
|---|---|---|
| `REDE_REGRA_MAX` | `1000` | regras ativas por (inquilino, perfil) numa rodada |
| `REDE_REGRAS_OBJETOS_MAX` | `50000` | objetos de rede avaliados por rodada de cálculo |
| `REDE_REGRAS_ITENS_MAX` | `10000` | itens de uma validação em lote (acima disso: truncado=true) |
| `REDE_REGRAS_ERROS_MAX` | `100` | erros de avaliação guardados no resultado de uma rodada (o total é contado) |

## consumidores e endereços da rede (L4-20-consumidores-e-enderecos; migração

| nome | valor | explicação |
|---|---|---|
| `REDE_ENDERECOS_MAX` | `500000` | teto de endereços por geração (proteção de RAM/tempo da consulta) |
| `REDE_RAIO_REDE_MAX_M` | `2000.0` | raio máximo de busca de rede a partir do endereço |
| `REDE_RAIO_PADRAO_M` | `700.0` | portão do item: endereço com rede a até 700 m |
| `REDE_RAIO_BT_PADRAO_M` | `135.0` | presença de baixa tensão (calibração na base da cooperativa de teste) |
| `REDE_JUSANTE_TRECHOS_MAX` | `200000` | teto de trechos por cálculo de jusante (grafo em memória) |
| `REDE_JUSANTE_NO_MAX` | `200000` | teto de nós do grafo |
| `REDE_AGREGACAO_MIN_UCS` | `5` | regra do adversário: agregação mínima exibida quando há consumo |

## pipeline único de upload (L7-03-a-antivirus-upload; app/varredura_conteudo.py POLITICAS): tamanho por

| nome | valor | explicação |
|---|---|---|
| `ANEXO_BYTES_MAX` | `104857600` | — |
| `IMAGEM_UPLOAD_BYTES_MAX` | `1048576` | — |
| `CLAMD_MAX_BYTES` | `26214400` | StreamMaxLength padrão do clamd; acima disso só o início é varrido |
| `CLAMD_TIMEOUT_S` | `20.0` | clamd fora do ar = recusa (nunca "passa sem varrer" quando configurado) |

## - L6-01-i-raster-e-arquivos: camadas de ARQUIVO do acervo da casa (acervo.camada_arquivo) no catálogo

| nome | valor | explicação |
|---|---|---|
| `ACERVO_ARQUIVO_BYTES_MAX` | `2147483648` | teto por arquivo (igual a RASTER_BYTES_MAX; guardrail D21) |
| `ACERVO_ARQUIVO_LOTE_MAX` | `50` | arquivos por chamada de exposição em lote |
| `ACERVO_ARQUIVO_LOTE_BYTES_MAX` | `3221225472` | soma do lote (D21: a trilha trabalha com <= 3 GB) |
| `ACERVO_ARQUIVO_LISTA_MAX` | `500` | linhas por página de GET /api/acervo/arquivos |

## geocodificação de tabela (L2-11-a-geocodificacao-csv): CSV/XLSX com endereço vira job de geocodificação em

| nome | valor | explicação |
|---|---|---|
| `GEOCODIFICADOR_LOTE_MAX_LINHAS` | `20000` | — |
| `GEOCODIFICADOR_LOTE_LIMIAR_PENDENTE_PADRAO` | `60.0` | score abaixo disso também vira pendente, mesmo com tipo bom |
| `GEOCODIFICADOR_LOTE_TITULO_MAX` | `250` | — |
| `ESCALA_AMOSTRAS_LOTE_MAX` | `20000` | amostras de fator por chamada de POST (streaming não é o item; teto direto) |

## limite de taxa por inquilino/plano (L7-03-b-rate-limit-abuso; app/limite_taxa.py, docs/SEGURANCA.md §9):

| nome | valor | explicação |
|---|---|---|
| `LIMITE_TAXA_PADROES` | *(dicionário; ver subtabela abaixo)* | — |
| `LIMITE_TAXA_JANELA_S` | `60` | janela deslizante única para os dois escopos acima (segundos) |
| `LIMITE_TAXA_ESCOPOS` | `('api', 'tiles')` | — |
| `LIMITE_TAXA_RETRY_AFTER_MIN_S` | `1` | nunca manda Retry-After: 0 (RFC 6585 recomenda um valor positivo) |

### `LIMITE_TAXA_PADROES`

| chave | padrão | mínimo | máximo |
|---|---|---|---|
| `api_por_minuto` | `6000` | `5` | `500000` |
| `tiles_por_minuto` | `12000` | `10` | `2000000` |

## - L3-05-localizar-regioes: localizar N regiões contíguas sobre a grade de favorabilidade

| nome | valor | explicação |
|---|---|---|
| `REGIOES_N_MAX` | `30` | o mesmo teto da referência (Locate Regions: 1-30) |
| `REGIOES_CELULAS_MAX` | `4000000` | células da grade aceitas por chamada (2.000×2.000; acima disso é job) |
| `REGIOES_TEMPO_LIMITE_S` | `120` | a rota é síncrona: acima disto o pedido é grande demais para a tela |

## ------------------------------------------------------------- provisionamento federado (item L0-08-e)

| nome | valor | explicação |
|---|---|---|
| `PROVISIONAMENTO_REGRAS_MAX` | `200` | regras (valores do IdP mapeados) por provedor |
| `PROVISIONAMENTO_GRUPOS_POR_REGRA` | `50` | grupos internos por regra |
| `PROVISIONAMENTO_GRUPOS_IDP_MAX` | `1000` | valores do atributo de grupos lidos do IdP por login (o resto é ignorado) |
| `PROVISIONAMENTO_VALOR_MAX` | `200` | tamanho de um valor de grupo do IdP |

## - L3-09-backtest-decisao-real: comparar o ranking do modelo com as escolhas reais

| nome | valor | explicação |
|---|---|---|
| `BACKTEST_PONTOS_MAX` | `50000` | escolhas por chamada (a grade regional de teste tem ~600) |
| `BACKTEST_PERMUTACOES_MAX` | `20000` | sorteios do nulo por chamada (a rota é síncrona) |

## traçado de custo mínimo sobre a grade do motor multicritério (L3-10-corredor-custo-minimo)

| nome | valor | explicação |
|---|---|---|
| `CORREDOR_CELULAS_GEOJSON_MAX` | `20000` | — |

## consulta SQL do cliente no banco externo (L6-02-j-bancos-externos; app/conexao/consulta_sql.py): LIMIT

| nome | valor | explicação |
|---|---|---|
| `CONEXAO_PG_CONSULTA_LINHAS_MAX` | `5000` | — |
| `CONEXAO_PG_CONSULTA_TEXTO_MAX` | `4000` | — |

## catálogo de conectores públicos (L6-02-m-catalogo-endpoints-brasil; app/conexao/endpoints_publicos.py):

| nome | valor | explicação |
|---|---|---|
| `ENDPOINT_PUBLICO_LER_TIMEOUT_S` | `20.0` | leitura do documento de teste (órgão lento monta capabilities em segundos) |
| `ENDPOINT_PUBLICO_MAX_BYTES` | `4194304` | 4 MiB: acima disso o serviço respondeu XML e conta como vivo (OGC) |
| `ENDPOINT_PUBLICO_RETESTE_DIAS` | `7` | cadência do job endpoints_publicos.retestar (B12: "retestado por semana") |
| `ENDPOINT_PUBLICO_FALHAS_PARA_MORTO` | `1` | 1 teste vermelho já tira da lista (vai para 'fora do ar'; volta ao passar) |
| `ENDPOINT_PUBLICO_PAGINA_MAX` | `500` | a tela lista o catálogo inteiro de uma vez (dezenas, não milhares) |

## descoberta por catálogo CSW 2.0.2 (L6-06-descoberta-csw; app/conexao/csw.py): a INDE devolve ~9 KB por

| nome | valor | explicação |
|---|---|---|
| `CSW_MAX_REGISTROS` | `20` | maxRecords por GetRecords (e teto do que a tela pede) |
| `CSW_LER_TIMEOUT_S` | `20.0` | leitura de GetRecords/GetRecordById (buscar_seguro) |
| `CSW_TEXTO_MAX` | `1000` | corte de resumo/licença/linhagem guardados na ficha (config <= 8 KiB) |
| `CSW_PALAVRAS_MAX` | `30` | palavras-chave guardadas por registro |
| `CSW_TEXTO_BUSCA_MAX` | `200` | tamanho do texto livre da busca (vira AnyText like '%...%') |

## motor multicritério (L3-01-a/b; ADR 0016, decisões A1/A3/A7 do L3L6_CONCEITO). Os tetos de unidade e de

| nome | valor | explicação |
|---|---|---|
| `AMC_LADO_M_MIN` | `10.0` | abaixo disso a grade deixa de ser unidade de análise e vira pixel |
| `AMC_LADO_M_MAX` | `100000.0` | 100 km: célula maior que isto não cabe em nenhuma zona UTM sem distorcer |
| `AMC_AREA_ESTUDO_KM2_MAX` | `2000000.0` | ~1/4 do Brasil: acima disso a zona UTM única do centróide perde sentido |
| `AMC_UNIDADES_MAX` | `1000000` | unidades por conjunto (grade ou feições) |
| `AMC_FEICOES_INLINE_MAX` | `20000` | feições por envio síncrono de conjunto do tipo 'feicoes' |
| `AMC_MODELOS_POR_INQUILINO` | `500` | modelos vivos (apagado_em IS NULL) por inquilino |
| `AMC_CONJUNTOS_POR_INQUILINO` | `200` | conjuntos de unidades por inquilino |
| `AMC_VERSOES_POR_MODELO` | `500` | versões de um modelo (cada edição cria uma; imutáveis, nunca apagadas) |
| `AMC_UNIDADES_PAGINA_MAX` | `5000` | unidades por página em GET /api/amc/conjuntos/{id}/unidades |
| `AMC_RESULTADOS_PAGINA_MAX` | `5000` | linhas por página em GET /api/amc/execucoes/{id}/resultados |

## importação de metadado ISO 19139 (L0-09-c-xml-iso-validacao; POST /api/itens/{id}/metadado.xml). O teto

| nome | valor | explicação |
|---|---|---|
| `METADADO_XML_BYTES_MAX` | `2097152` | — |
| `METADADO_XML_ELEMENTOS_MAX` | `20000` | — |
| `METADADO_NAO_COUBE_MAX` | `200` | linhas distintas no relatório do que não coube |

## galeria de mapas base por inquilino (L2-01-e-mapas-base)

| nome | valor | explicação |
|---|---|---|
| `MAPA_BASE_ZOOM_MAX` | `19` | tile.openstreetmap.org não publica além disso |
| `MAPA_BASE_OSM_HOSTS` | `('a.tile.openstreetmap.org', 'b.tile.openstreetmap.org', 'c.tile.openstreetmap.org')` | — |
| `MAPA_BASE_OSM_USER_AGENT` | `'plat-mapa-base/1 (+https://iagrointel.com; contato@iagrosat.com)'` | — |
| `MAPA_BASE_OSM_CACHE_BYTES_MAX` | `104857600` | 100 MiB de teto do cache em disco (disco da casa a 98 %) |
| `MAPA_BASE_OSM_CONECTAR_TIMEOUT_S` | `3.0` | — |
| `MAPA_BASE_OSM_LER_TIMEOUT_S` | `8.0` | — |
| `MAPA_BASE_OSM_RESPOSTA_MAX_BYTES` | `1048576` | 1 MiB: um PNG 256×256 nunca chega perto disso |
| `MAPA_BASE_PMTILES_BYTES_MAX` | `50000000` | — |
| `MAPA_BASE_DISCO_BYTES_MAX` | `154857600` | — |
| `SIMBOLO_SVG_BYTES_MAX` | `65536` | — |
| `SIMBOLO_NOME_MAX` | `64` | — |
| `SIMBOLO_CATEGORIA_MAX` | `40` | — |
| `SIMBOLO_GALERIA_BUSCA_MAX` | `100` | — |

## ferramentas de análise (L2-05-a; L2_CONCEITO C8): job por padrão, síncrono só abaixo do custo declarado

| nome | valor | explicação |
|---|---|---|
| `FERRAMENTA_SINCRONO_CUSTO_MAX` | `5000` | custo = feições × complexidade declarada no manifesto; acima disso só job |
| `FERRAMENTA_JOB_MEMORIA_MB` | `1024` | RLIMIT_DATA do filho que roda uma ferramenta |
| `FERRAMENTA_JOB_TIMEOUT_S` | `1800` | 30 min por execução; ferramenta mais longa é outro tipo de job |
| `BUFFER_DISTANCIA_M_MAX` | `100000` | 100 km: acima disso o buffer geodésico deixa de fazer sentido em camada |

## ferramentas vetoriais elementares (L2-05-b): o teto de feições é por ENTRADA, conferido antes de operar

| nome | valor | explicação |
|---|---|---|
| `VETOR_FEICOES_MAX` | `2000000` | acima disso a ferramenta recusa a entrada em vez de encher o disco |
| `PONTOS_ALEATORIOS_MAX` | `10000` | pontos sorteados por feição em pontos_aleatorios |

## ferramentas de relação entre camadas (L2-05-c): índice espacial, grade e tabela de distâncias

| nome | valor | explicação |
|---|---|---|
| `SUBDIVIDIR_VERTICES` | `256` | ST_Subdivide nas entradas poligonais: partes com até tantos vértices |
| `GRADE_CELULAS_MAX` | `250000` | células que agregar_pontos aceita desenhar antes de recusar o tamanho |
| `DISTANCIAS_PARES_MAX` | `5000000` | pares origem x destino sem vizinhos_por_origem nem distancia_maxima |
| `DISTANCIAS_VIZINHOS_MAX` | `1000` | teto de vizinhos_por_origem na tabela de distâncias |

## grades, densidade, padrões espaciais e interpolação (L2-05-d)

| nome | valor | explicação |
|---|---|---|
| `PADROES_FEICOES_MAX` | `200000` | Gi*, Moran e vizinho mais próximo carregam as coordenadas em memória |
| `H3_NIVEL_MIN` | `5` | níveis aceitos na tesselação H3 (aresta de ~ 8 km a ~ 66 m) |
| `H3_NIVEL_MAX` | `10` | — |
| `DENSIDADE_RAIO_M_MAX` | `100000` | raio do kernel: mesmo teto do buffer geodésico |
| `IDW_VIZINHOS_MAX` | `64` | amostras usadas por célula na interpolação por inverso da distância |
| `CONTORNO_LINHAS_MAX` | `200000` | isolinhas geradas antes de a ferramenta recusar o intervalo |

## ferramentas raster (item L2-05-e) ---------------------------------------------------------------

| nome | valor | explicação |
|---|---|---|
| `FERRAMENTA_RASTER_ZONAS_MAX` | `20000` | feições de uma camada de zonas por execução |
| `FERRAMENTA_RASTER_PIXELS_SAIDA_MAX` | `4000000000` | pixels do raster de saída (4 Gpx) |
| `FERRAMENTA_RASTER_FEICOES_SAIDA_MAX` | `500000` | feições de curva de nível / vetorização por execução |
| `FERRAMENTA_RASTER_ENTRADAS_MAX` | `20` | rasters numa calculadora ou num mosaico |

## ferramentas de rede (L2-05-f): isócrona, rota por paradas, matriz origem-destino, K mais próximas,

| nome | valor | explicação |
|---|---|---|
| `REDE_ISOCRONAS_MAX` | `25` | origens × intervalos por execução de área de serviço |
| `REDE_INTERVALOS_MAX` | `5` | intervalos de tempo por execução (anéis da área de serviço) |
| `REDE_PARADAS_MAX` | `25` | paradas por rota (mesmo teto que a otimização por /trip aguenta bem) |
| `REDE_MATRIZ_LADO_MAX` | `1000` | N e M da matriz origem-destino, cada um |
| `REDE_MATRIZ_PARES_MAX` | `1000000` | N×M declarado (1.000×1.000); o serviço parte em blocos do teto do OSRM |
| `REDE_SNAP_PONTOS_MAX` | `500` | pontos por execução de conectar à rede (1 chamada /nearest por ponto) |
| `REDE_K_MAX` | `20` | K de "K instalações mais próximas" |
| `REDE_ALOCAR_P_MAX` | `25` | P instalações escolhidas por localizar-alocar (heurística gulosa) |

## formulário de coleta por XLSForm (L2-07-b-formulario-de-coleta-xlsform; app/coleta)

| nome | valor | explicação |
|---|---|---|
| `XLSFORM_TAMANHO_MAX` | `2097152` | 2 MiB por planilha (formulários reais têm dezenas de KiB) |
| `FORMULARIO_CAMPOS_MAX` | `500` | perguntas por formulário (mesmo teto de campos da camada) |
| `FORMULARIO_LISTA_MAX` | `5000` | linhas por lista de escolhas (cascata de município cabe) |
| `FORMULARIO_REPETICOES_MAX` | `200` | linhas por repetição numa única resposta |
| `FORMULARIO_ANEXOS_MAX` | `20` | anexos por resposta |

## ------------------------------------------------------------- modelos 3D (item L2-09-c)

| nome | valor | explicação |
|---|---|---|
| `MODELO3D_ARQUIVO_BYTES` | `209715200` | teto do IFC/GLB de entrada; a refutação do item usa 50 MB |
| `MODELO3D_GLB_BYTES` | `314572800` | teto do glTF binário PRODUZIDO pela conversão |
| `MODELO3D_MEMORIA_MB` | `1024` | teto do trabalhador (PLAT_WORKER_MEMORIA_MB): o grafo do IFC |
| `MODELO3D_TIMEOUT_S` | `1800` | — |
| `MODELO3D_NOME_MAX` | `200` | mesmo teto de CHECK(length(nome)<=200) da migração |
| `MODELO3D_ELEMENTOS_PAGINA_MAX` | `500` | elementos por página em GET /api/modelos/{id}/elementos |
| `MODELO3D_PAGINA_MAX` | `200` | modelos por página em GET /api/modelos |

## versionamento por ramo (item L2-13-a): teto de ramos ABERTOS por camada. A camada pode declarar o

| nome | valor | explicação |
|---|---|---|
| `VERSOES_POR_CAMADA_MAX` | `50` | — |
| `VERSAO_NOME_MAX` | `128` | — |

## atualização viva de painel e mapa por SSE (L2-06-d; migração 20260908T0702_camada_eventos_vivos.sql).

| nome | valor | explicação |
|---|---|---|
| `VIVO_SSE_POR_INQUILINO` | `100` | refutação do item: 1.000 conexões têm de bater em 429 |
| `VIVO_SSE_POR_USUARIO` | `10` | uma pessoa não consome sozinha a cota do inquilino |
| `VIVO_SSE_CAMADAS_MAX` | `50` | camadas assinadas por conexão (um painel real usa 2 a 6) |
| `VIVO_SSE_DURACAO_MAX_S` | `1800` | a conexão fecha sozinha em 30 min; o navegador reconecta com Last-Event-ID |
| `VIVO_SSE_KEEPALIVE_S` | `15` | comentário `: keepalive` que impede proxy de derrubar conexão ociosa |
| `VIVO_EVENTO_JANELA_MIN` | `15` | retenção de plat.camada_evento = janela de recuperação da reconexão |
| `VIVO_DEBOUNCE_MS` | `1000` | atraso do navegador antes de refazer a consulta (coalesce de rajada) |

## entrada de eventos em tempo real (item L2-14-a-ingestao-de-fluxos; processo plat-fluxo, porta 8155).

| nome | valor | explicação |
|---|---|---|
| `FLUXO_PORTA` | `8155` | unidade plat-fluxo (deploy/plat-fluxo.service; C14 do L2_CONCEITO) |
| `FLUXO_CORPO_MAX_BYTES` | `4194304` | 4 MiB por pedido do receptor HTTP (e por quadro de WebSocket) |
| `FLUXO_LOTE_MAX` | `20000` | eventos por pedido; 10 mil/s com 2 pedidos/s cabe num lote só |
| `FLUXO_CAMPOS_MAX` | `200` | campos mapeados por fonte (mesma ordem de EDICAO_ATRIBUTOS_MAX) |
| `FLUXO_TEXTO_MAX` | `4096` | caracteres por valor de campo texto |
| `FLUXO_RASTRO_MAX` | `200` | caracteres do id de rastro (refutação: id de 1 MB é recusado) |
| `FLUXO_WKT_MAX` | `4096` | caracteres do WKT de um ponto |
| `FLUXO_URL_MAX` | `2048` | mesma ordem do CHECK de plat.conexao.url |
| `FLUXO_MQTT_TOPICO_MAX` | `500` | filtro de tópico assinado no broker externo |
| `FLUXO_INTEIRO_MAX` | `9007199254740992` | 2^53: acima disso o número não sobrevive ao JSON do navegador |
| `FLUXO_TEMPO_FUTURO_MAX_S` | `300` | 5 min de folga de relógio; além disso o evento é descartado |
| `FLUXO_TEMPO_PASSADO_MAX_DIAS` | `3650` | 10 anos: histórico legítimo passa, lixo com época zerada não |
| `FLUXO_FILA_MAX` | `200000` | eventos na fila em memória do processo antes de descartar (contado) |
| `FLUXO_LOTE_INTERVALO_S` | `1.0` | um lote por segundo (C14) |
| `FLUXO_LOTE_LINHAS_MAX` | `20000` | linhas por INSERT em lote; acima disso o lote é partido |
| `FLUXO_FILTRO_PASSOS_MAX` | `2000` | orçamento do filtro POR EVENTO (o padrão do servidor é 100 mil) |
| `FLUXO_FILTRO_MS` | `50.0` | orçamento de relógio do filtro por evento |
| `FLUXO_BUFFER_PAUSA_S` | `30` | fonte pausada guarda este tanto de segundos de eventos |
| `FLUXO_BUFFER_PAUSA_MAX` | `50000` | ... e nunca mais que isto, mesmo com teto por segundo alto |
| `FLUXO_SONDAGEM_INTERVALO_MIN_S` | `5` | sondar mais rápido que isto é abusar do serviço de terceiro |
| `FLUXO_SONDAGEM_INTERVALO_MAX_S` | `86400` | — |
| `FLUXO_EVENTOS_LISTA_MAX` | `1000` | eventos por página em GET /api/fluxos/{id}/eventos |
| `FLUXO_RECONEXAO_MIN_S` | `1.0` | espera inicial de reconexão do conector (MQTT/WebSocket/AIS) |
| `FLUXO_RECONEXAO_MAX_S` | `60.0` | ... com dobra a cada tentativa, até este teto |
| `FLUXO_MQTT_KEEPALIVE_S` | `60` | keep-alive anunciado no CONNECT do MQTT 3.1.1 |
| `FLUXO_AIS_LINHA_MAX` | `1024` | bytes de uma sentença NMEA (o padrão é 82; a folga é para lixo) |

## GeoParquet particionado no bucket (L2-15-a-geoparquet-bucket-catalogo). Mesmos tetos de memória/tempo/

| nome | valor | explicação |
|---|---|---|
| `GEOPARQUET_MEMORIA_MB` | `1024` | — |
| `GEOPARQUET_TIMEOUT_S` | `3600` | — |
| `GEOPARQUET_DISCO_MIN_LIVRE_BYTES` | `2147483648` | — |
| `GEOPARQUET_FATOR_DISCO` | `3` | — |
| `GEOPARQUET_GRUPO_LINHAS_PADRAO` | `50000` | — |
| `GEOPARQUET_GRUPO_LINHAS_MIN` | `1000` | — |
| `GEOPARQUET_GRUPO_LINHAS_MAX` | `1000000` | — |
| `GEOPARQUET_CAMPOS_MAX` | `500` | — |
| `GEOPARQUET_WHERE_MAX` | `4000` | — |
| `GEOPARQUET_POR_USUARIO_EM_CURSO` | `3` | — |
| `GEOPARQUET_URL_ASSINADA_SEGUNDOS` | `900` | 15 min: o bastante para DuckDB/QGIS/Pro abrirem o arquivo |

## consulta grande sobre Parquet com DuckDB (L2-15-b-consultas-duckdb-em-escala). O motor roda num processo

| nome | valor | explicação |
|---|---|---|
| `CONSULTA_GRANDE_MEMORIA_MB` | `2048` | — |
| `CONSULTA_GRANDE_THREADS` | `4` | — |
| `CONSULTA_GRANDE_TEMPO_S` | `900` | teto do relógio que interrompe a consulta (con.interrupt) |
| `CONSULTA_GRANDE_JOB_TIMEOUT_S` | `1200` | teto do JOB; folgado sobre o teto da consulta para a mensagem chegar |
| `CONSULTA_GRANDE_JOB_MEMORIA_MB` | `3072` | RLIMIT_DATA do filho; o processo do DuckDB é neto e cabe dentro |
| `CONSULTA_GRANDE_LINHAS_SAIDA_MAX` | `2000000` | resultado acima disso é recusado, nunca truncado em silêncio |
| `CONSULTA_GRANDE_SQL_MAX` | `2000` | caracteres do SQL livre: é o teto de GPString do |
| `CONSULTA_GRANDE_ARQUIVOS_MAX` | `4096` | partes Parquet de uma fonte (partição hive fina cabe aqui) |
| `CONSULTA_GRANDE_FONTES_MAX` | `8` | fontes Parquet numa consulta (uma view cada) |
| `CONSULTA_GRANDE_GRADE_METROS_MIN` | `10` | — |
| `CONSULTA_GRANDE_GRADE_METROS_MAX` | `500000` | — |
| `CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB` | `5000000` | acima disto a ferramenta grande é o caminho, não o PostGIS |

## ferramentas por job (L2-16-a-sdk-python-geo): a geometria entra no CORPO do job; o teto abaixo

| nome | valor | explicação |
|---|---|---|
| `FERRAMENTA_GEOJSON_MAX_BYTES` | `5000000` | GeoJSON de entrada por ferramenta (5 MB ≈ 1-2 milhões de vértices) |
| `FERRAMENTA_BUFFER_MAX_M` | `100000.0` | distância de buffer; 100 km já é análise regional, não local |
| `AMC_MATRIZ_PAGINA_MAX` | `2000` | unidades por página em GET /api/amc/execucoes/{id}/matriz (tela do motor |
| `AMC_PREVISAO_VALORES_MAX` | `200000` | valores por chamada de POST /api/amc/transformacoes/previsao (histograma |

## localização semelhante (L3-17-similaridade): pedido é síncrono (sem job), então o teto é o que a

| nome | valor | explicação |
|---|---|---|
| `SIMILARIDADE_UNIDADES_MAX` | `20000` | — |
| `SIMILARIDADE_CAMPOS_MAX` | `50` | — |
| `SIMILARIDADE_REFERENCIAS_MAX` | `500` | — |

## presets do motor multicritério (L3-01-h-presets; migração 20260908T1659_amc_preset.sql):

| nome | valor | explicação |
|---|---|---|
| `AMC_PRESET_FATORES_MAX` | `200` | fatores declarados por preset (mesma ordem do modelo) |
| `AMC_PRESET_FATOR_NOME_MAX` | `120` | nome de fator dentro do preset |
| `AMC_PRESET_DESCRICAO_MAX` | `2000` | mesmo teto de CHECK(length(descricao)<=2000) da migração |
| `AMC_PRESET_UNIDADES_MAX` | `250000` | unidades (linhas da matriz) por aplicação síncrona |

## critérios sobre a própria feição (L3-06-criterios-de-feicao): a avaliação é SÍNCRONA e roda na tela,

| nome | valor | explicação |
|---|---|---|
| `AMC_CRITERIOS_FEICAO_MAX` | `5000` | feições por avaliação síncrona (na tela) |
| `AMC_CRITERIOS_POR_AVALIACAO` | `20` | critérios por avaliação (o painel compara par a par: 20 = 400 células) |
| `AMC_CRITERIO_RAIO_M_MAX` | `100000.0` | 100 km: raio maior que isto não vale numa única zona UTM |
| `AMC_CRITERIO_CAMADA_PONTOS_MAX` | `200000` | pontos por camada auxiliar num pedido (raio, contenção, distância) |

## desempenho em escala do motor multicritério (L3-16-desempenho-escala). Contrato de escala do motor:

| nome | valor | explicação |
|---|---|---|
| `AMC_COMBINAR_NAVEGADOR_MAX` | `50000` | unidades combinadas no navegador; acima disso, servidor |
| `AMC_BLOCO_UNIDADES` | `50000` | unidades por bloco lido/gravado pelo servidor (pico de RAM constante) |
| `AMC_EXTRACAO_MEMORIA_MB` | `4096` | teto DECLARADO do job de extração/recombinação (guardrail do portão do |
| `AMC_EXTRACAO_TIMEOUT_S` | `1800` | 30 min: o prazo do portão para 1 mi de células × 15 fatores |
| `AMC_EXTRACAO_US_POR_UNIDADE_FATOR` | `719` | — |

## malha de parcelas (L4-parcelas-01-modelo-de-parcelas; migração 20260908T2140_parcelas.sql):

| nome | valor | explicação |
|---|---|---|
| `PARCELA_IMPORT_LOTES_MAX` | `50000` | lotes por rodada de import (acima disso: 422, rodada menor) |
| `PARCELA_VALIDACAO_PARES_MAX` | `500` | pares de sobreposição devolvidos por consulta (o total é contado) |
| `PARCELA_TRAJETO_MAX` | `200` | segmentos COGO na criação de UMA parcela por trajeto |
| `PARCELA_DXF_LINHAS_MAX` | `20000` | segmentos de DXF por rodada de "copiar linhas de CAD" |
| `PARCELA_BUILD_LINHAS_MAX` | `20000` | linhas livres por chamada de build |
| `PARCELA_BUILD_FACES_MAX` | `2000` | faces fechadas aceitas em um build (acima: 422, estique a extent) |
| `PARCELA_DIVIDE_PARTES_MAX` | `100` | partes por divisão (EqualArea/ProportionalArea/EqualWidth) |
| `PARCELA_UNIR_MAX` | `50` | parcelas por união (merge) |
| `PARCELA_ATRIBUICAO_MAX` | `1000` | feições por assignFeaturesToRecord |
| `PARCELA_AJUSTE_LINHAS_MAX` | `10000` | linhas observadas numa rede de ajuste LSA (item 03) |
| `PARCELA_QUALIDADE_FACES_MAX` | `500` | faces de lacuna devolvidas pela camada de qualidade |

## pacotes e galeria de modelos (L5-37-pacotes-modelos-entre-inquilinos; migração 20260908T1055).

| nome | valor | explicação |
|---|---|---|
| `PACOTE_DOCUMENTOS_MAX` | `200` | — |
| `PACOTE_PROFUNDIDADE_MAX` | `8` | — |
| `PACOTE_BYTES_MAX` | `4194304` | — |
| `PACOTE_MODELOS_MAX` | `200` | modelos na galeria por inquilino (o de escopo plataforma conta no dele) |
| `PACOTE_NOME_MAX` | `200` | CHECK(length(nome) BETWEEN 1 AND 200) da migração |
| `PACOTE_DESCRICAO_MAX` | `2000` | — |

## site do inquilino (L5-20-sites-paginas-publicas): tetos do documento e do que a página pública consulta

| nome | valor | explicação |
|---|---|---|
| `SITE_PAGINAS_MAX` | `50` | páginas por site (o menu do cabeçalho fica ilegível muito antes disso) |
| `SITE_NOS_MAX` | `400` | nós do documento inteiro (páginas + seções + cartões) |
| `SITE_TEXTO_MAX` | `4000` | caracteres do cartão de texto e do rodapé |
| `SITE_GALERIA_ITENS_MAX` | `60` | teto duro do cartão de galeria e da busca (o mesmo do LIMIT da função SQL) |
| `SITE_GALERIA_ITENS_PADRAO` | `12` | — |
| `SITE_INCORPORADO_ALTURA_MIN` | `120` | — |
| `SITE_INCORPORADO_ALTURA_MAX` | `1200` | — |

## edição transacional de feições (L2-03-a-api-edicao-transacional; POST /api/camadas/{id}/edicoes, única

| nome | valor | explicação |
|---|---|---|
| `EDICAO_LOTE_MAX` | `2000` | — |
| `EDICAO_ATRIBUTOS_MAX` | `500` | campos por feição num único pedido (mesmo teto de INGESTAO_CAMPOS_MAX) |
| `EDICAO_TEXTO_MAX` | `65536` | 64 KiB por valor de campo texto (mesma ordem de ITEM_DESCRICAO_MAX) |
| `EDICAO_REGRA_CAMPO_MAX` | `500` | entradas em dados.regras_campo (mesmo teto de campos da camada) |
| `EDICAO_DOMINIO_VALORES_MAX` | `1000` | valores aceitos por regra de domínio codificado |
| `EDICAO_SRID_MAX` | `999999` | mesmo teto do esquema de camada_vetorial (029_ingestao_vetor.sql) |

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

## construtor de formulário de atributos, arrasta-e-solta (item L5-03-form-builder): uma camada tem no

| nome | valor | explicação |
|---|---|---|
| `FORMULARIO_GRUPOS_MAX` | `40` | — |
| `FORMULARIO_CAMPOS_POR_GRUPO_MAX` | `60` | — |
| `FORMULARIO_DESENHO_BYTES_MAX` | `524288` | jsonb bruto (nome+rótulo+expressões de até 60x40 campos cabe longe disso) |
| `FORMULARIO_VERSOES_MAX` | `200` | rascunhos guardados por formulário (histórico do construtor) |

## telemetria da rede de utilidades (item L4-13-integracao-telemetria): leitura ligada ao ativo,

| nome | valor | explicação |
|---|---|---|
| `REDE_MEDICAO_LOTE_MAX` | `2000` | leituras por POST /api/rede/medicao/leituras |
| `REDE_MEDICAO_JANELA_FUTURO_S` | `120` | tolerância de relógio do sensor (refutação "timestamp futuro") |
| `REDE_MEDICAO_SERIE_DIAS_PADRAO` | `7` | janela padrão do gráfico da ficha do ativo |
| `REDE_MEDICAO_SERIE_DIAS_MAX` | `92` | mesmo teto de LOG_JANELA_DIAS |
| `REDE_MEDICAO_SERIE_PONTOS_MAX` | `20000` | linhas devolvidas por série (amostragem simples acima disso) |
| `REDE_MEDICAO_ALARME_JANELA_MIN` | `30` | "carregamento > 100% por 30 min" (portão do item) |
| `REDE_MEDICAO_ALARME_LOOKBACK_MIN` | `90` | quanto de histórico o motor olha para achar o início do surto |
