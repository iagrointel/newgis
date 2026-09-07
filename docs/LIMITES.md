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

## exportação de camada (L0-04-h-exportar; ADR 0018). Os tempos e tetos abaixo saem de MEDIÇÃO nesta

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
