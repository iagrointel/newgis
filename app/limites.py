"""Limites e faixas da plataforma, um lugar só (ADR 0002 seção 11; docs/LIMITES.md do L0-12 é gerado daqui).
Cada trilha acrescenta a sua seção abaixo da anterior; nenhuma edita a seção de outra."""

# --- identidade (L0-02)
# política de senha, sessão, bloqueio e token: (padrão, mínimo, máximo) por chave de tenant.config.auth
AUTH_PADROES: dict[str, tuple] = {
    # padrão 10 (a hipótese do item L0-02-b, e o que o portão declara); 8 continua sendo o PISO configurável,
    # que é também o mínimo do NIST SP 800-63B §3.1.1.2 para senha escolhida pelo usuário. Era (8, 8, 64):
    # achado G1-b1 do adversário do turno 3, portão e código divergindo.
    "senha_min": (10, 8, 64),
    "senha_maiuscula": (False, None, None),
    "senha_minuscula": (False, None, None),
    "senha_simbolo": (False, None, None),
    "senha_historico": (5, 0, 24),
    "senha_expira_dias": (0, 0, 365),  # 0 = nunca; fora de 0 a faixa válida é 30–365 (politica.py corta)
    "bloqueio_tentativas": (5, 3, 10),
    "bloqueio_minutos": (15, 5, 60),
    "sessao_ociosa_horas": (12, 1, 24),
    "sessao_max_dias": (7, 1, 30),
    "exigir_2fa": (False, None, None),
    "token_max_dias": (365, 1, 365),
    "token_padrao_dias": (90, 1, 365),
    "dominios_email": ([], 0, 20),
    "compartilhar_publico": (False, None, None),
}
SENHA_MAX = 128  # fixo: pbkdf2 sobre 128 bytes evita DoS por senha longa
SENHA_EXPIRA_MIN_DIAS = 30
BLOQUEIO_JANELA_MIN = 15  # fixo (ADR 0002 seção 6.2)
DESAFIO_2FA_MIN = 5
TOTP_JANELA_PASSOS = 1
CODIGOS_RECUPERACAO = 8
SENHA_TEMPORARIA_TAMANHO = 12
TOKEN_PREFIXO_TAMANHO = 8  # "plat_" + 3 do segredo; o portão do L0-02-d declara 8 (achado G1-d1)
TOKENS_POR_USUARIO = 20
CAMPO_MAPAS_MAX = 200  # item L2-07-a-pwa-instalavel-cache: teto do que /api/campo/mapas devolve por chamada
GRUPOS_POR_USUARIO = 512
GRUPO_TAGS_MAX = 50
GRUPO_NOME_MAX = 128
GRUPO_RESUMO_MAX = 2048
PAPEL_NOME_MAX = 128
PAPEL_DESCRICAO_MAX = 250
LOTE_MAX = 100
LOG_JANELA_DIAS = 92
LOG_LIMITE_MAX = 1000
LOG_CSV_MAX = 100_000
LOG_RETENCAO_MESES = 12
# --- trilha de auditoria (L7-20). Padrão de 2 anos porque a trilha responde por ATO DE NEGÓCIO, não por
# requisição: o log de acesso continua com 12 meses. O PISO de 90 dias não é conforto — é o que impede o
# administrador do inquilino de encolher a retenção até apagar a própria trilha (refutação do item).
AUDITORIA_RETENCAO_PADRAO_DIAS = 730
AUDITORIA_RETENCAO_MIN_DIAS = 90
AUDITORIA_RETENCAO_MAX_DIAS = 3650
AUDITORIA_EXPORTA_MAX = 100_000
PAGINA_PADRAO = 50
PAGINA_MAX = 1000
RESTRICAO_MAX = 20
TOKEN_ROTACAO_HORAS = 24

# --- catálogo (L0-03; ADR 0004 seção 14)
ITEM_TITULO_MAX = 250
ITEM_RESUMO_MAX = 2048  # snippet da Esri, limite literal
ITEM_DESCRICAO_MAX = 65536
ITEM_CREDITOS_MAX = 2048
ITEM_TAGS_MAX = 50
TAG_MAX = 128
ITEM_CATEGORIAS_MAX = 20
METADADO_ISO_BYTES_MAX = 1 * 1024 * 1024  # item L0-09-b-editor-iso-mgb: refutação exige recusar 5 MB (limite 1 MB)
CATEGORIAS_POR_INQUILINO = (200, 50, 900)  # (padrão, mínimo, máximo) em tenant.config.catalogo.categorias_max
CATEGORIA_NIVEIS = 3
CATEGORIA_NOME_MAX = 100
PASTA_PROFUNDIDADE_MAX = 5
PASTA_NOME_MAX = 128
MINIATURA_BYTES_MAX = 10 * 1024 * 1024
MINIATURA_PIXELS_MAX = 25_000_000
MINIATURA_LARGURA = 600
MINIATURA_ALTURA = 400
LINKS_POR_ITEM = 100
LINK_VALIDADE_MAX_DIAS = 365
LINK_TOKEN_BYTES = 32  # 64 hex
RELACOES_POR_ORIGEM = 5000
RELACOES_POR_DESTINO = 50000
RELACAO_PROFUNDIDADE_MAX = 20
VERSOES_VIVAS = 50
VERSOES_BLOCO_COMPACTACAO = 10
VERSAO_COMENTARIO_MAX = 500
FAVORITOS_POR_USUARIO = 500
# notificações internas (L0-03-k): dedup por chave no banco; teto por minuto por usuário contra enxurrada
# de uma origem só (refutação "10 mil notificações para um usuário em 1 min"); expurgo por idade
NOTIFICACOES_POR_MINUTO = 60
NOTIFICACOES_DIAS = 90
NOTIFICACOES_PAGINA_MAX = 100
DESTAQUES_POR_GRUPO = 24
BUSCA_Q_MAX = 1000
BUSCA_TERMOS_MAX = 200
BUSCA_TRGM_LIMIAR = 0.3
BUSCA_REFORCO_STATUS = 0.25
ITENS_PAGINA_MAX = 200
ITENS_DESLOCAMENTO_MAX = 10_000
LIXEIRA_DIAS = 30
RASTER_LIXEIRA_DIAS = 7  # retenção da lixeira do item de IMAGEM: os objetos ficam no balde 7 dias após a
# exclusão (janela de restauração); depois o job imagens.raster_apagar_objetos libera o espaço (L1-01-i)
COTA_ITENS = 100_000  # padrão por inquilino, tenant.config.catalogo.cota_itens
USADO_POR_PROFUNDIDADE_MAX = 5

# --- publicação de documento de construtor (L5-14-publicacao-links-embed)
PUBLICACAO_SLUG_MIN = 2
PUBLICACAO_SLUG_MAX = 60
PUBLICACAO_DOMINIOS_MAX = 20
PUBLICACAO_CAMADAS_PROFUNDIDADE = 4  # app -> mapa -> camada; folga para um nível extra de vista_de_camada
PUBLICACAO_VISUALIZACOES_DIAS_MAX = 366

# --- contrato de API e limites transversais (L0-12; docs/CONTRATO_API.md e docs/LIMITES.md nascem daqui)
CORPO_MAX_PADRAO_BYTES = 10 * 1024 * 1024        # 10 MiB; toda rota /api,/svc,/ogc,/tiles fora da lista de upload
CORPO_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB (hipótese do item); sem rota isenta ainda (upload = L1-01-e)

# --- arquivos/objetos (L0-11; ADR 0006). PLAT_ARQUIVO_BYTES_MAX bem abaixo de CORPO_MAX_UPLOAD_BYTES de propósito:
# MEDIDO 06/09/2026, `df -h /` = 12 GiB livres (98% cheio) onde o Garage grava — um teto de 2 GiB por objeto
# encheria o disco em poucos envios; 512 MiB é o teto ATÉ o disco crescer (revisar junto do L1-01-e, que herda
# CORPO_MAX_UPLOAD_BYTES para raster). A parte (chunk) do multipart é fixa e NÃO cresce com o arquivo: o envio
# nunca bufferiza mais que ARQUIVO_PARTE_BYTES de RAM, mesmo para um objeto no teto (streaming, ver app/objetos.py)
ARQUIVO_BYTES_MAX = 512 * 1024 * 1024
ARQUIVO_PARTE_BYTES = 8 * 1024 * 1024            # 8 MiB por parte S3 (mínimo do protocolo é 5 MiB, exceto a última)
ARQUIVO_BUFFER_UNICO_BYTES = ARQUIVO_PARTE_BYTES  # até aqui: 1 PUT só, sem abrir multipart

# --- upload retomável (L0-04-a-upload-arquivo; ADR 0005 seção 3): parte de 16 MiB fixa (não cresce com o
# arquivo — cada PUT bufferiza no máximo isto de RAM); teto de 2 GiB por arquivo nesta fase (hipótese do item;
# a Esri aceita 500 GB — ampliar é mudar UPLOAD_BYTES_MAX e reindexar; 24 h é o prazo do periódico de expurgo,
# reaproveitando o padrão de `jobs.expurgo`/`jobs.sessoes_expurgar` do L0-05).
UPLOAD_BYTES_MAX = 2 * 1024 * 1024 * 1024   # 2 GiB
UPLOAD_PARTE_BYTES = 16 * 1024 * 1024       # 16 MiB (ADR 0005 seção 3.1; distinto de ARQUIVO_PARTE_BYTES acima,
                                             # que é do caminho de streaming server-driven do L0-11)
UPLOAD_EXPIRA_HORAS = 24
UPLOAD_NOME_MAX = 255

# --- upload grande retomável (L1-01-e; ADR 20260908T1600): o corpo de `PUT /api/uploads/{id}/partes/{n}` NUNCA
# é acumulado em memória — ele é escrito em fluxo no disco de trabalho (`app.uploads.disco`) em pedaços de
# UPLOAD_PEDACO_BYTES e só depois enviado ao Garage a partir do arquivo. Logo o pico de memória do processo que
# recebe não cresce com o tamanho do arquivo nem com o número de envios simultâneos: é UPLOAD_PEDACO_BYTES por
# requisição em curso, não UPLOAD_PARTE_BYTES. UPLOAD_RAM_MAX_MB é o teto declarado para o processo da API/worker
# que recebe partes (a medida de pico com envios simultâneos é registrada em tests/medidas/L1-01-e-*.json).
UPLOAD_PEDACO_BYTES = 1024 * 1024            # 1 MiB por leitura do socket e escrita no disco de trabalho
UPLOAD_DISCO_LIVRE_MIN_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB livres exigidos no disco de trabalho, além da parte
UPLOAD_RAM_MAX_MB = 512                      # teto declarado de pico de memória do processo que recebe partes
UPLOAD_CABECALHO_INICIO_BYTES = 65536        # bytes da parte 1 usados para recusar tipo errado antes do fim

# --- rede de rota (L2-11-c): OSRM isolado `plat-osrm-guarulhos` (:5010; recorte de teste ≤ 50 MB — nunca os
# OSRM de outras frentes da casa em 5000-5003); PLAT_ROTA_MATRIZ_MAX/PLAT_ROTA_ISOCRONA_MAX_PONTOS no .env
# sobrepõem os padrões abaixo (settings.py). ROTA_MATRIZ_MAX_PADRAO bate com --max-table-size do container.
ROTA_MATRIZ_MAX_PADRAO = 625            # N×M <= isto por pedido de /api/matriz
ROTA_ISOCRONA_MAX_PONTOS_PADRAO = 400   # pontos de grade por pedido de /api/isocrona (1 fonte + N destinos)
ROTA_PERFIS = ("carro",)                # só car.lua está carregado nesta instância de teste (D-osrm-perfis)
ROTA_MINUTOS_MAX = 180                  # 3 h; acima disso o polígono satura no limite do recorte de teste
ROTA_ISOCRONA_RATIO_PADRAO = 0.3        # parâmetro do casco côncavo (shapely.concave_hull); 0 = casco convexo

# --- LDAP/Active Directory (L0-08-d; app/auth/ldap.py): provedor externo por inquilino, sem servidor de
# sistema (ldap3 puro Python). Os tempos são curtos de propósito: "diretório fora do ar não derruba o login
# local" (portão do item) exige que a tentativa de bind desista rápido, nunca prenda a requisição
LDAP_TIMEOUT_S = 5                  # connect_timeout e receive_timeout do ldap3 (bind de serviço e bind do usuário)
LDAP_BUSCA_MAX = 1                  # a busca por login casa EXATAMENTE 1 entrada; 0 ou 2+ = credenciais inválidas
LDAP_IMPORTAR_MAX = 2000            # tamanho máximo de uma importação de grupo em massa (POST /api/org/ldap/importar)
# contador de força bruta contra o bind LDAP: em memória de processo, por (tenant_id, login), reaproveitando
# AUTH_PADROES["bloqueio_tentativas"/"bloqueio_minutos"] do MESMO inquilino (nunca um número novo aqui) — vale
# inclusive para login que ainda não existe localmente (o adversário do item testa exatamente 1.000 binds/min)

# --- SSO OIDC/SAML 2.0 (L0-08-sso; app/auth/sso.py): login federado por inquilino, sem biblioteca de SAML
# (validação XML-DSig própria sobre lxml+cryptography — signxml exigiria trocar a versão de lxml/cryptography
# do ambiente, trocada que o laço proíbe). Tempos curtos de propósito: provedor fora do ar nunca prende a
# requisição nem derruba o login local (portão do item)
SSO_TIMEOUT_S = 5                # timeout de TODA chamada HTTP ao IdP (descoberta, JWKS, troca de código)
SSO_TRANSACAO_MINUTOS = 10       # validade do state/nonce/PKCE (OIDC) e do pedido (SAML) em plat.sso_transacao
SSO_DESVIO_RELOGIO_S = 60        # folga de relógio aceita em exp/iat (OIDC) e NotBefore/NotOnOrAfter (SAML)
SSO_DESCOBERTA_CACHE_S = 600     # cache em memória do documento de descoberta OIDC e das chaves JWKS
SSO_RESPOSTA_MAX = 262144        # teto do corpo SAMLResponse decodificado (256 KB; assertion típica < 30 KB)

# --- conexão externa e SSRF (L6-02-a-modelo-conexao-e-seguranca; app/conexao/): modelo genérico de conexão
# a serviço externo (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles — só o MODELO nesta trilha, os
# conectores em si são itens futuros). Tempos curtos de propósito: o teste de saúde nunca prende a requisição
# e o proxy nunca vira um jeito de esgotar a máquina com um serviço lento de propósito (ADR 0012).
CONEXAO_TIPOS = (
    "wms", "wmts", "wfs", "ogc_api", "esri_rest", "stac", "geoparquet", "pmtiles", "xyz", "postgres_fdw", "s3", "http",
    "wms", "wmts", "wfs", "ogc_api", "esri_rest", "stac", "geoparquet", "pmtiles", "postgres_fdw", "s3", "http",
    "odk_central",
    # item L6-02-i-google-sheets: planilha do Google como fonte (publicada = exportação CSV sem credencial;
    # privada = JSON de conta de serviço, trocado por access token na leitura — app/conexao/google_sheets.py)
    "google_sheets",
)
CONEXAO_MODOS = ("referenciada", "copiada")
CONEXAO_NOME_MAX = 200
CONEXAO_URL_MAX = 2048
CONEXAO_CONFIG_MAX_BYTES = 8192          # tamanho máximo do JSON de `config` (json.dumps, utf-8)
CONEXAO_DNS_TIMEOUT_S = 3.0              # socket.getaddrinfo (validação do host antes de qualquer conexão)
CONEXAO_CONECTAR_TIMEOUT_S = 3.0
CONEXAO_LER_TIMEOUT_S = 6.0              # teste de saúde: curto de propósito (POST /api/conexoes/{id}/testar)
CONEXAO_REDIRECT_MAX = 5                 # cada hop é revalidado do zero (host novo pode ser interno)
CONEXAO_RESPOSTA_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB: o teste de saúde confere status/corpo curto
                                                # (nunca baixa o serviço inteiro)

# --- conectores de feição externa WFS 2.0 / OGC API - Features (L6-02-c-wfs-ogcapi; app/conexao/vetor_externo.py
# e app/conexao/copia.py). Os tetos existem para o caso do adversário do item: serviço que declara 5 milhões de
# feições e ignora a paginação. Nenhum deles é negociado com o serviço — quem decide é a plataforma.
CONEXAO_VETOR_LER_TIMEOUT_S = 30.0            # página de feições é maior que o teste de saúde (6 s),
                                              # mas nunca ilimitada
CONEXAO_VETOR_METADADO_MAX_BYTES = 32 * 1024 * 1024  # GetCapabilities/DescribeFeatureType/collections.
                                              # MEDIDO 06/09/2026: o GetCapabilities do GeoServer do IBGE
                                              # (geoservicos.ibge.gov.br/geoserver/ows) tem 11.602.903 bytes
                                              # em 2,3 s — 8 MiB recusava um serviço público legítimo.
CONEXAO_VETOR_PAGINA_MAX_BYTES = 48 * 1024 * 1024    # corpo de UMA página de feições
CONEXAO_VETOR_PAGINA_PADRAO = 1000            # feições por página quando quem chama não escolhe
CONEXAO_VETOR_PAGINA_MAX = 10_000             # teto do que se pede por página (COUNT / limit)
CONEXAO_VETOR_PAGINAS_MAX = 2_000             # teto de requisições de UMA cópia (com 10 mil/página dá 20 mi)
CONEXAO_VETOR_LIMITE_PADRAO = 100_000         # feições que a cópia aceita quando quem chama não declara
CONEXAO_VETOR_LIMITE_MAX = 2_000_000          # teto absoluto do limite declarável numa cópia
CONEXAO_VETOR_PREVIA_MAX = 1000               # feições que a consulta REFERENCIADA devolve por vez
CONEXAO_VETOR_CACHE_TTL_S = 30.0              # cache curto da consulta referenciada (item: "cache curto")
CONEXAO_VETOR_CACHE_ENTRADAS = 128            # entradas guardadas no processo; a mais velha sai
COPIA_MEMORIA_MB = 1024                       # job conexao.copiar_vetor (ogr2ogr + reprojeção)
COPIA_TIMEOUT_S = 3600
# --- fonte de dado registrada: conector postgres_fdw (L0-04-i-fonte-registrada; ver
# docs/adr/20260907T0148-fonte-registrada-postgres-fdw.md). Conexão TCP direta
# a um Postgres/PostGIS de cliente (não HTTP: `pgfdw.py` reusa `seguranca.resolver_ips_bloqueando_categorias`,
# nunca `buscar_seguro`). Diferente do bloqueio de SSRF de `CONEXAO_TIPOS` http-like, aqui só link_local/
# multicast/nao_especificado são bloqueados por categoria de IP (uma rede privada/VPN é um alvo LEGÍTIMO para
# o Postgres de um cliente); o próprio iagro_sat é bloqueado por LISTA EXPLÍCITA (nome do banco + host/porta/
# banco do PLAT_DSN desta própria instalação), não por faixa de IP — ver `pgfdw.validar_alvo`.
CONEXAO_PG_CATEGORIAS_BLOQUEADAS = frozenset({"link_local", "multicast", "nao_especificado"})
CONEXAO_PG_BANCOS_PROIBIDOS = frozenset({"iagro_sat"})  # nome do banco de produção da casa, em qualquer host
CONEXAO_PG_CONECTAR_TIMEOUT_S = 5
CONEXAO_PG_ESTATEMENT_TIMEOUT_MS = 8000       # listar tabelas/colunas nunca trava a rota
CONEXAO_PG_TABELAS_MAX = 500                  # teto de tabelas devolvidas por GET .../tabelas
CONEXAO_PG_COLUNAS_MAX = 300                  # teto de colunas por tabela publicada
CONEXAO_PG_PUBLICAR_LOTE_MAX = 50             # teto de tabelas por chamada de publicar-em-massa
# --- agendamento de camada copiada (L6-02-k-agendamento; app/conexao/tarefas_agendamento.py): não é outro
# relógio, reusa plat.agenda/app/jobs/agenda.py (intervalo mínimo 15 min já em INTERVALO_MINIMO_S de lá).
CONEXAO_COPIA_MAX_BYTES = 8 * 1024 * 1024        # bem maior que o teste de saúde, mas pequeno de propósito
                                                   # (disco a 98% nos dois servidores, D21 do laço)
# --- PMTiles/XYZ/TileJSON (L6-02-g-pmtiles-xyz-tilejson; app/conexao/ladrilhos.py): dois `CONEXAO_TIPOS` novos
# (pmtiles já existia no vocabulário desde a 030, sem conector; xyz é novo). Regra da hipótese: PMTiles só entra
# se o servidor honra `Range`/206 de verdade (byte de cabeçalho lido AGORA, na criação — nunca um palpite);
# XYZ/TileJSON exigem zoom mínimo/máximo e atribuição DECLARADOS pelo usuário no `config` (nenhum dos dois
# protocolos tem metadado padronizado sondável, ver app/conexao/proveniencia.py).
CONEXAO_PMTILES_RANGE_BYTES = 16 * 1024  # bytes pedidos no Range de prova (cobre o cabeçalho fixo do PMTiles v3,
                                          # 127 bytes, com folga generosa para o directory raiz)
CONEXAO_TILE_ZOOM_MAX = 24               # teto de bom senso (WebMercator raramente passa de 22-23 na prática)
CONEXAO_ATRIBUICAO_MAX = 500             # `config.atribuicao`: texto curto de legenda, nunca um parágrafo
# --- ArcGIS REST externo (L6-02-d-arcgis-rest-externo; ADR 0020): FeatureServer (query paginado),
# MapServer (export dinâmico) e ImageServer (exportImage) de Portal/AGOL de terceiro. `maxRecordCount`
# do serviço é sempre respeitado (nunca pedimos mais do que ele aceita); quando o serviço declara um valor
# hostil (ex.: 1) ou nunca fecha `exceededTransferLimit`, os tetos abaixo evitam laço infinito — a página é
# sempre gravada como aviso de procedência, nunca um erro silencioso.
ESRI_REST_TIMEOUT_S = 15.0                        # descrição do serviço (?f=json) e cada página de query
ESRI_REST_IMAGEM_TIMEOUT_S = 20.0                 # export/exportImage: pode gerar imagem grande no servidor
ESRI_REST_DESCRICAO_MAX_BYTES = 5 * 1024 * 1024   # 5 MiB: JSON de descrição do serviço/camada
ESRI_REST_PAGINA_MAX_BYTES = 8 * 1024 * 1024      # 8 MiB: uma página de feições (geojson/pbf)
ESRI_REST_MAX_RECORD_COUNT_PADRAO = 1000          # quando o serviço não declara `maxRecordCount`
ESRI_REST_PAGINAS_MAX = 50                        # teto de segurança mesmo com maxRecordCount hostil (ex.: 1)
ESRI_REST_FEICOES_MAX = 20000                     # teto de segurança do modo referenciado (consulta ao vivo)
ESRI_REST_IMAGEM_MAX_BYTES = 8 * 1024 * 1024      # 8 MiB: uma única imagem export/exportImage
ESRI_REST_IMAGEM_LADO_MAX = 2048                  # largura/altura máximas pedidas ao serviço (px)
# --- WMS/WMTS externo (L6-02-b-wms-wmts): GetCapabilities pode ser grande (catálogo com centenas de camadas);
# o teto abaixo é DELIBERADAMENTE maior que CONEXAO_RESPOSTA_MAX_BYTES (a de saúde, que só confere status) mas
# ainda finito — o adversário do item manda 40 MiB de propósito, e a resposta certa é recusar com motivo, nunca
# carregar tudo em memória. defusedxml nunca resolve entidade externa (XXE), independente do tamanho.
CONEXAO_WMS_CAPACIDADES_MAX_BYTES = 20 * 1024 * 1024   # 20 MiB
CONEXAO_WMS_CAPACIDADES_TIMEOUT_S = 15.0
CONEXAO_WMS_MAPA_MAX_BYTES = 8 * 1024 * 1024           # 8 MiB: uma única imagem GetMap/tile, nunca um mosaico
CONEXAO_WMS_MAPA_TIMEOUT_S = 20.0
CONEXAO_WMS_FEICAO_MAX_BYTES = 2 * 1024 * 1024         # 2 MiB: resposta de GetFeatureInfo (texto/GML/JSON)
CONEXAO_WMS_LARGURA_MAX = 2048
CONEXAO_WMS_ALTURA_MAX = 2048
CONEXAO_WMTS_TILE_MAX_BYTES = 4 * 1024 * 1024          # 4 MiB: um único tile (256/512 px), nunca a pirâmide
# --- ponte com o ODK Central (L2-07-e-odk-central-ponte; app/odk/): conexão do tipo `odk_central`, publicação do
# XLSForm e leitura dos envios por OData. Os tempos são maiores que os do teste de saúde porque aqui há
# transferência de verdade (planilha, página de envios, anexo), e continuam pequenos o bastante para o job não
# prender o worker: quem tem muito envio pagina, não espera uma resposta gigante.
ODK_LER_TIMEOUT_S = 30.0
ODK_PAGINA_ENVIOS = 100                    # $top do OData por página (o Central aceita até 1000; 100 é o padrão dele)
ODK_ENVIOS_MAX_POR_EXECUCAO = 1000         # teto de envios lidos numa sincronização (o resto fica para a próxima)
ODK_PAGINAS_MAX = 50                       # trava contra paginação que nunca termina (página sempre cheia)
ODK_RESPOSTA_MAX_BYTES = 8 * 1024 * 1024   # página de OData / lista de entidades
# a planilha publicada é a MESMA que a importação aceita (XLSFORM_TAMANHO_MAX) e o anexo puxado é o mesmo que a
# API de anexo aceita (ANEXO_TAMANHO_MAX): dois tetos para a mesma coisa deixariam passar aqui o que a outra
# porta recusa, e o envio só quebraria depois de baixado.
ODK_ENTIDADES_MAX = 5000                   # entidades lidas de um dataset para virar lista de escolhas
# --- arquivo por URL (L6-02-h-csv-url-geojson-kml; app/conexao/arquivo_url.py): CSV/GeoJSON/KML/KMZ/GeoRSS/GPX
# baixados de uma URL pública pela MESMA `app.conexao.seguranca.buscar_seguro` do teste de saúde (nunca um
# cliente HTTP próprio), convertidos para GeoJSON quando o formato não é um dos 4 que a ingestão do L0-04 já
# lê, e carregados pelo pipeline de importação existente.
CONEXAO_ARQUIVO_FORMATOS = ("csv", "geojson", "kml", "kmz", "georss", "gpx")
CONEXAO_ARQUIVO_MAX_BYTES = 64 * 1024 * 1024   # teto geral do download (mesmo teto de GeoJSON do ADR 0005)
# MEDIDO nesta máquina (06/09/2026, GDAL 3.8.4): KML de 200 mil pontos = 35,5 MB de arquivo -> `ogr2ogr -f
# GeoJSON` gasta 2,42 s e 417 MiB de RSS (razão ~12x o tamanho do arquivo, porque o driver KML/GPX/GeoRSS lê o
# documento XML inteiro na memória). Com o teto geral de 64 MiB o pico passaria de 780 MiB e estouraria o
# RLIMIT do job (INGESTAO_MEMORIA_MB=768). Por isso os formatos XML têm teto PRÓPRIO, menor:
CONEXAO_ARQUIVO_XML_MAX_BYTES = 40 * 1024 * 1024   # ~480 MiB de pico medido, dentro do orçamento do job
CONEXAO_ARQUIVO_LER_TIMEOUT_S = 60.0           # baixar arquivo é mais lento que testar saúde (6 s lá)
CONEXAO_ARQUIVO_INTERVALO_MIN_S = 900          # atualização agendada: 15 min é o mínimo do agendador (L0-05)
CONEXAO_ARQUIVO_INTERVALO_PADRAO_S = 86400     # padrão: uma vez por dia
CONEXAO_ARQUIVO_INTERVALO_MAX_S = 30 * 86400
CONEXAO_ARQUIVO_LOTE_PERIODICO = 20            # conexões sincronizadas por execução do periódico
# faixas de coordenada geográfica: usadas para RECUSAR (nunca para corrigir sozinho) CSV com latitude e
# longitude trocadas — ver `app/conexao/arquivo_url.py::conferir_faixa_coordenada`.
CONEXAO_ARQUIVO_LAT_MAX = 90.0
CONEXAO_ARQUIVO_LON_MAX = 180.0
# --- descoberta de camada (item L6-02-conectores-vivos; app/conexao/descoberta.py): GetCapabilities de um
# GeoServer nacional pode ser grande de verdade (o do IBGE mede 11.602.903 bytes, achado do T3) — teto maior
# e timeout mais folgado que o teste de saúde, mas ainda finito (nunca "baixa até acabar").
CONEXAO_DESCOBERTA_MAX_BYTES = 24 * 1024 * 1024   # 24 MiB
CONEXAO_DESCOBERTA_TIMEOUT_S = 15.0
CONEXAO_DESCOBERTA_CAMADAS_MAX = 2000              # teto de linhas gravadas por descoberta (corta, não trava)

# --- proxy de tile/imagem por conexão cadastrada (mesmo item): generaliza `app/mapa/proxy_wms.py` (allowlist
# fixa de 3 fontes públicas) para "as fontes que o inquilino cadastrou" em `plat.conexao`. Só wms/wmts/esri_rest
# têm operação de tile/imagem (wfs/ogc_api são API de feição, não de raster — L6-02-c, fora deste proxy).
CONEXAO_PROXY_TIPOS = ("wms", "wmts", "esri_rest")
CONEXAO_PROXY_CONECTAR_TIMEOUT_S = 3.0
CONEXAO_PROXY_LER_TIMEOUT_S = 20.0                 # uma base pública lenta não pode travar o mapa de quem espera
CONEXAO_PROXY_MAX_BYTES = 12 * 1024 * 1024         # 12 MiB: teto de 1 tile/imagem (ortofoto 10-20 cm inclusa)
CONEXAO_PROXY_CACHE_TTL_S = 600                    # mesmos 10 min do proxy público de hoje
CONEXAO_PROXY_CACHE_MAX_ITENS = 500                # cache em processo; LRU simples por ordem de inserção

# --- ingestão vetorial (L0-04; ADR 0005, reduzido a 4 formatos: shapefile.zip, gpkg, geojson, csv)
INGESTAO_AMOSTRA_VALIDADE = 1000          # feições lidas na amostra de ST_IsValid (ogr2ogr -limit, MEDIDO no ADR)
INGESTAO_MEMORIA_MB = 768                 # job ingestao.inspecionar (cobre GeoJSON de 64 MiB, ADR seção 0.4)
INGESTAO_TIMEOUT_S = 300
CARGA_MEMORIA_MB = 1024                   # job ingestao.carregar (ogr2ogr + ST_MakeValid)
CARGA_TIMEOUT_S = 3600
CARGA_FATOR_COTA = 3                      # estimativa = bytes do arquivo × 3 (MEDIDO: shapefile 14 MB -> tabela 45 MB)
INGESTAO_CAMPOS_MAX = 500                 # mesmo teto do JSON Schema de camada_vetorial (ADR 0004/0005)
INGESTAO_FIDS_RELATORIO_MAX = 1000        # fids corrigidos listados no relatório de ST_MakeValid
# camada de 1 ponto: a envoltória tem largura zero e o polígono correspondente é inválido (o CHECK
# item_extent_check de plat.item recusa). O lado nulo é afastado deste tanto, em graus (~1 cm no equador);
# só afeta o retângulo guardado no item, nunca a geometria da feição.
INGESTAO_EPSILON_ENVOLTORIA = 1e-7

# --- intercâmbio de formatos em lote (L6-02-o): exportação por camada nos formatos extra, escrow do inquilino
# em GeoPackage + manifesto JSON e importação em lote, em app/intercambio/
INTERCAMBIO_EXPORTACAO_BYTES_MAX = 2 * 1024 * 1024 * 1024   # 2 GiB: pacote final guardado no Garage
INTERCAMBIO_DISCO_FOLGA = 3               # disco livre exigido = estimativa do pacote × 3 (disco a 98%)
INTERCAMBIO_CAMADAS_ESCROW_MAX = 500      # teto de camadas vetoriais num escrow (job único, timeout 3600 s)
INTERCAMBIO_XLSX_LINHAS_MAX = 500_000     # importação XLSX: acima disso a conversão p/ CSV estoura a memória
INTERCAMBIO_DBF_LARGURA_MAX = 254         # largura máxima de campo texto em DBF (limite do formato)
INTERCAMBIO_MVT_ZOOM = 14                 # zoom de geração/leitura de mbtiles/pmtiles (declarado no relatório)
INTERCAMBIO_MEMORIA_MB = 1024             # job intercambio.exportar_camada / exportar_inquilino / importacoes_lote
INTERCAMBIO_TIMEOUT_S = 3600              # relógio do job de intercâmbio (EXPORTACAO_TIMEOUT_S é do L0-04-h)
INTERCAMBIO_LOTE_ITENS_MAX = 200          # teto de arquivos/camadas por chamada de lote (import ou export)

# --- configurações da organização (L0-07-a-configuracoes-org; GET/PUT /api/org): nome, identidade visual
# (logotipo reaproveitando o adaptador genérico de arquivo do L0-11, classe 'org_logo'), mapa padrão, idioma
# padrão, cotas de armazenamento/usuários e a política de senha/2FA já lida de tenant.config.auth (app/auth/
# politica.py, L0-02) — esta tela só EXPÕE aquele esquema, nunca recria um novo.
ORG_NOME_MAX = 55                         # mesmo teto do "Organization name" da Esri (portão do item-pai L0-07-a)
ORG_COR_PADRAO = "#2463a8"                # mesmo azul de app/catalogo/miniatura.py TRACO, cor de marca padrão
ORG_IDIOMAS = ("pt-BR", "en", "es")       # só o que existe em web/js/i18n/ (UX-02: en e es com paridade de chaves)
ORG_ZOOM_MAX = 24                         # teto de zoom de um webmap (padrão MapLibre/Leaflet)
ORG_BASEMAP_MAX = 100
ORG_LOGO_BYTES_MAX = 1 * 1024 * 1024      # 1 MiB (portão do item-pai: "logo > 1 MB recusado")
ORG_LOGO_PIXELS_MAX = 25_000_000          # mesma defesa de bomba de descompressão de app/catalogo/miniatura.py
ORG_LOGO_LADO = 300                       # canvas quadrado 300×300 (portão do item-pai)
ORG_COTA_BYTES_MIN = 100 * 1024 * 1024    # 100 MiB: abaixo disso o próprio inquilino de demonstração não sobe
ORG_COTA_USUARIOS_MIN = 1
# Teto ABSOLUTO da instalação (achados G4-04/G4-05: o admin do inquilino passou de 20 GiB para 9e18 bytes e de
# 2.000 para 1e9 assentos com HTTP 200, e a cota chegou ao bucket do Garage). Quem escolhe o teto de CADA
# inquilino é a plataforma (`PUT /api/plataforma/inquilinos/{id}/cotas`, superadmin, grava
# plat.tenant.cota_bytes_teto/cota_usuarios_teto); o inquilino só escolhe abaixo do próprio teto. Estes dois
# números são o limite que nem a plataforma passa, e estão repetidos em plat.tenant_cotas_teto_definir.
ORG_COTA_BYTES_TETO_MAX = 1024 * 1024 * 1024 * 1024   # 1 TiB
ORG_COTA_USUARIOS_TETO_MAX = 100_000
ORG_COTA_USUARIOS_PADRAO = 2000           # bem acima do maior lote (LOTE_MAX=100) e do uso medido em demo (T3: 59)
ORG_COTA_ITENS_MIN = 1                    # cota de itens do catálogo (tenant.config.catalogo.cota_itens, D16 da 011)
ORG_USO_DIAS_PADRAO = 30                  # período padrão da tela/relatório de uso (L0-07-admin-org)
ORG_USO_DIAS_MAX = 366                    # acima disso = 422 (a série é diária; um ano basta para o console)

# --- perfil próprio do usuário (L0-02-g-perfil-usuario; POST/PUT /api/eu, app/auth/rotas_eu.py): idioma,
# unidades, formato de data, visibilidade e foto (mesmo padrão do org_logo do L0-07-a — reaproveita
# app/objetos.py, classe 'usuario_foto', sha256 guardado numa coluna). PERFIL_IDIOMAS é maior que ORG_IDIOMAS
# de propósito: a APLICAÇÃO da tradução (troca de dicionário no cliente) é o item L7-10-a-i18n-pt-en-es, ainda
# pendente — guardar a preferência agora não promete tela traduzida hoje.
PERFIL_IDIOMAS = ("pt-BR", "en", "es")
PERFIL_UNIDADES = ("metrico", "imperial")
PERFIL_FORMATOS_DATA = ("dd/mm/aaaa", "mm/dd/aaaa", "aaaa-mm-dd")
PERFIL_VISIBILIDADES = ("privado", "inquilino")
PERFIL_FOTO_BYTES_MAX = 1 * 1024 * 1024   # 1 MiB (portão do item: "foto > 1 MB recusada")
PERFIL_FOTO_PIXELS_MAX = 25_000_000       # mesma defesa de bomba de descompressão do org_logo/miniatura
PERFIL_FOTO_LADO = 200                    # canvas quadrado 200×200 (hipótese do item)

# --- SMTP, convite de membro e redefinição de senha por e-mail (L0-07-d-smtp-convites; privilégio
# `org.integracoes`, já semeado na migração 003 com a descrição "SSO, SMTP, webhooks, CORS"). Sem SMTP
# configurado (nem por inquilino, nem na instalação) os fluxos caem no caminho manual já existente
# (senha temporária mostrada ao admin, POST /api/usuarios/{id}/senha) — nada aqui torna esse caminho obrigatório.
SMTP_HOST_MAX = 255
SMTP_USUARIO_MAX = 255
SMTP_SENHA_MAX = 1024                     # antes de cifrar; a cifra em si (AES-GCM) é maior no banco
SMTP_REMETENTE_MAX = 255
SMTP_ROTULO_MAX = 100
SMTP_PORTA_MIN = 1
SMTP_PORTA_MAX = 65535
SMTP_CONECTAR_TIMEOUT_S = 6.0             # teste de envio: curto de propósito, nunca prende a requisição
SMTP_ENVIAR_TIMEOUT_S = 15.0              # dentro do job (worker), pode ser mais folgado que o teste síncrono
SMTP_ASSUNTO_MAX = 200
SMTP_TEXTO_MAX = 20_000
CONVITE_VALIDADE_DIAS = 7                 # portão do item: link após 7 dias = 410
CONVITE_LOGIN_MAX = 128
CONVITE_NOME_MAX = 128
CONVITE_LISTA_MAX = 200
REDEFINICAO_VALIDADE_HORAS = 1            # portão do item-pai (ADR 0002 seção 6.3): token de 1 hora
REDEFINICAO_JANELA_MIN = 15               # limite de taxa (refutação do item: 1.000 pedidos/min p/ o mesmo e-mail)
REDEFINICAO_MAX_JANELA = 5                # no máximo 5 pedidos por (inquilino, e-mail) a cada REDEFINICAO_JANELA_MIN
AVISO_EXPIRACAO_DIAS = (90, 30, 7, 1)     # avisos de expiração de token de serviço (hipótese do item; como a Esri)

# --- grades aninhadas do motor multicritério (L3-19-multiescala; migração 20260906T1640_multiescala.sql):
# macro (grosseira, ex. 1 km) triando regiões e micro (fina, ex. 100 m) gerada SÓ dentro das aprovadas.
# ESCALA_CELULAS_MAX vale tanto para a grade macro inteira quanto para o refino micro (aprovadas × k²) — é o
# mesmo teto de proteção de RAM/disco (a casa está com o disco a 98 %, item não pode gerar grade sem freio);
# 250.000 células cobrem, por exemplo, uma grade macro de 500×500 ou um refino de 500 regiões aprovadas a
# k=22. ESCALA_LIGACOES_MAX freia célula × fator (a tabela `escala_fator_celula` é uma LINHA por par).
ESCALA_AREA_VERTICES_MAX = 5_000      # vértices do polígono de estudo (mesma ordem de grandeza de INGESTAO_*)
ESCALA_RESOLUCAO_MIN_M = 1.0
ESCALA_RESOLUCAO_MAX_M = 100_000.0
ESCALA_CELULAS_MAX = 250_000
ESCALA_FATORES_MAX = 20
ESCALA_LIGACOES_MAX = 2_000_000
ESCALA_APROVACAO_TIPOS = ("limiar", "top_pct")
ESCALA_NOME_MAX = 200                 # mesmo teto de CHECK(length(nome)<=200) da migração
ESCALA_UNIDADE_MAX = 40               # CHECK(length(unidade)<=40)
ESCALA_FONTE_MAX = 500                # CHECK(length(fonte)<=500)
ESCALA_AMOSTRAS_LOTE_MAX = 20_000     # amostras de fator por chamada de POST (streaming não é o item; teto direto)
# --- motor multicritério (L3-01-a/b; ADR 0016, decisões A1/A3/A7 do L3L6_CONCEITO). Os tetos de unidade e de
# área não são arbitrários: MEDIDO 06/09/2026 nesta máquina, uma grade quadrada de 250 m sobre 2.000 km²
# (32.000 células) leva ~13 s e ocupa ~19 MB; `df -h /mnt/pgdata` mostra 98 % de uso, então 1 milhão de
# unidades num conjunto (≈ 600 MB com geometria e índice) é o máximo que cabe com folga. Acima disso a API
# recusa com `grade_grande_demais` e diz para aumentar o lado ou reduzir a área, nunca corta em silêncio
AMC_LADO_M_MIN = 10.0                 # abaixo disso a grade deixa de ser unidade de análise e vira pixel
AMC_LADO_M_MAX = 100_000.0            # 100 km: célula maior que isto não cabe em nenhuma zona UTM sem distorcer
AMC_AREA_ESTUDO_KM2_MAX = 2_000_000.0 # ~1/4 do Brasil: acima disso a zona UTM única do centróide perde sentido
AMC_UNIDADES_MAX = 1_000_000          # unidades por conjunto (grade ou feições)
AMC_FEICOES_INLINE_MAX = 20_000       # feições por envio síncrono de conjunto do tipo 'feicoes'
AMC_MODELOS_POR_INQUILINO = 500       # modelos vivos (apagado_em IS NULL) por inquilino
AMC_CONJUNTOS_POR_INQUILINO = 200     # conjuntos de unidades por inquilino
AMC_VERSOES_POR_MODELO = 500          # versões de um modelo (cada edição cria uma; imutáveis, nunca apagadas)
AMC_UNIDADES_PAGINA_MAX = 5_000       # unidades por página em GET /api/amc/conjuntos/{id}/unidades
AMC_RESULTADOS_PAGINA_MAX = 5_000     # linhas por página em GET /api/amc/execucoes/{id}/resultados

# --- imagens/STAC (L1-01-a-pgstac-e-stac-api-por-inquilino; app/imagens/): catálogo é o pgstac (schema
# `pgstac`, global ao banco), isolado por inquilino por convenção de nome de coleção `<tenant_id>-<slug>`,
# nunca por RLS do pgstac (ele não tem). STAC_SLUG_MAX é o que sobra de 63 bytes (limite de identificador do
# Postgres, embora `id` do pgstac seja `text` livre — o teto aqui é POLÍTICA, não do banco) depois do prefixo
# `<tenant_id>-`: numa instalação com tenant_id de até 6 dígitos, 58 caracteres de slug cabem com folga no
# CHECK de plat.raster_item.colecao.
STAC_SLUG_MAX = 58
STAC_ITEM_ID_MAX = 256
STAC_PAGINA_PADRAO = 10      # `limit` padrão da busca (mesmo padrão da spec STAC API Item Search)
STAC_PAGINA_MAX = 1000       # `limit` máximo aceito por pedido (pgstac pagina por token, não por offset)
STAC_COLECOES_POR_INQUILINO = 500
STAC_LOTE_ITENS_MAX = 10_000  # POST .../items:lote (semeadura de teste/ingestão em massa; ADR do item L1-01-h)

# --- ingestão de raster (L1-01-ingest-raster; ADR 20260906T2127): validação isolada + COG dois perfis +
# STAC no pgstac. RASTER_DIMENSAO_MAX/RASTER_BANDAS_MAX são recusa da validação (acima disto o COG não é
# manejável pelo appliance: 200k×200k px uint8 já são 40 GB por banda); RASTER_VISUAL_MAX_LADO só limita a
# MINIATURA/estatística amostrada, nunca o COG. TILE_CACHE_DATASET_MAX limita datasets abertos por processo
# no handler de tiles (mínimo honesto até o TiTiler do L1-02).
RASTER_DIMENSAO_MAX = 200_000           # pixels por eixo (linhas ou colunas) — acima: recusa na validação
RASTER_BANDAS_MAX = 64                  # bandas por raster — acima: recusa na validação
RASTER_BYTES_MAX = 2 * 1024 * 1024 * 1024  # bruto aceito para ingestão (igual a UPLOAD_BYTES_MAX)
RASTER_VISUAL_MAX_LADO = 1024           # miniatura PNG (lado maior)
RASTER_ESTATISTICA_AMOSTRA = 100_000    # pixels amostrados por banda para percentis do perfil visual
RASTER_TILE_CACHE_DATASET_MAX = 8       # datasets abertos por processo no handler de tiles (LRU)
RASTER_TILE_TIMEOUT_S = 30              # teto de renderização de um tile (mata a requisição, não o worker)
# Quantos níveis ABAIXO do zoom mínimo da imagem um ladrilho ainda é servido. Abaixo do mínimo a imagem
# não enche um ladrilho e o custo DOBRA por nível — MEDIDO nesta máquina numa cena de 869 MB com mínimo 8:
# z=8 0,05 s · z=7 2,2 s · z=6 2,0 s · z=5 3,3 s · z=4 5,9 s · z=3 12 s · z=2 23 s · z=1 46 s · z=0 94 s.
# O teto do nginx é 60 s: de z=1 para baixo o cliente recebia 504, e o ArcGIS Pro traduz isso para
# "Invalid Path" e recusa a camada inteira. Três níveis param em 3,3 s e ainda cobrem o raster pequeno,
# que tem mínimo alto por ser pequeno (o de teste tem mínimo 14 e é pedido em z=12).
RASTER_TILE_NIVEIS_ABAIXO_DO_MINIMO = 3
# --- exportação de camada (L0-04-h-exportar; ADR 0018). Os tempos e tetos abaixo saem de MEDIÇÃO nesta
# --- geocodificação de tabela enviada pelo usuário (L2-11-a-geocodificacao-csv). O teto de tamanho é medido
# em BYTES REAIS do objeto (não no que o navegador declara) e em LINHAS: os dois existem porque um arquivo
# pequeno pode ter muitas linhas (CSV de 20 MB com endereço curto passa de 300 mil linhas) e o custo do lote é
# por LINHA, não por byte. Quem estoura qualquer um dos dois é recusado ANTES de começar (nunca no meio).
GEOCOD_ARQUIVO_BYTES_MAX = 32 * 1024 * 1024   # 32 MiB do arquivo enviado (D21: o laço trabalha com <= 3 GB)
GEOCOD_LINHAS_MAX = 200_000                   # linhas de dado (sem o cabeçalho)
GEOCOD_AMOSTRA_COLUNAS_BYTES = 256 * 1024     # só este pedaço é lido para propor o mapeamento de colunas
GEOCOD_LOTE_GRAVACAO = 500                    # linhas por INSERT em lote (execute_values)
GEOCOD_CAMPO_TEXTO_MAX = 300                  # valor de célula acima disso é truncado com aviso na linha
GEOCOD_LINHAS_PAGINA_MAX = 500                # teto da listagem da tela de revisão
GEOCOD_CAMPOS = ("endereco", "logradouro", "numero", "bairro", "municipio", "uf", "cep")

# --- exportação de camada (L0-04-h-exportar; ADR 0016). Os tempos e tetos abaixo saem de MEDIÇÃO nesta
# máquina em 06/09/2026 sobre uma camada de 100 mil pontos (ver tests/medidas/L0-04-h-exportar.json), não de
# estimativa: ogr2ogr escreve GPKG/GeoJSON/shapefile/CSV/XLSX/KML/FlatGeobuf/GML/DXF de 50 mil feições em
# 0,2-0,7 s cada. A exceção medida é o driver LIBKML: 3,5 min de CPU e 255 MB de RSS para as MESMAS 50 mil
# feições, sem terminar — por isso KML/KMZ usam o driver `KML` (0,34 s) e o KMZ é o zip do KML feito aqui.
EXPORTACAO_VALIDADE_DIAS = 7                  # arquivo gerado some depois disso (periódico exportacao.expirar)
EXPORTACAO_POR_USUARIO_EM_CURSO = 3           # exportações pendentes/gerando por usuário (refutação: 5 em paralelo)
EXPORTACAO_MEMORIA_MB = 1024                  # job exportacao.gerar (mesmo teto de ingestao.carregar)
EXPORTACAO_TIMEOUT_S = 3600
EXPORTACAO_DISCO_MIN_LIVRE_BYTES = 2 * 1024 * 1024 * 1024   # nunca começa com menos que isto livre (disco a 98%)
EXPORTACAO_FATOR_DISCO = 3                    # arquivo temporário estimado = tamanho da tabela x isto (GML mede 3,4x
                                              # o GPKG na medição de 06/09; o fator cobre o pior caso + o zip)
EXPORTACAO_CAMPOS_MAX = 500                   # mesmo teto de INGESTAO_CAMPOS_MAX (a lista vem do mesmo item)
EXPORTACAO_WHERE_MAX = 4000                   # caracteres do filtro `where` (o parser do L2-04-b recusa o resto)
EXPORTACAO_NOME_MAX = 120                     # nome do arquivo pedido pelo usuário (sem extensão)
EXPORTACAO_ERRO_BANCO_MAX = 300               # tamanho do erro do banco depois de saneado, no corpo do 400
EXPORTACAO_CODIFICACOES = ("UTF-8", "ISO-8859-1")
EXPORTACAO_CSV_SEPARADORES = (",", ";", "\t", "|")
EXPORTACAO_CSV_DECIMAIS = (".", ",")
EXPORTACAO_BLOCO_LEITURA_BYTES = 8 * 1024 * 1024   # leitura do arquivo pronto em blocos (sha256 e envio); NUNCA
                                              # o arquivo inteiro em memória, nem no envio ao Garage nem na entrega

# --- exportação COMPLETA do inquilino (L0-06-d-exportar-inquilino): "Exportar meu inquilino" do admin. Reusa
# EXPORTACAO_VALIDADE_DIAS (mesmos 7 dias) e EXPORTACAO_MEMORIA_MB do irmão L0-04-h; os limites abaixo são só
# os que este item acrescenta.
EXPORTACAO_INQUILINO_TIMEOUT_S = 3600 * 4          # inquilino inteiro pode ter muitas camadas; 4x o de uma só
EXPORTACAO_INQUILINO_POR_DIA_MAX = 1               # portão do item: pedir a 2ª no mesmo dia UTC devolve 429
# --- SAML 2.0 Web SSO por inquilino (L0-08-b-saml; app/auth/saml.py)
SAML_DESVIO_RELOGIO_S = 300              # tolerância de relógio IdP x SP (o portão manda recusar 10 min à frente)
SAML_RESPOSTA_MAX = 256 * 1024           # SAMLResponse/LogoutRequest acima disto = 413 (asserção real tem poucos KiB)
SAML_METADADO_MAX = 512 * 1024           # metadado do IdP lido por URL/arquivo
SAML_METADADO_TIMEOUT_S = 8.0            # leitura do metadado do IdP por URL
SAML_TRANSACAO_MIN = 10                  # validade do AuthnRequest/LogoutRequest emitido (plat.saml_transacao)
# --- ferramentas de análise (L2-05-a; L2_CONCEITO C8): job por padrão, síncrono só abaixo do custo declarado
FERRAMENTA_SINCRONO_CUSTO_MAX = 5000       # custo = feições × complexidade declarada no manifesto; acima disso só job
FERRAMENTA_JOB_MEMORIA_MB = 1024            # RLIMIT_DATA do filho que roda uma ferramenta
FERRAMENTA_JOB_TIMEOUT_S = 1800             # 30 min por execução; ferramenta mais longa é outro tipo de job
BUFFER_DISTANCIA_M_MAX = 100_000            # 100 km: acima disso o buffer geodésico deixa de fazer sentido em camada

# --- COG direto por HTTPS (L1-02-e): uma requisição Range é mantida pequena para que clientes analíticos
# não transformem a API em download monolítico; a resposta sem Range continua permitida, mas sai em streaming.
COG_FAIXA_MAX_BYTES = 16 * 1024 * 1024  # 16 MiB por Range; GDAL/QGIS normalmente pede blocos muito menores

# --- WMS 1.3.0 (L1-02-g-wms-1-3-0-raster; app/imagens/wms.py, rotas_wms.py): camada fina sobre o mesmo
# leitor de pixel do ladrilho (`recorte()` em tiles.py, irmã de `ladrilho()`) — GetMap é um recorte
# arbitrário (bbox+CRS+tamanho do cliente), não uma célula da grade WebMercator. WMS_PIXELS_MAX é o
# teto que protege RAM/CPU do processo (um GetMap grande demais lê e reprojeta o COG inteiro na hora);
# 4096×4096 cobre a maior tela física comum (4K) com folga e ainda cabe em RAM sem swap nesta máquina
# apertada. WMS_CAMADAS_MAX limita quantos `<Layer>` o GetCapabilities enumera por token: cada camada
# custa uma leitura do STAC (bbox), então sem teto um token com muitos itens deixaria o documento lento
# e enorme — 500 é acima de qualquer inquilino de demonstração hoje, revisar quando houver caso real.
WMS_LARGURA_MAX = 4096                  # WIDTH máximo aceito no GetMap — acima: ServiceExceptionReport
WMS_ALTURA_MAX = 4096                   # HEIGHT máximo aceito no GetMap — acima: ServiceExceptionReport
WMS_PIXELS_MAX = 4096 * 4096            # teto de WIDTH×HEIGHT (é o que de fato protege a memória)
WMS_CAMADAS_MAX = 500                   # <Layer> por GetCapabilities (itens além disso não aparecem)
WMS_TIMEOUT_S = 30                      # teto de renderização de um GetMap (mesma ordem do tile)

# --- ImageServer compatível Esri (L1-25-servico-de-imagem-esri-compativel; app/imagens/rotas_imageserver.py):
# `exportImage` é o mesmo tipo de recorte arbitrário que o GetMap do WMS (`Reader.part`, não uma célula da
# grade) — mesma defesa, mesmo teto: a refutação do item manda pedir 20.000×20.000 e recusar sem travar.
IMAGESERVER_EXPORT_LADO_MAX = 4096      # largura/altura máximas aceitas no exportImage, em pixels
IMAGESERVER_EXPORT_LADO_PADRAO = 400    # tamanho quando `size` não vem — mesmo default do ArcGIS Server

# --- ingestão de modelo 3D (L1-03-modelo3d, 10/09/2026): IFC bruto enviado pelo usuário antes da conversão
# (que roda num conversor externo — GPU box por ssh nesta instalação — por isso o teto é bem menor que o do
# raster: o arquivo inteiro viaja por scp duas vezes, ida e volta, dentro do timeout do job).
MODELO3D_IFC_BYTES_MAX = 512 * 1024 * 1024
MODELO3D_XKT_BYTES_MAX = 512 * 1024 * 1024
MODELO3D_CONVERSAO_TIMEOUT_S = 1500     # teto do ssh+scp+convert2xkt no conversor remoto (job todo tem mais margem)
FOTO360_BYTES_MAX = 64 * 1024 * 1024
MODELO3D_URL_VALIDADE_S = 3600          # validade da URL assinada do .xkt/.jpg entregue ao visualizador
# --- grades aninhadas do motor multicritério (L3-19-multiescala; migração 20260906T1640_multiescala.sql):
# macro (grosseira, ex. 1 km) triando regiões e micro (fina, ex. 100 m) gerada SÓ dentro das aprovadas.
# ESCALA_CELULAS_MAX vale tanto para a grade macro inteira quanto para o refino micro (aprovadas × k²) — é o
# mesmo teto de proteção de RAM/disco (a casa está com o disco a 98 %, item não pode gerar grade sem freio);
# 250.000 células cobrem, por exemplo, uma grade macro de 500×500 ou um refino de 500 regiões aprovadas a
# k=22. ESCALA_LIGACOES_MAX freia célula × fator (a tabela `escala_fator_celula` é uma LINHA por par).
ESCALA_AREA_VERTICES_MAX = 5_000      # vértices do polígono de estudo (mesma ordem de grandeza de INGESTAO_*)
ESCALA_RESOLUCAO_MIN_M = 1.0
ESCALA_RESOLUCAO_MAX_M = 100_000.0
ESCALA_CELULAS_MAX = 250_000
ESCALA_FATORES_MAX = 20
ESCALA_LIGACOES_MAX = 2_000_000
ESCALA_APROVACAO_TIPOS = ("limiar", "top_pct")
ESCALA_NOME_MAX = 200                 # mesmo teto de CHECK(length(nome)<=200) da migração
ESCALA_UNIDADE_MAX = 40               # CHECK(length(unidade)<=40)
ESCALA_FONTE_MAX = 500                # CHECK(length(fonte)<=500)
ESCALA_CELULAS_GEOJSON_MAX = 50_000   # feições de GET /api/multiescala/execucoes/{id}/celulas (UX-08); além = truncado
ESCALA_AMOSTRAS_LOTE_MAX = 20_000     # amostras de fator por chamada de POST (streaming não é o item; teto direto)

# ---- L2-10-d-regras-de-atributo: regras por camada (cálculo, restrição, validação) e campos virtuais, avaliadas
# pela linguagem de expressão (app/expressao) no caminho único de escrita (app/edicao) e no job camadas.validar
REGRAS_POR_CAMADA_MAX = 100                # entradas em dados.regras (cálculo + restrição + validação)
REGRAS_CAMPOS_VIRTUAIS_MAX = 50            # entradas em dados.campos_virtuais (só leitura, avaliados na leitura)
REGRAS_EXPRESSAO_TEXTO_MAX = 4_000         # caracteres por expressão de regra (bem abaixo de MAX_TEXTO do avaliador)
REGRAS_MENSAGEM_MAX = 500                  # mensagem configurada da restrição/validação
REGRAS_VALIDACAO_LOTE = 5_000              # feições por lote do job camadas.validar (cursor no servidor)
REGRAS_VALIDACAO_ERROS_MAX = 1_000_000     # teto de erros gravados por execução (acima disso o job para e avisa)
REGRAS_FEICOES_LEITURA_MAX = 1_000         # linhas por chamada de GET /api/camadas/{id}/feicoes
ESCALA_AMOSTRAS_LOTE_MAX = 20_000     # amostras de fator por chamada de POST (streaming não é o item; teto direto)
# --- edição transacional de feições (L2-03-a-api-edicao-transacional; POST /api/camadas/{id}/edicoes, única
# porta de escrita para navegador/PWA/FeatureServer/OGC). LOTE_MAX = 2× o tamanho medido no portão (1.000
# feições ≤ 3 s), com folga operacional; bem abaixo do lote de 100 mil que a refutação do item manda recusar
# (esse cai primeiro no 413 de CORPO_MAX_PADRAO_BYTES quando o corpo é grande, mas o teto por lista garante o
# 422 mesmo com corpo pequeno e muitas feições minúsculas).
EDICAO_LOTE_MAX = 2_000
EDICAO_ATRIBUTOS_MAX = 500                # campos por feição num único pedido (mesmo teto de INGESTAO_CAMPOS_MAX)
EDICAO_TEXTO_MAX = 65_536                 # 64 KiB por valor de campo texto (mesma ordem de ITEM_DESCRICAO_MAX)
EDICAO_REGRA_CAMPO_MAX = 500              # entradas em dados.regras_campo (mesmo teto de campos da camada)
EDICAO_DOMINIO_VALORES_MAX = 1_000        # valores aceitos por regra de domínio codificado
EDICAO_SRID_MAX = 999_999                 # mesmo teto do esquema de camada_vetorial (029_ingestao_vetor.sql)

# --- edição no mapa: histórico/restauração e anexos por feição (item L2-03-edicao)
HISTORICO_LISTA_MAX = 500                 # entradas devolvidas por consulta (mais recentes primeiro)
ANEXO_TAMANHO_MAX = 7 * 1024 * 1024       # 7 MiB por anexo — NÃO 10: o envio é JSON com o conteúdo em base64
# (achado do adversário 07/09), que incha o arquivo em ~4/3; um anexo de 10 MiB vira ~13,3 MiB de corpo, acima
# de CORPO_MAX_PADRAO_BYTES (10 MiB) — o 413 genérico do middleware dispara ANTES desta checagem rodar, e o
# 422 "anexo_grande" (com a mensagem específica) nunca aparece. 7 MiB codifica para ~9,33 MiB, com folga.
# tupla ordenada, não frozenset: repr() de um set não é determinístico entre execuções (docs/gerar_limites.py
# lê repr() literal — um frozenset faria docs/LIMITES.md variar a cada regeneração sem nada ter mudado)
ANEXO_TIPOS_PERMITIDOS = ("application/pdf", "image/gif", "image/jpeg", "image/png", "image/webp")
# --- motor multicritério, modelo (L3-01-a-modelo-dado; laco/decomposicao/L3L6_CONCEITO.md decisões A1/A4/A10).
# Vocabulário e tetos do documento em docs/esquemas/amc_modelo.v1.json nascem daqui quando o número é livre
# (o que é vocabulário FECHADO — tipos de transformação, combinador — mora só no JSON Schema, que é o contrato
# público; aqui só os tetos de tamanho, que são os mesmos limites transversais do resto da casa).
AMC_NOME_MAX = 250                # mesmo teto de ITEM_TITULO_MAX
AMC_FATORES_MAX = 50              # mesmo teto de docs/esquemas/amc_modelo.v1.json fatores.maxItems
AMC_CAMADAS_MAX = 50              # camadas de entrada declaradas por execução (A10)
# --- tabela de atributos da camada (L2-01-g-tabela-atributos): paginação no servidor, busca em texto, filtro
# pela extensão do mapa, seleção e a vista por usuário (colunas visíveis, alias, largura, domínio). As páginas
# são as três do Map Viewer/ArcGIS Pro; nenhum valor livre, para que o `LIMIT` seja sempre um dos três.
TABELA_PAGINAS = (50, 200, 1000)
TABELA_BUSCA_MAX = 200                    # termo de busca (ILIKE + unaccent) — acima disso é ataque, não busca
TABELA_FIDS_MAX = 5000                    # seleção vinda do mapa: identificadores enviados de uma vez
TABELA_COLUNAS_MAX = 500                  # mesmo teto de `campos` no esquema do tipo camada_vetorial (029)
TABELA_ALIAS_MAX = 200                    # mesmo teto de `alias` no esquema do tipo camada_vetorial (029)
TABELA_LARGURA_MIN = 40                   # pixels; abaixo disso a coluna some da tela e não dá para arrastar
TABELA_LARGURA_MAX = 2000
TABELA_DOMINIO_ITENS_MAX = 1000           # pares código -> descrição por coluna
TABELA_DOMINIO_TEXTO_MAX = 250
TABELA_GEOMETRIA_LIMITE = 2000            # feições com geometria devolvidas para desenhar no mapa (por página)
# --- exportação de camada (L0-04-h-exportar; ADR 0018). Os tempos e tetos abaixo saem de MEDIÇÃO nesta
# máquina em 06/09/2026 sobre uma camada de 100 mil pontos (ver tests/medidas/L0-04-h-exportar.json), não de
# estimativa: ogr2ogr escreve GPKG/GeoJSON/shapefile/CSV/XLSX/KML/FlatGeobuf/GML/DXF de 50 mil feições em
# 0,2-0,7 s cada. A exceção medida é o driver LIBKML: 3,5 min de CPU e 255 MB de RSS para as MESMAS 50 mil
# feições, sem terminar — por isso KML/KMZ usam o driver `KML` (0,34 s) e o KMZ é o zip do KML feito aqui.
EXPORTACAO_VALIDADE_DIAS = 7                  # arquivo gerado some depois disso (periódico exportacao.expirar)
EXPORTACAO_POR_USUARIO_EM_CURSO = 3           # exportações pendentes/gerando por usuário (refutação: 5 em paralelo)
EXPORTACAO_MEMORIA_MB = 1024                  # job exportacao.gerar (mesmo teto de ingestao.carregar)
EXPORTACAO_TIMEOUT_S = 3600
EXPORTACAO_DISCO_MIN_LIVRE_BYTES = 2 * 1024 * 1024 * 1024   # nunca começa com menos que isto livre (disco a 98%)
EXPORTACAO_FATOR_DISCO = 3                    # arquivo temporário estimado = tamanho da tabela x isto (GML mede 3,4x
                                              # o GPKG na medição de 06/09; o fator cobre o pior caso + o zip)
PACOTE_CAMADAS_MAX = 50                       # camadas num pacote de mapa (item L2-01-l)
PACOTE_IMPORTAR_MAX_BYTES = 200 * 1024 * 1024 # pacote enviado para reimportação (acima disso, 413)
PACOTE_OGR_TIMEOUT_S = 900                    # ogr2ogr de UMA camada do pacote na reimportação
EXPORTACAO_IDS_MAX = 200000                   # fids de uma seleção exportada (mesmo teto do tipo de item `selecao`)
EXPORTACAO_CAMPOS_MAX = 500                   # mesmo teto de INGESTAO_CAMPOS_MAX (a lista vem do mesmo item)
EXPORTACAO_WHERE_MAX = 4000                   # caracteres do filtro `where` (o parser do L2-04-b recusa o resto)
EXPORTACAO_NOME_MAX = 120                     # nome do arquivo pedido pelo usuário (sem extensão)
EXPORTACAO_ERRO_BANCO_MAX = 300               # tamanho do erro do banco depois de saneado, no corpo do 400
EXPORTACAO_CODIFICACOES = ("UTF-8", "ISO-8859-1")
EXPORTACAO_CSV_SEPARADORES = (",", ";", "\t", "|")
EXPORTACAO_CSV_DECIMAIS = (".", ",")
EXPORTACAO_BLOCO_LEITURA_BYTES = 8 * 1024 * 1024   # leitura do arquivo pronto em blocos (sha256 e envio); NUNCA
                                              # o arquivo inteiro em memória, nem no envio ao Garage nem na entrega

# --- widgets de página e de menu (L5-01-d)
QR_TEXTO_MAX = 2048                         # conteúdo máximo do QR de compartilhar (uma URL longa cabe)

# --- layout de impressão (item L2-12-b-layouts-elementos-exportacao)
LAYOUT_ELEMENTOS_MAX = 200                  # elementos por documento de layout
LAYOUT_QUADROS_MAX = 6                      # quadros de mapa por layout (principal + localização + auxiliares)
LAYOUT_ESCALA_MIN = 100                     # 1:N mínimo aceito no quadro por escala fixa
LAYOUT_ESCALA_MAX = 50_000_000              # 1:N máximo (o mundo cabe em A4)
LAYOUT_TEXTO_MAX = 4000                     # caracteres de um título/texto do layout
LAYOUT_TABELA_LINHAS_MAX = 200              # linhas da tabela de atributos num layout
LAYOUT_DPI_MIN = 72                         # DPI mínimo de exportação
LAYOUT_DPI_MAX = 300                        # DPI máximo de exportação (o portão do item pede 96-300)
LAYOUT_QUADRO_PIXELS_MAX = 4096             # maior lado do quadro em pixels no motor de render; acima, o quadro é
                                            # desenhado neste teto e o DPI efetivo (menor) vai no relatório
LAYOUT_INLINE_BYTES_MAX = 256 * 1024        # documento de layout inline num pedido/job (JSON)
# --- resultado de traçado de rede de utilidades (L4-02-f-resultados-e-exportacao)
# O traçado inteiro é montado em memória antes de virar arquivo (CSV, GeoJSON ou GeoPackage), e o
# GeoPackage é um SQLite construído em memória: o teto abaixo é o que impede um traçado de alimentador
# inteiro de virar consumo de RAM sem freio na máquina (a casa trabalha com 2-3 GB livres). Acima dele a
# resposta é 413 dizendo o número medido e como estreitar, nunca um arquivo pela metade.
TRACADO_EXPORTACAO_MAX = 50_000     # elementos por exportação ou por camada salva
TRACADO_HISTORICO_MAX = 20          # "os 20 últimos traçados do usuário" (portão do item)
# --- gráficos por camada (L2-01-i-graficos-de-camada; rota POST /api/camadas/{id}/grafico): a agregação é
# sempre no servidor e a resposta nunca carrega a tabela crua — estes tetos são o que garante "nenhuma
# resposta > 1 MB" mesmo numa camada de 1 milhão de linhas ou de 5.000 categorias.
GRAFICO_CATEGORIAS_PADRAO = 50        # barras/pizza: categorias maiores mostradas; o resto vira UM grupo "outros"
GRAFICO_CATEGORIAS_MAX = 500
GRAFICO_FAIXAS_MAX = 200              # histograma: faixas de largura igual
GRAFICO_AMOSTRA_PADRAO = 2_000        # dispersão: pontos desenhados (a regressão usa TODAS as linhas)
GRAFICO_AMOSTRA_MAX = 5_000
GRAFICO_RESPOSTA_BYTES_MAX = 1_000_000  # teto declarado (refutação do item); conferido por teste, não por corte

# --- MapServer compatível com Esri (item L2-04-f): export/identify/legend/find e o GeometryServer.
# O lado máximo é o mesmo `maxImageWidth`/`maxImageHeight` que o ArcGIS Server traz de fábrica (4096);
# o teto de pixels é o quadrado desse lado, e existe separado porque 4096×4096 já é imagem de 16,8 Mpx
# — um pedido de 8.000×8.000 (a refutação declarada do item) bate no lado e volta 400 antes de alocar
# um único byte de imagem.
MAPSERVER_LADO_MAX = 4096
MAPSERVER_PIXELS_MAX = 4096 * 4096
MAPSERVER_DPI_MAX = 600                   # acima disso o traço em pixel passa a não caber na memória prometida
MAPSERVER_FEICOES_POR_CAMADA = 50_000     # teto de feições desenhadas por camada num único export
MAPSERVER_CAMADAS_MAX = 50                # camadas desenhadas por pedido (o documento de mapa aceita 200)
MAPSERVER_IDENTIFY_MAX = 100              # resultados por identify (`maxAllowableOffset` da doc Esri é outro eixo)
MAPSERVER_FIND_MAX = 100                  # resultados por find
GEOMETRIA_FEICOES_MAX = 1_000             # geometrias por chamada do GeometryServer (project/buffer/...)
GEOMETRIA_VERTICES_MAX = 200_000          # vértices somados por chamada (mesmo teto do filtro espacial da query)

# --- réplicas para trabalho desconectado (item L2-13-b-replicas-sincronizacao)
# REPLICA_RASTREIO_RETENCAO_DIAS é a retenção DECLARADA de plat.feicao_historico: além dela o rastreio pode
# ter sido expurgado e "o que mudou desde a geração G" deixa de ser respondível. A validade da réplica é
# menor de propósito — uma réplica dentro da validade sempre acha o seu rastreio inteiro. O invariante
# (validade < retenção) é provado em tests/unit/test_replica_limites.py: inverter os dois deixaria a
# sincronização devolver um conjunto de mudanças INCOMPLETO sem nenhum erro, que é o pior desfecho possível.
REPLICA_VALIDADE_DIAS = 30
REPLICA_RASTREIO_RETENCAO_DIAS = 45
REPLICA_CAMADAS_MAX = 20                  # camadas por réplica (o pacote é um arquivo só, baixado por rede de campo)
REPLICA_FEICOES_MAX = 100_000             # feições por camada no pacote; acima disso o recorte tem de ser menor
REPLICA_SINCRONIZAR_LOTE_MAX = 2_000      # mudanças por camada num pedido (mesmo teto de EDICAO_LOTE_MAX)
REPLICA_BAIXAR_MAX = 5_000                # mudanças do servidor devolvidas por camada por sincronização
REPLICA_ANEXOS_BYTES_MAX = 64 * 1024 * 1024  # 64 MiB de anexo embutido no pacote (acima disso o pacote é recusado)
REPLICA_POR_USUARIO = 20                  # réplicas vivas por usuário (cada uma segura um pacote no armazenamento)
REPLICA_NOME_MAX = 200                    # CHECK(length(nome) BETWEEN 1 AND 200) da migração
REPLICA_FILTRO_MAX = 2_000                # CHECK(length(filtro) <= 2000) da migração
# --- imagens/STAC (L1-01-a-pgstac-e-stac-api-por-inquilino; app/imagens/): catálogo é o pgstac (schema
# `pgstac`, global ao banco), isolado por inquilino por convenção de nome de coleção `<tenant_id>-<slug>`,
# nunca por RLS do pgstac (ele não tem). STAC_SLUG_MAX é o que sobra de 63 bytes (limite de identificador do
# Postgres, embora `id` do pgstac seja `text` livre — o teto aqui é POLÍTICA, não do banco) depois do prefixo
# `<tenant_id>-`: numa instalação com tenant_id de até 6 dígitos, 58 caracteres de slug cabem com folga no
# CHECK de plat.raster_item.colecao.
STAC_SLUG_MAX = 58
STAC_ITEM_ID_MAX = 256
STAC_PAGINA_PADRAO = 10      # `limit` padrão da busca (mesmo padrão da spec STAC API Item Search)
STAC_PAGINA_MAX = 1000       # `limit` máximo aceito por pedido (pgstac pagina por token, não por offset)
STAC_COLECOES_POR_INQUILINO = 500
STAC_LOTE_ITENS_MAX = 10_000  # POST .../items:lote (semeadura de teste/ingestão em massa; ADR do item L1-01-h)

# --- ingestão de raster (L1-01-ingest-raster; ADR 20260906T2127): validação isolada + COG dois perfis +
# STAC no pgstac. RASTER_DIMENSAO_MAX/RASTER_BANDAS_MAX são recusa da validação (acima disto o COG não é
# manejável pelo appliance: 200k×200k px uint8 já são 40 GB por banda); RASTER_VISUAL_MAX_LADO só limita a
# MINIATURA/estatística amostrada, nunca o COG. TILE_CACHE_DATASET_MAX limita datasets abertos por processo
# no handler de tiles (mínimo honesto até o TiTiler do L1-02).
RASTER_DIMENSAO_MAX = 200_000           # pixels por eixo (linhas ou colunas) — acima: recusa na validação
RASTER_BANDAS_MAX = 64                  # bandas por raster — acima: recusa na validação
RASTER_BYTES_MAX = 2 * 1024 * 1024 * 1024  # bruto aceito para ingestão (igual a UPLOAD_BYTES_MAX)
RASTER_VISUAL_MAX_LADO = 1024           # miniatura PNG (lado maior)
RASTER_ESTATISTICA_AMOSTRA = 100_000    # pixels amostrados por banda para percentis do perfil visual
RASTER_TILE_CACHE_DATASET_MAX = 8       # datasets abertos por processo no handler de tiles (LRU)
RASTER_TILE_TIMEOUT_S = 30              # teto de renderização de um tile (mata a requisição, não o worker)
# Quantos níveis ABAIXO do zoom mínimo da imagem um ladrilho ainda é servido. Abaixo do mínimo a imagem
# não enche um ladrilho e o custo DOBRA por nível — MEDIDO nesta máquina numa cena de 869 MB com mínimo 8:
# z=8 0,05 s · z=7 2,2 s · z=6 2,0 s · z=5 3,3 s · z=4 5,9 s · z=3 12 s · z=2 23 s · z=1 46 s · z=0 94 s.
# O teto do nginx é 60 s: de z=1 para baixo o cliente recebia 504, e o ArcGIS Pro traduz isso para
# "Invalid Path" e recusa a camada inteira. Três níveis param em 3,3 s e ainda cobrem o raster pequeno,
# que tem mínimo alto por ser pequeno (o de teste tem mínimo 14 e é pedido em z=12).
RASTER_TILE_NIVEIS_ABAIXO_DO_MINIMO = 3
# --- classes de relacionamento entre camadas (L2-10-b-relacionamentos; plat.relacionamento/_junc,
# /api/relacionamentos e /api/camadas/{id}/relacionados/{rel}). Nomes seguem o mesmo teto de campo do
# L2-10-a (CAMPO_PADRAO); NOME_MAX é o mesmo teto do nome_direto/nome_inverso do banco.
RELACIONAMENTO_NOME_MAX = 120
RELACIONAMENTO_VALOR_MAX = 200            # tamanho do valor de chave guardado em relacionamento_junc (texto)
RELACIONAMENTO_LIMITE_PADRAO = 2000       # teto de relacionados por consulta quando a classe não declara outro
RELACIONAMENTO_LIMITE_MAX = 100_000       # teto absoluto (refutação do item: "100 mil relacionados numa origem")

# --- clonagem de camadas hospedadas da Esri (L2-08-b-clonar-camadas-hospedadas; app/migracao/clonar.py)
CLONE_PAGINA = 1000                      # feições por página de query e por lote de INSERT (maxRecordCount 1000-2000)
CLONE_ANEXO_MAX = 50 * 1024 * 1024       # bytes por anexo lido do portal (acima: aviso no relatório, feição segue)
CLONE_CAMADAS_MAX = 200                  # camadas + tabelas por serviço numa execução
CLONE_AMOSTRA = 100                      # feições da amostra comparada por sha256 (geometria normalizada + atributos)
# --- análise 3D sobre terreno e extrusões (L2-09-d-analise-3d-visibilidade): terreno chega INLINE na
# requisição (grade de alturas em SRID SIRGAS 2000 UTM, metros) enquanto a família raster (L2-05-e/L2-09-a)
# não entrega o armazenamento de MDT; os tetos seguem a mesma disciplina de RAM da ESCALA_* acima. A distância
# máxima de visada/viewshed é o que o adversário do item tenta estourar (alvo a 200 km = 422, nunca calcula).
ANALISE3D_CELULAS_MAX = 250_000        # mesma ordem do teto multiescala (proteção de RAM/disco)
ANALISE3D_ALTURA_MAX_M = 10_000.0      # altura de terreno/observador/alvo/sólido; Everest × 1 sobra
ANALISE3D_DISTANCIA_MAX_M = 30_000.0   # visada e viewshed recusam alvo além disso (refutação: 200 km)
ANALISE3D_AMOSTRAS_MAX = 20_000        # pontos de perfil/visada por chamada
ANALISE3D_GDAL_TIMEOUT_S = 120         # gdal_viewshed por subprocesso, sempre com relógio
ANALISE3D_SOLIDOS_MAX = 500            # sólidos (extrusões) por análise de sombra
ANALISE3D_SOLIDO_VERTICES_MAX = 200    # vértices do polígono de cada sólido
# ---------------------------------------------------------------- console da plataforma (item L0-07-f)
PLATAFORMA_SUSPENSAO_MENSAGEM_MAX = 300   # mensagem mostrada aos membros do inquilino suspenso (503); cabe num aviso

# --- edição em lote (L2-03-f-edicao-em-lote-calculo-campo; `POST /api/camadas/{id}/lote`)
LOTE_SINCRONO_MAX = 5_000                 # hipótese do item: acima disto roda como job (L0-05), com progresso
LOTE_TRANSACAO = 1_000                    # feições por sub-lote dentro da transação única (progresso a cada sub-lote)
LOTE_PREVIA = 10                          # linhas da pré-visualização (antes/depois), hipótese do item
LOTE_IDS_MAX = 50_000                     # ids explícitos numa seleção (acima disto use `onde` ou `todas`)
LOTE_FALHAS_MAX = 100                     # falhas por feição devolvidas no modo parcial (o resto vira contagem)
LOTE_EXPRESSAO_MS = 500                   # orçamento do avaliador POR LINHA (mesmo teto do servidor do L2-10-c)
LOTE_JOB_TIMEOUT_S = 1_800                # teto do job (refutação: "mede se o job respeita o timeout")
LOTE_MAPEAMENTO_MAX = 500                 # pares campo_destino: campo_origem em copiar/mover (teto de campos da camada)
# ---------------------------------------------------------------- relatórios do admin (item L0-07-e; limites iguais aos
# relatórios de uso da Esri, declarados em GET /api/relatorios/tipos)
RELATORIO_JANELA_DIAS = 366       # janela máxima de um relatório: 12 meses
RELATORIO_LINHAS_MAX = 10_000     # linhas por relatório; acima disso o CSV é cortado e o resultado diz truncado
RELATORIO_POR_TIPO_HORA = 1       # pedidos por tipo por hora pela API (agenda disparada pelo worker não conta)

# --- fronteira de Pareto do motor multicritério (L3-08-pareto): análise sem agregação, 2 a 4 objetivos.
# A resposta traz uma linha por unidade (id, ordem, valores) e a camada traz a geometria da fronteira, as duas
# em memória; 50.000 unidades × 4 objetivos são ~1,6 MB de número mais a geometria, dentro do teto de corpo da
# API. Acima disso a rota recusa com o número dizendo por quê, em vez de a máquina engasgar (o teto de célula
# do motor de grades é 250.000, cinco vezes maior de propósito: gerar a grade é barato, devolvê-la não é).
PARETO_UNIDADES_MAX = 50_000
# --- chamados de suporte (L7-13-a-chamados; migração 20260908T2230_chamados_suporte.sql). O contexto vem do
# navegador do cliente e nunca é confiado: o servidor recorta strings, conta entradas e descarta o que passa
# dos tetos abaixo (nada aqui é dado de outra fonte). A captura de tela entra como data URL de PNG dentro do
# MESMO corpo JSON (o CSRF sob cookie exige application/json em toda escrita — ADR 0002 seção 5.3; mesmo truque
# base64-sob-JSON da miniatura e do logotipo), e os anexos comuns passam pela prova tipo × conteúdo do pipeline
# de upload (app/uploads/tipos.py::verificar_conteudo) + varredura de cabeçalho (app/varredura_conteudo.py).
CHAMADO_TITULO_MAX = 200
CHAMADO_DESCRICAO_MAX = 20_000
CHAMADO_COMENTARIO_MAX = 10_000
CHAMADO_SEVERIDADES = ("baixa", "media", "alta", "critica")
CHAMADO_ESTADOS = ("aberto", "em_analise", "aguardando_cliente", "resolvido", "fechado")
CHAMADO_CONTEXTO_BYTES_MAX = 64_000        # contexto inteiro serializado; o que passa é cortado com marca
CHAMADO_REQ_IDS_MAX = 20                   # as últimas 20 requisições (hipótese do item)
CHAMADO_REQ_ID_TAM = 16                    # req_id são 16 hex (app/log.py::req_id); o que não casa é descartado
CHAMADO_CAPTURA_BYTES_MAX = 2_000_000      # PNG decodificado; 2 MiB cobre tela 1280×800 com folga
CHAMADO_ANEXO_BYTES_MAX = 8_000_000        # anexo comum; acima disso o upload retomável (L0-04-a) é o caminho
CHAMADO_DOM_ENTRADAS_MAX = 60              # estrutura do DOM capturada: nº de elementos descritos
CHAMADO_DOM_TEXTO_MAX = 120                # e o texto de cada entrada, cortado aqui
# SLA de primeira resposta por severidade, em horas (hipótese: "SLA de primeira resposta por severidade
# (L7-22)"). L7-22-sla-e-incidentes (pendente) é quem deve mover estes números para dado medido em tabela;
# enquanto isso valem os valores declarados aqui, exibidos junto do tempo medido em toda leitura do chamado.
CHAMADO_SLA_PRIMEIRA_RESPOSTA_HORAS = {"critica": 4, "alta": 8, "media": 24, "baixa": 72}
# --- recurso partilhado com dimensão de inquilino (conserto de classe 06/09, laudos ataque-g2/g3/g4/g6).
# Cinco adversários independentes mediram o mesmo padrão: o que é por LINHA estava protegido (RLS, filtro de
# dono, contexto por inquilino), o que é RECURSO PARTILHADO não tinha dimensão de inquilino nenhuma. Os
# números abaixo são tetos da INSTALAÇÃO inteira; app/jobs/eventos.py divide cada um pelo número de
# processos da API (PLAT_API_PROCESSOS) antes de aplicá-lo dentro do processo.
SSE_POR_USUARIO = 10        # conexões de eventos abertas por usuário (era 10 POR PROCESSO = 20 na unidade)
SSE_POR_INQUILINO = 40      # teto novo: sem ele um inquilino com muitos usuários consome a máquina inteira
SSE_TOTAL = 200             # teto novo: orçamento da instalação, independente de quantos inquilinos existem
CEIFA_API_INTERVALO_S = 30  # a API ceifa os jobs sem sinal do PRÓPRIO inquilino no máximo a cada 30 s
CEIFA_LIMITE_S = 60         # mesmo LIMITE_SEM_SINAL_S do worker (app/jobs/worker.py); piso na função SQL
CHAVE_RESERVADA = "sys:"    # espaço de nome das chaves de trinco dos periódicos da plataforma
# --- regras de atributo de rede (L4-29-regras-de-atributo-de-rede; migração 20260908T1934_regras_atributo_rede.sql):
# perfis cálculo/restrição/validação sobre `plat.rede_objeto`. A refutação do item é o laço
# "jusante de jusante": o motor NÃO itera — cada rodada avalia cada regra UMA vez por objeto
# (declarado em docs/adr/20260908T1945-regras-atributo-de-rede.md), então não existe fixpoint;
# os tetos abaixo freiam o tamanho da rodada, não a profundidade da iteração.
REDE_REGRA_MAX = 1_000          # regras ativas por (inquilino, perfil) numa rodada
REDE_REGRAS_OBJETOS_MAX = 50_000   # objetos de rede avaliados por rodada de cálculo
REDE_REGRAS_ITENS_MAX = 10_000  # itens de uma validação em lote (acima disso: truncado=true)
REDE_REGRAS_ERROS_MAX = 100     # erros de avaliação guardados no resultado de uma rodada (o total é contado)
# --- consumidores e endereços da rede (L4-20-consumidores-e-enderecos; migração
# 20260908T1710_consumidores_enderecos.sql): cruzamento endereço do censo × rede, consumidores a
# jusante e regra de agregação de consumo. REDE_AGREGACAO_MIN_UCS é a regra do item: consumo só
# aparece na API quando a agregação cobre pelo menos 5 unidades consumidoras; por unidade, nunca.
REDE_ENDERECOS_MAX = 500_000        # teto de endereços por geração (proteção de RAM/tempo da consulta)
REDE_RAIO_REDE_MAX_M = 2_000.0      # raio máximo de busca de rede a partir do endereço
REDE_RAIO_PADRAO_M = 700.0          # portão do item: endereço com rede a até 700 m
REDE_RAIO_BT_PADRAO_M = 135.0       # presença de baixa tensão (calibração na base da cooperativa de teste)
REDE_JUSANTE_TRECHOS_MAX = 200_000  # teto de trechos por cálculo de jusante (grafo em memória)
REDE_JUSANTE_NO_MAX = 200_000       # teto de nós do grafo
REDE_AGREGACAO_MIN_UCS = 5          # regra do adversário: agregação mínima exibida quando há consumo
# --- pipeline único de upload (L7-03-a-antivirus-upload; app/varredura_conteudo.py POLITICAS): tamanho por
# classe de upload e lista de Content-Type permitida por classe (paridade com uploadFileExtensionAllowedList da
# Esri, que é por extensão; aqui é por tipo PROVADO pelos bytes). Anexo de feição/item cabe em 100 MiB (foto,
# PDF, planilha); imagem de perfil/logotipo/miniatura já tem 1 MiB nos itens próprios.
ANEXO_BYTES_MAX = 100 * 1024 * 1024
IMAGEM_UPLOAD_BYTES_MAX = 1 * 1024 * 1024
CLAMD_MAX_BYTES = 25 * 1024 * 1024      # StreamMaxLength padrão do clamd; acima disso só o início é varrido
CLAMD_TIMEOUT_S = 20.0                  # clamd fora do ar = recusa (nunca "passa sem varrer" quando configurado)
# ---- L6-01-i-raster-e-arquivos: camadas de ARQUIVO do acervo da casa (acervo.camada_arquivo) no catálogo
ACERVO_ARQUIVO_BYTES_MAX = 2 * 1024 * 1024 * 1024  # teto por arquivo (igual a RASTER_BYTES_MAX; guardrail D21)
ACERVO_ARQUIVO_LOTE_MAX = 50                       # arquivos por chamada de exposição em lote
ACERVO_ARQUIVO_LOTE_BYTES_MAX = 3 * 1024 * 1024 * 1024  # soma do lote (D21: a trilha trabalha com <= 3 GB)
ACERVO_ARQUIVO_LISTA_MAX = 500                     # linhas por página de GET /api/acervo/arquivos
# --- geocodificação de tabela (L2-11-a-geocodificacao-csv): CSV/XLSX com endereço vira job de geocodificação em
# lote reusando o motor do L2-11-b; teto de linhas por lote para não estourar memória do worker leve (disco a
# 98%, sem processamento em memória sem limite — regra da trilha).
GEOCODIFICADOR_LOTE_MAX_LINHAS = 20_000
GEOCODIFICADOR_LOTE_LIMIAR_PENDENTE_PADRAO = 60.0   # score abaixo disso também vira pendente, mesmo com tipo bom
GEOCODIFICADOR_LOTE_TITULO_MAX = 250
ESCALA_AMOSTRAS_LOTE_MAX = 20_000     # amostras de fator por chamada de POST (streaming não é o item; teto direto)
# --- limite de taxa por inquilino/plano (L7-03-b-rate-limit-abuso; app/limite_taxa.py, docs/SEGURANCA.md §9):
# camada 2 do item (a camada 1 é o nginx por IP, zonas plat_api/plat_tiles em deploy/nginx.conf; a camada 3 é
# o fail2ban sobre 401/429 repetidos, deploy/fail2ban/). Cada chave abaixo é (padrão, mínimo, máximo) por
# tenant.config.limites.<chave> — MESMA faixa/corte de AUTH_PADROES (nunca permite política MAIS FROUXA que o
# mínimo, nunca MAIS APERTADA que impediria uso normal); "tiles" fica pronto para o item L1-02-tiles-token
# (ainda não mesclado nesta trilha, ver ADR desta trilha §5) — o mecanismo é genérico por escopo, testado aqui
# só com "api" contra rotas reais; anexar "tiles" a uma rota de ladrilho é um passo de fiação, não de desenho.
LIMITE_TAXA_PADROES: dict[str, tuple] = {
    # 6000/min (100/s sustentado) é DE PROPÓSITO alto: este teto corre em TODA requisição autenticada da CASA
    # inteira (`app/auth/sessao.py::resolver`), inclusive a suíte de teste inteira martelando os inquilinos
    # demo/demo2 (`sessao_a`/`sessao_b`, escopo de sessão do pytest) — um teto pensado só para "uso normal de
    # um cliente" derrubaria `make check` por motivo nenhum do produto. 100/s já é bem acima do que um cliente
    # legítimo sustenta (a Esri, referência do item, não documenta um número; este é o piso defensável: pára
    # abuso de volume mantendo folga generosa para teste e uso real). Um inquilino real que precise de mais
    # ajusta pelo próprio `config.limites.api_por_minuto` (corte de faixa abaixo garante que nunca fica ABAIXO
    # do mínimo nem ACIMA do máximo).
    "api_por_minuto": (6000, 5, 500_000),          # por tenant_id, todo /api/* autenticado (sessão OU token)
    "tiles_por_minuto": (12000, 10, 2_000_000),    # por tenant_id, /svc/<token>/(raster|mosaico) e /tiles/*
}
LIMITE_TAXA_JANELA_S = 60           # janela deslizante única para os dois escopos acima (segundos)
LIMITE_TAXA_ESCOPOS = ("api", "tiles")
LIMITE_TAXA_RETRY_AFTER_MIN_S = 1   # nunca manda Retry-After: 0 (RFC 6585 recomenda um valor positivo)
# ---- L3-05-localizar-regioes: localizar N regiões contíguas sobre a grade de favorabilidade
REGIOES_N_MAX = 30                    # o mesmo teto da referência (Locate Regions: 1-30)
REGIOES_CELULAS_MAX = 4_000_000       # células da grade aceitas por chamada (2.000×2.000; acima disso é job)
REGIOES_TEMPO_LIMITE_S = 120          # a rota é síncrona: acima disto o pedido é grande demais para a tela
# ---------------------------------------------------------------- provisionamento federado (item L0-08-e)
PROVISIONAMENTO_REGRAS_MAX = 200          # regras (valores do IdP mapeados) por provedor
PROVISIONAMENTO_GRUPOS_POR_REGRA = 50     # grupos internos por regra
PROVISIONAMENTO_GRUPOS_IDP_MAX = 1000     # valores do atributo de grupos lidos do IdP por login (o resto é ignorado)
PROVISIONAMENTO_VALOR_MAX = 200           # tamanho de um valor de grupo do IdP
# ---- L3-09-backtest-decisao-real: comparar o ranking do modelo com as escolhas reais
BACKTEST_PONTOS_MAX = 50_000          # escolhas por chamada (a grade regional de teste tem ~600)
BACKTEST_PERMUTACOES_MAX = 20_000     # sorteios do nulo por chamada (a rota é síncrona)

# --- traçado de custo mínimo sobre a grade do motor multicritério (L3-10-corredor-custo-minimo)
# O traçado carrega a grade INTEIRA da execução em memória (duas matrizes float32/bool), logo o teto de células
# é o mesmo da grade (ESCALA_CELULAS_MAX = 250 mil = 2 MB de custo). O que precisa de teto próprio é a
# GEOMETRIA do corredor: unir 100 mil quadrados em PostGIS e mandar isso por HTTP é o que derruba a tela, não
# o cálculo. Acima do teto a resposta traz a contagem e diz que omitiu a geometria.
CORREDOR_CELULAS_GEOJSON_MAX = 20_000
# --- consulta SQL do cliente no banco externo (L6-02-j-bancos-externos; app/conexao/consulta_sql.py): LIMIT
# obrigatório e explícito, teto de linhas e de texto; o statement_timeout é o mesmo de CONEXAO_PG_ESTATEMENT_TIMEOUT_MS
CONEXAO_PG_CONSULTA_LINHAS_MAX = 5000
CONEXAO_PG_CONSULTA_TEXTO_MAX = 4000
# --- catálogo de conectores públicos (L6-02-m-catalogo-endpoints-brasil; app/conexao/endpoints_publicos.py):
# o teste de "vivo" pede o documento do protocolo (GetCapabilities, f=json, raiz STAC) e confere a assinatura do
# corpo; capabilities de órgão grande passam de 1 MiB (a INDE, o IBGE), por isso o teto próprio de bytes.
ENDPOINT_PUBLICO_LER_TIMEOUT_S = 20.0    # leitura do documento de teste (órgão lento monta capabilities em segundos)
ENDPOINT_PUBLICO_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB: acima disso o serviço respondeu XML e conta como vivo (OGC)
ENDPOINT_PUBLICO_RETESTE_DIAS = 7        # cadência do job endpoints_publicos.retestar (B12: "retestado por semana")
ENDPOINT_PUBLICO_FALHAS_PARA_MORTO = 1   # 1 teste vermelho já tira da lista (vai para 'fora do ar'; volta ao passar)
ENDPOINT_PUBLICO_PAGINA_MAX = 500        # a tela lista o catálogo inteiro de uma vez (dezenas, não milhares)
# --- descoberta por catálogo CSW 2.0.2 (L6-06-descoberta-csw; app/conexao/csw.py): a INDE devolve ~9 KB por
# registro ISO 19139 completo, logo 20 registros cabem com folga em CONEXAO_RESPOSTA_MAX_BYTES (1 MiB); o tempo
# de leitura é maior que o do teste de saúde porque o catálogo monta a resposta (medido 3-8 s na INDE em 07/09).
CSW_MAX_REGISTROS = 20                   # maxRecords por GetRecords (e teto do que a tela pede)
CSW_LER_TIMEOUT_S = 20.0                 # leitura de GetRecords/GetRecordById (buscar_seguro)
CSW_TEXTO_MAX = 1000                     # corte de resumo/licença/linhagem guardados na ficha (config <= 8 KiB)
CSW_PALAVRAS_MAX = 30                    # palavras-chave guardadas por registro
CSW_TEXTO_BUSCA_MAX = 200                # tamanho do texto livre da busca (vira AnyText like '%...%')
# --- motor multicritério (L3-01-a/b; ADR 0016, decisões A1/A3/A7 do L3L6_CONCEITO). Os tetos de unidade e de
# área não são arbitrários: MEDIDO 06/09/2026 nesta máquina, uma grade quadrada de 250 m sobre 2.000 km²
# (32.000 células) leva ~13 s e ocupa ~19 MB; `df -h /mnt/pgdata` mostra 98 % de uso, então 1 milhão de
# unidades num conjunto (≈ 600 MB com geometria e índice) é o máximo que cabe com folga. Acima disso a API
# recusa com `grade_grande_demais` e diz para aumentar o lado ou reduzir a área, nunca corta em silêncio
AMC_LADO_M_MIN = 10.0                 # abaixo disso a grade deixa de ser unidade de análise e vira pixel
AMC_LADO_M_MAX = 100_000.0            # 100 km: célula maior que isto não cabe em nenhuma zona UTM sem distorcer
AMC_AREA_ESTUDO_KM2_MAX = 2_000_000.0 # ~1/4 do Brasil: acima disso a zona UTM única do centróide perde sentido
AMC_UNIDADES_MAX = 1_000_000          # unidades por conjunto (grade ou feições)
AMC_FEICOES_INLINE_MAX = 20_000       # feições por envio síncrono de conjunto do tipo 'feicoes'
AMC_MODELOS_POR_INQUILINO = 500       # modelos vivos (apagado_em IS NULL) por inquilino
AMC_CONJUNTOS_POR_INQUILINO = 200     # conjuntos de unidades por inquilino
AMC_VERSOES_POR_MODELO = 500          # versões de um modelo (cada edição cria uma; imutáveis, nunca apagadas)
AMC_UNIDADES_PAGINA_MAX = 5_000       # unidades por página em GET /api/amc/conjuntos/{id}/unidades
AMC_RESULTADOS_PAGINA_MAX = 5_000     # linhas por página em GET /api/amc/execucoes/{id}/resultados
# --- importação de metadado ISO 19139 (L0-09-c-xml-iso-validacao; POST /api/itens/{id}/metadado.xml). O teto
# de bytes é 2 MiB: o maior registro do catálogo aberto da INDE medido neste item tem 31 KiB, e o corpo padrão
# da API (CORPO_MAX_PADRAO_BYTES, 10 MiB) é generoso demais para um documento de metadado — a refutação do item
# manda recusar um XML de 50 MB antes de o analisador tocar nele. ELEMENTOS_MAX limita o relatório do que não
# coube (documento com dezenas de milhares de elementos vira relatório inútil, não erro).
METADADO_XML_BYTES_MAX = 2 * 1024 * 1024
METADADO_XML_ELEMENTOS_MAX = 20_000
METADADO_NAO_COUBE_MAX = 200              # linhas distintas no relatório do que não coube
# --- galeria de mapas base por inquilino (L2-01-e-mapas-base)
MAPA_BASE_ZOOM_MAX = 19                            # tile.openstreetmap.org não publica além disso
MAPA_BASE_OSM_HOSTS = ("a.tile.openstreetmap.org", "b.tile.openstreetmap.org", "c.tile.openstreetmap.org")
# política de uso do OSM (https://operations.osmfoundation.org/policies/tiles/): identificar o cliente
MAPA_BASE_OSM_USER_AGENT = "plat-mapa-base/1 (+https://iagrointel.com; contato@iagrosat.com)"
MAPA_BASE_OSM_CACHE_BYTES_MAX = 100 * 1024 * 1024  # 100 MiB de teto do cache em disco (disco da casa a 98 %)
MAPA_BASE_OSM_CONECTAR_TIMEOUT_S = 3.0
MAPA_BASE_OSM_LER_TIMEOUT_S = 8.0
MAPA_BASE_OSM_RESPOSTA_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB: um PNG 256×256 nunca chega perto disso
# Teto de disco do mapa base instalado (PMTiles vetorial + teto do cache do proxy raster). A decisão D27 do
# dono (Protomaps do Brasil inteiro = gigabytes × disco da casa a 98 %) está ABERTA: enquanto não houver
# número do dono, vale o teto já em vigor no repositório — os 50 MB do recorte PMTiles declarados em
# web/dados/basemap/PROVENIENCIA.md (item L2-01-a) mais MAPA_BASE_OSM_CACHE_BYTES_MAX do cache do proxy.
MAPA_BASE_PMTILES_BYTES_MAX = 50 * 1000 * 1000
MAPA_BASE_DISCO_BYTES_MAX = MAPA_BASE_PMTILES_BYTES_MAX + MAPA_BASE_OSM_CACHE_BYTES_MAX
# item L2-02-e-simbolos-sprites-glifos: ícone SVG enviado pelo inquilino
SIMBOLO_SVG_BYTES_MAX = 64 * 1024
SIMBOLO_NOME_MAX = 64
SIMBOLO_CATEGORIA_MAX = 40
SIMBOLO_GALERIA_BUSCA_MAX = 100
# --- ferramentas de análise (L2-05-a; L2_CONCEITO C8): job por padrão, síncrono só abaixo do custo declarado
FERRAMENTA_SINCRONO_CUSTO_MAX = 5000       # custo = feições × complexidade declarada no manifesto; acima disso só job
FERRAMENTA_JOB_MEMORIA_MB = 1024            # RLIMIT_DATA do filho que roda uma ferramenta
FERRAMENTA_JOB_TIMEOUT_S = 1800             # 30 min por execução; ferramenta mais longa é outro tipo de job
BUFFER_DISTANCIA_M_MAX = 100_000            # 100 km: acima disso o buffer geodésico deixa de fazer sentido em camada

# --- ferramentas vetoriais elementares (L2-05-b): o teto de feições é por ENTRADA, conferido antes de operar
VETOR_FEICOES_MAX = 2_000_000               # acima disso a ferramenta recusa a entrada em vez de encher o disco
PONTOS_ALEATORIOS_MAX = 10_000              # pontos sorteados por feição em pontos_aleatorios

# --- ferramentas de relação entre camadas (L2-05-c): índice espacial, grade e tabela de distâncias
SUBDIVIDIR_VERTICES = 256                   # ST_Subdivide nas entradas poligonais: partes com até tantos vértices
GRADE_CELULAS_MAX = 250_000                 # células que agregar_pontos aceita desenhar antes de recusar o tamanho
DISTANCIAS_PARES_MAX = 5_000_000            # pares origem x destino sem vizinhos_por_origem nem distancia_maxima
DISTANCIAS_VIZINHOS_MAX = 1_000             # teto de vizinhos_por_origem na tabela de distâncias

# --- grades, densidade, padrões espaciais e interpolação (L2-05-d)
PADROES_FEICOES_MAX = 200_000               # Gi*, Moran e vizinho mais próximo carregam as coordenadas em memória
H3_NIVEL_MIN = 5                            # níveis aceitos na tesselação H3 (aresta de ~ 8 km a ~ 66 m)
H3_NIVEL_MAX = 10
DENSIDADE_RAIO_M_MAX = 100_000              # raio do kernel: mesmo teto do buffer geodésico
IDW_VIZINHOS_MAX = 64                       # amostras usadas por célula na interpolação por inverso da distância
CONTORNO_LINHAS_MAX = 200_000               # isolinhas geradas antes de a ferramenta recusar o intervalo
# --- ferramentas raster (item L2-05-e) ---------------------------------------------------------------
# Tetos de PRODUÇÃO das ferramentas de análise raster. O que cada um evita: zonas demais numa execução
# (a memória do resultado é proporcional a elas), saída maior que o que o appliance escreve em disco de
# trabalho, e vetorização/curva de nível que produziriam uma camada impossível de desenhar.
FERRAMENTA_RASTER_ZONAS_MAX = 20_000          # feições de uma camada de zonas por execução
FERRAMENTA_RASTER_PIXELS_SAIDA_MAX = 4_000_000_000  # pixels do raster de saída (4 Gpx)
FERRAMENTA_RASTER_FEICOES_SAIDA_MAX = 500_000  # feições de curva de nível / vetorização por execução
FERRAMENTA_RASTER_ENTRADAS_MAX = 20           # rasters numa calculadora ou num mosaico
# --- ferramentas de rede (L2-05-f): isócrona, rota por paradas, matriz origem-destino, K mais próximas,
# conexão à rede (snap) e localizar-alocar. Todas chamam o serviço de rota do L2-11-c (app/rede), que fala
# com o OSRM isolado `plat-osrm-guarulhos`; os tetos abaixo são do PEDIDO, não do grafo, e aparecem no
# manifesto de cada ferramenta (campo `limites`) para o cliente ler antes de mandar trabalho grande.
REDE_ISOCRONAS_MAX = 25               # origens × intervalos por execução de área de serviço
REDE_INTERVALOS_MAX = 5               # intervalos de tempo por execução (anéis da área de serviço)
REDE_PARADAS_MAX = 25                 # paradas por rota (mesmo teto que a otimização por /trip aguenta bem)
REDE_MATRIZ_LADO_MAX = 1000           # N e M da matriz origem-destino, cada um
REDE_MATRIZ_PARES_MAX = 1_000_000     # N×M declarado (1.000×1.000); o serviço parte em blocos do teto do OSRM
REDE_SNAP_PONTOS_MAX = 500            # pontos por execução de conectar à rede (1 chamada /nearest por ponto)
REDE_K_MAX = 20                       # K de "K instalações mais próximas"
REDE_ALOCAR_P_MAX = 25                # P instalações escolhidas por localizar-alocar (heurística gulosa)

# --- formulário de coleta por XLSForm (L2-07-b-formulario-de-coleta-xlsform; app/coleta)
XLSFORM_TAMANHO_MAX = 2 * 1024 * 1024    # 2 MiB por planilha (formulários reais têm dezenas de KiB)
FORMULARIO_CAMPOS_MAX = 500              # perguntas por formulário (mesmo teto de campos da camada)
FORMULARIO_LISTA_MAX = 5_000             # linhas por lista de escolhas (cascata de município cabe)
FORMULARIO_REPETICOES_MAX = 200          # linhas por repetição numa única resposta
FORMULARIO_ANEXOS_MAX = 20               # anexos por resposta
# ---------------------------------------------------------------- modelos 3D (item L2-09-c)
MODELO3D_ARQUIVO_BYTES = 200 * 1024 * 1024   # teto do IFC/GLB de entrada; a refutação do item usa 50 MB
MODELO3D_GLB_BYTES = 300 * 1024 * 1024       # teto do glTF binário PRODUZIDO pela conversão
MODELO3D_MEMORIA_MB = 1024                   # teto do trabalhador (PLAT_WORKER_MEMORIA_MB): o grafo do IFC
MODELO3D_TIMEOUT_S = 1800
MODELO3D_NOME_MAX = 200                      # mesmo teto de CHECK(length(nome)<=200) da migração
MODELO3D_ELEMENTOS_PAGINA_MAX = 500          # elementos por página em GET /api/modelos/{id}/elementos
MODELO3D_PAGINA_MAX = 200                    # modelos por página em GET /api/modelos

# --- versionamento por ramo (item L2-13-a): teto de ramos ABERTOS por camada. A camada pode declarar o
# seu próprio teto menor em `dados.versionamento.ramos_max`; este é o máximo que ela pode declarar e o
# valor usado quando ela não declara nada. Não é um limite físico: cada ramo aberto acrescenta uma perna
# ao UNION de nada (a leitura consulta UM ramo por vez), mas cada ramo aberto é uma reconciliação a
# fazer, e um número redondo declarado vale mais que um teto implícito descoberto quando dói.
VERSOES_POR_CAMADA_MAX = 50
VERSAO_NOME_MAX = 128

# --- atualização viva de painel e mapa por SSE (L2-06-d; migração 20260908T0702_camada_eventos_vivos.sql).
# Conexão SSE é conexão TCP presa: os dois tetos abaixo são o que impede uma instalação de ficar sem soquete
# por causa de abas esquecidas abertas. São POR PROCESSO da aplicação (o contador vive na memória do
# processo, como o do progresso de job) — com N workers o teto efetivo do inquilino é N × VIVO_SSE_POR_INQUILINO.
VIVO_SSE_POR_INQUILINO = 100          # refutação do item: 1.000 conexões têm de bater em 429
VIVO_SSE_POR_USUARIO = 10             # uma pessoa não consome sozinha a cota do inquilino
VIVO_SSE_CAMADAS_MAX = 50             # camadas assinadas por conexão (um painel real usa 2 a 6)
VIVO_SSE_DURACAO_MAX_S = 1800         # a conexão fecha sozinha em 30 min; o navegador reconecta com Last-Event-ID
VIVO_SSE_KEEPALIVE_S = 15             # comentário `: keepalive` que impede proxy de derrubar conexão ociosa
VIVO_EVENTO_JANELA_MIN = 15           # retenção de plat.camada_evento = janela de recuperação da reconexão
VIVO_DEBOUNCE_MS = 1000               # atraso do navegador antes de refazer a consulta (coalesce de rajada)

# --- entrada de eventos em tempo real (item L2-14-a-ingestao-de-fluxos; processo plat-fluxo, porta 8155).
# O teto de corpo do receptor é MENOR que CORPO_MAX_PADRAO_BYTES da API: um evento de fluxo é uma linha de
# telemetria, não um arquivo; a refutação do item manda recusar um JSON de 10 MB, e é este número que recusa.
FLUXO_PORTA = 8155                        # unidade plat-fluxo (deploy/plat-fluxo.service; C14 do L2_CONCEITO)
FLUXO_CORPO_MAX_BYTES = 4 * 1024 * 1024   # 4 MiB por pedido do receptor HTTP (e por quadro de WebSocket)
FLUXO_LOTE_MAX = 20_000                   # eventos por pedido; 10 mil/s com 2 pedidos/s cabe num lote só
FLUXO_CAMPOS_MAX = 200                    # campos mapeados por fonte (mesma ordem de EDICAO_ATRIBUTOS_MAX)
FLUXO_TEXTO_MAX = 4_096                   # caracteres por valor de campo texto
FLUXO_RASTRO_MAX = 200                    # caracteres do id de rastro (refutação: id de 1 MB é recusado)
FLUXO_WKT_MAX = 4_096                     # caracteres do WKT de um ponto
FLUXO_URL_MAX = 2_048                     # mesma ordem do CHECK de plat.conexao.url
FLUXO_MQTT_TOPICO_MAX = 500               # filtro de tópico assinado no broker externo
FLUXO_INTEIRO_MAX = 9_007_199_254_740_992  # 2^53: acima disso o número não sobrevive ao JSON do navegador
FLUXO_TEMPO_FUTURO_MAX_S = 300            # 5 min de folga de relógio; além disso o evento é descartado
FLUXO_TEMPO_PASSADO_MAX_DIAS = 3_650      # 10 anos: histórico legítimo passa, lixo com época zerada não
FLUXO_FILA_MAX = 200_000                  # eventos na fila em memória do processo antes de descartar (contado)
FLUXO_LOTE_INTERVALO_S = 1.0              # um lote por segundo (C14)
FLUXO_LOTE_LINHAS_MAX = 20_000            # linhas por INSERT em lote; acima disso o lote é partido
FLUXO_FILTRO_PASSOS_MAX = 2_000           # orçamento do filtro POR EVENTO (o padrão do servidor é 100 mil)
FLUXO_FILTRO_MS = 50.0                    # orçamento de relógio do filtro por evento
FLUXO_BUFFER_PAUSA_S = 30                 # fonte pausada guarda este tanto de segundos de eventos
FLUXO_BUFFER_PAUSA_MAX = 50_000           # ... e nunca mais que isto, mesmo com teto por segundo alto
FLUXO_SONDAGEM_INTERVALO_MIN_S = 5        # sondar mais rápido que isto é abusar do serviço de terceiro
FLUXO_SONDAGEM_INTERVALO_MAX_S = 86_400
FLUXO_EVENTOS_LISTA_MAX = 1_000           # eventos por página em GET /api/fluxos/{id}/eventos
FLUXO_RECONEXAO_MIN_S = 1.0               # espera inicial de reconexão do conector (MQTT/WebSocket/AIS)
FLUXO_RECONEXAO_MAX_S = 60.0              # ... com dobra a cada tentativa, até este teto
FLUXO_MQTT_KEEPALIVE_S = 60               # keep-alive anunciado no CONNECT do MQTT 3.1.1
FLUXO_AIS_LINHA_MAX = 1_024               # bytes de uma sentença NMEA (o padrão é 82; a folga é para lixo)
# --- GeoParquet particionado no bucket (L2-15-a-geoparquet-bucket-catalogo). Mesmos tetos de memória/tempo/
# disco do irmão L0-04-h (o intermediário continua sendo um GPKG do ogr2ogr); GRUPO_LINHAS_PADRAO medido
# como ponto de partida razoável (DuckDB docs: 100k-1M linhas por row group; 50k cobre camada pequena sem
# blocos minúsculos demais em partição fina).
GEOPARQUET_MEMORIA_MB = 1024
GEOPARQUET_TIMEOUT_S = 3600
GEOPARQUET_DISCO_MIN_LIVRE_BYTES = 2 * 1024 * 1024 * 1024
GEOPARQUET_FATOR_DISCO = 3
GEOPARQUET_GRUPO_LINHAS_PADRAO = 50_000
GEOPARQUET_GRUPO_LINHAS_MIN = 1_000
GEOPARQUET_GRUPO_LINHAS_MAX = 1_000_000
GEOPARQUET_CAMPOS_MAX = 500
GEOPARQUET_WHERE_MAX = 4000
GEOPARQUET_POR_USUARIO_EM_CURSO = 3
GEOPARQUET_URL_ASSINADA_SEGUNDOS = 900   # 15 min: o bastante para DuckDB/QGIS/Pro abrirem o arquivo

# --- consulta grande sobre Parquet com DuckDB (L2-15-b-consultas-duckdb-em-escala). O motor roda num processo
# próprio, lançado pelo job (que é `pesado`: o worker já serializa "1 pesado por vez" por advisory lock, e é
# essa trava, não uma nova, que garante UMA consulta grande de cada vez por base). MEMORIA_MB é o
# `memory_limit` declarado ao DuckDB e THREADS o seu `threads`: os dois vão para a proveniência do resultado,
# porque tempo medido sem eles não quer dizer nada.
CONSULTA_GRANDE_MEMORIA_MB = 2048
CONSULTA_GRANDE_THREADS = 4
CONSULTA_GRANDE_TEMPO_S = 900            # teto do relógio que interrompe a consulta (con.interrupt)
CONSULTA_GRANDE_JOB_TIMEOUT_S = 1200     # teto do JOB; folgado sobre o teto da consulta para a mensagem chegar
CONSULTA_GRANDE_JOB_MEMORIA_MB = 3072    # RLIMIT_DATA do filho; o processo do DuckDB é neto e cabe dentro
CONSULTA_GRANDE_LINHAS_SAIDA_MAX = 2_000_000   # resultado acima disso é recusado, nunca truncado em silêncio
CONSULTA_GRANDE_SQL_MAX = 2_000          # caracteres do SQL livre: é o teto de GPString do
                                         # vocabulário GP da Esri (app/ferramentas/registro.py),
                                         # e não um número escolhido aqui — quem manda a consulta
                                         # por cliente Esri cabe no mesmo limite da API própria
CONSULTA_GRANDE_ARQUIVOS_MAX = 4_096     # partes Parquet de uma fonte (partição hive fina cabe aqui)
CONSULTA_GRANDE_FONTES_MAX = 8           # fontes Parquet numa consulta (uma view cada)
CONSULTA_GRANDE_GRADE_METROS_MIN = 10
CONSULTA_GRANDE_GRADE_METROS_MAX = 500_000
CONSULTA_GRANDE_LIMIAR_LINHAS_DUCKDB = 5_000_000  # acima disto a ferramenta grande é o caminho, não o PostGIS
# --- ferramentas por job (L2-16-a-sdk-python-geo): a geometria entra no CORPO do job; o teto abaixo
# guarda o worker (e o registro em plat.job.parametros) de um GeoJSON grande demais para buffer em memória.
FERRAMENTA_GEOJSON_MAX_BYTES = 5_000_000  # GeoJSON de entrada por ferramenta (5 MB ≈ 1-2 milhões de vértices)
FERRAMENTA_BUFFER_MAX_M = 100_000.0       # distância de buffer; 100 km já é análise regional, não local
AMC_MATRIZ_PAGINA_MAX = 2_000         # unidades por página em GET /api/amc/execucoes/{id}/matriz (tela do motor
                                      # recombina no navegador: cada unidade traz valor bruto E favorabilidade
                                      # de cada fator, até 64 fatores, logo a página é ~64x mais pesada que a
                                      # de resultados e o teto é proporcionalmente menor)
AMC_PREVISAO_VALORES_MAX = 200_000    # valores por chamada de POST /api/amc/transformacoes/previsao (histograma
                                      # da transformação escolhida; o portão do item L3-01-d mede 100 mil em
                                      # <= 300 ms, este teto deixa o dobro de folga e nada além)

# --- localização semelhante (L3-17-similaridade): pedido é síncrono (sem job), então o teto é o que a
# requisição aguenta responder em segundos, não o que o motor AMC aguenta processar em lote.
SIMILARIDADE_UNIDADES_MAX = 20_000
SIMILARIDADE_CAMPOS_MAX = 50
SIMILARIDADE_REFERENCIAS_MAX = 500
# --- presets do motor multicritério (L3-01-h-presets; migração 20260908T1659_amc_preset.sql):
# preset = conjunto nomeado de pesos e vetos de um modelo, salvo por usuário ou compartilhado no
# inquilino; 'pesos iguais' e os quatro exemplos do motor logístico são INTEGRADOS (código, não
# tabela). A aplicação é SÍNCRONA (recalcula sem job), por isso o teto de unidades é o mesmo freio
# de RAM da grade aninhada (ESCALA_CELULAS_MAX).
AMC_PRESET_FATORES_MAX = 200          # fatores declarados por preset (mesma ordem do modelo)
AMC_PRESET_FATOR_NOME_MAX = 120       # nome de fator dentro do preset
AMC_PRESET_DESCRICAO_MAX = 2000       # mesmo teto de CHECK(length(descricao)<=2000) da migração
AMC_PRESET_UNIDADES_MAX = 250_000     # unidades (linhas da matriz) por aplicação síncrona
# --- critérios sobre a própria feição (L3-06-criterios-de-feicao): a avaliação é SÍNCRONA e roda na tela,
# sobre as feições que chegam no pedido (com os atributos delas), então o teto é o que a requisição responde
# em segundos. Acima do teto a API recusa com `acima_do_sincrono` e manda para o caminho de lote que já
# existe (conjunto de unidades + POST /api/amc/execucoes, job `amc.executar`); nunca corta a lista em silêncio.
AMC_CRITERIOS_FEICAO_MAX = 5_000        # feições por avaliação síncrona (na tela)
AMC_CRITERIOS_POR_AVALIACAO = 20        # critérios por avaliação (o painel compara par a par: 20 = 400 células)
AMC_CRITERIO_RAIO_M_MAX = 100_000.0     # 100 km: raio maior que isto não vale numa única zona UTM
AMC_CRITERIO_CAMADA_PONTOS_MAX = 200_000  # pontos por camada auxiliar num pedido (raio, contenção, distância)
# --- desempenho em escala do motor multicritério (L3-16-desempenho-escala). Contrato de escala do motor:
# ONDE a combinação roda, de quanto em quanto o servidor lê a matriz de fatores e quanta RAM um job de
# extração pode pedir. Os números medidos ficam em tests/medidas/L3-16-desempenho-escala.json e é de lá
# que o MANUAL os cita (teste tests/unit/test_amc_escala_manual.py reprova se alguém digitar à mão).
# AMC_COMBINAR_NAVEGADOR_MAX é o mesmo número nos dois lados: web/js/amc/combinacao.js recusa acima dele
# com `unidades_demais_para_o_navegador` e o cliente refaz o pedido no servidor (nunca combina pela metade).
AMC_COMBINAR_NAVEGADOR_MAX = 50_000   # unidades combinadas no navegador; acima disso, servidor
AMC_BLOCO_UNIDADES = 50_000           # unidades por bloco lido/gravado pelo servidor (pico de RAM constante)
AMC_EXTRACAO_MEMORIA_MB = 4096        # teto DECLARADO do job de extração/recombinação (guardrail do portão do
                                      # item). A máquina pode ter teto menor (PLAT_WORKER_MEMORIA_MB, 1024 MB
                                      # nesta): vale o MENOR dos dois, e é ele que vira RLIMIT_DATA no filho
                                      # (app/jobs/filho.py, item L0-05-e). Ver app.amc.escala.orcamento_mb.
AMC_EXTRACAO_TIMEOUT_S = 1800         # 30 min: o prazo do portão para 1 mi de células × 15 fatores
# Custo MEDIDO da extração, por unidade e por fator. Sai de tests/medidas/L3-16-desempenho-escala.json
# (chave `extracao_por_unidade_por_fator_us`, estatística zonal real sobre GeoTIFF, 07/09/2026) e é o que
# permite ao plano dizer, ANTES de enfileirar, que um trabalho não termina no prazo. Número deliberadamente
# conservador: a medida foi feita com parte das unidades fora do raster, que custam menos que a média real.
AMC_EXTRACAO_US_POR_UNIDADE_FATOR = 719

# --- malha de parcelas (L4-parcelas-01-modelo-de-parcelas; migração 20260908T2140_parcelas.sql):
# seis tabelas orientadas a registro (criada_por/retirada_por = linhagem, paridade com parcel
# fabric em docs/PARIDADE_PARCELAS.md). Os tetos abaixo freiam o TAMANHO de uma rodada
# (importação, consulta de validação, trajeto COGO de uma criação) — a linhagem não itera.
PARCELA_IMPORT_LOTES_MAX = 50_000     # lotes por rodada de import (acima disso: 422, rodada menor)
PARCELA_VALIDACAO_PARES_MAX = 500     # pares de sobreposição devolvidos por consulta (o total é contado)
PARCELA_TRAJETO_MAX = 200             # segmentos COGO na criação de UMA parcela por trajeto
PARCELA_DXF_LINHAS_MAX = 20_000       # segmentos de DXF por rodada de "copiar linhas de CAD"
PARCELA_BUILD_LINHAS_MAX = 20_000     # linhas livres por chamada de build
PARCELA_BUILD_FACES_MAX = 2_000       # faces fechadas aceitas em um build (acima: 422, estique a extent)
PARCELA_DIVIDE_PARTES_MAX = 100       # partes por divisão (EqualArea/ProportionalArea/EqualWidth)
PARCELA_UNIR_MAX = 50                 # parcelas por união (merge)
PARCELA_ATRIBUICAO_MAX = 1_000        # feições por assignFeaturesToRecord
PARCELA_AJUSTE_LINHAS_MAX = 10_000    # linhas observadas numa rede de ajuste LSA (item 03)
PARCELA_QUALIDADE_FACES_MAX = 500     # faces de lacuna devolvidas pela camada de qualidade

# --- pacotes e galeria de modelos (L5-37-pacotes-modelos-entre-inquilinos; migração 20260908T1055).
# Um pacote é só JSON (documentos, estilos, fluxos, formulários) e as fontes DECLARADAS: nenhum dado de
# feição, nenhuma imagem. Por isso o teto de bytes é pequeno de propósito — pacote grande é sinal de que
# alguém pôs dado dentro. O teto de documentos e o de profundidade freiam a caminhada no grafo de
# dependências antes de ela virar consulta sem fim.
PACOTE_DOCUMENTOS_MAX = 200
PACOTE_PROFUNDIDADE_MAX = 8
PACOTE_BYTES_MAX = 4 * 1024 * 1024
PACOTE_MODELOS_MAX = 200           # modelos na galeria por inquilino (o de escopo plataforma conta no dele)
PACOTE_NOME_MAX = 200              # CHECK(length(nome) BETWEEN 1 AND 200) da migração
PACOTE_DESCRICAO_MAX = 2000

# --- site do inquilino (L5-20-sites-paginas-publicas): tetos do documento e do que a página pública consulta
SITE_PAGINAS_MAX = 50            # páginas por site (o menu do cabeçalho fica ilegível muito antes disso)
SITE_NOS_MAX = 400               # nós do documento inteiro (páginas + seções + cartões)
SITE_TEXTO_MAX = 4000            # caracteres do cartão de texto e do rodapé
SITE_GALERIA_ITENS_MAX = 60      # teto duro do cartão de galeria e da busca (o mesmo do LIMIT da função SQL)
SITE_GALERIA_ITENS_PADRAO = 12
SITE_INCORPORADO_ALTURA_MIN = 120
SITE_INCORPORADO_ALTURA_MAX = 1200

# --- edição transacional de feições (L2-03-a-api-edicao-transacional; POST /api/camadas/{id}/edicoes, única
# porta de escrita para navegador/PWA/FeatureServer/OGC). LOTE_MAX = 2× o tamanho medido no portão (1.000
# feições ≤ 3 s), com folga operacional; bem abaixo do lote de 100 mil que a refutação do item manda recusar
# (esse cai primeiro no 413 de CORPO_MAX_PADRAO_BYTES quando o corpo é grande, mas o teto por lista garante o
# 422 mesmo com corpo pequeno e muitas feições minúsculas).
EDICAO_LOTE_MAX = 2_000
EDICAO_ATRIBUTOS_MAX = 500                # campos por feição num único pedido (mesmo teto de INGESTAO_CAMPOS_MAX)
EDICAO_TEXTO_MAX = 65_536                 # 64 KiB por valor de campo texto (mesma ordem de ITEM_DESCRICAO_MAX)
EDICAO_REGRA_CAMPO_MAX = 500              # entradas em dados.regras_campo (mesmo teto de campos da camada)
EDICAO_DOMINIO_VALORES_MAX = 1_000        # valores aceitos por regra de domínio codificado
EDICAO_SRID_MAX = 999_999                 # mesmo teto do esquema de camada_vetorial (029_ingestao_vetor.sql)

# --- integração ArcGIS Online do cliente (item L2-08-migracao-agol): credencial por inquilino em
# `tenant.config.agol` (mesmo padrão de SMTP_* acima) e o job `agol.publicar` (app/agol/tarefas.py), portado
# de `/home/dev/fgr/sig/pipeline/20_agol_publish.py`.
AGOL_PORTAL_MAX = 300
AGOL_USUARIO_MAX = 128
AGOL_CREDENCIAL_MAX = 1024                # senha ou token, antes de cifrar
AGOL_ROTULO_MAX = 100
AGOL_TITULO_MAX = 250
AGOL_CONECTAR_TIMEOUT_S = 6.0
AGOL_LER_TIMEOUT_S = 20.0                 # teste de credencial: curto de propósito (rota síncrona)
AGOL_PUBLICAR_TIMEOUT_S = 300.0           # addItem/publish dentro do job: upload pode ser grande
AGOL_POLL_INTERVALO_S = 4.0               # espera do job assíncrono de publish (mesmo valor do script original)
AGOL_POLL_TENTATIVAS_MAX = 90             # 90 x 4 s = 6 min (mesmo teto do script original: `for _ in range(90)`)
AGOL_FEICOES_MAX = 200_000                # teto de segurança do export GeoJSON (fetchall bounded; camada maior
# que isso é recusada com uma mensagem clara em vez de estourar a memória do worker — item novo desta portagem,
# o script original (`20_agol_publish.py`) não tinha teto nenhum porque rodava numa única fazenda/inquilino)

# --- campo: fila de trabalho, roteiro e visita com foto (item L2-07-campo), portado de rs-coop/certaja/sig
CAMPO_FILA_ALVOS_MAX = 5_000               # feições por fila (mesma ordem de grandeza de EDICAO_LOTE_MAX x2)
CAMPO_ROTEIRO_PARADAS_MAX = 60             # mesmo teto do sistema de origem ("no máximo 60 paradas por rota")
CAMPO_FOTO_BYTES_MAX = 10 * 1024 * 1024    # mesmo teto de MINIATURA_BYTES_MAX; a foto é reamostrada abaixo disso
CAMPO_FOTO_PIXELS_MAX = 40_000_000         # contra bomba de descompressão (mesma técnica de MINIATURA_PIXELS_MAX)
CAMPO_FOTO_LADO_MAX = 2400                 # px do maior lado após redimensionar (mesmo valor do sistema de origem)
CAMPO_ROTA_VELOCIDADE_KMH = 35             # estimativa de fallback (linha reta) quando não há motor de rota real;
# DECLARADA, nunca medida — o sistema de origem já rotula isso como estimativa no aviso devolvido

# --- backup lógico por inquilino e ensaio de restauração (item L0-06-backup-status; app/backup/), portado de
# `/home/dev/fgr/sig/pipeline/backup.sh`/`restore_test.sh`. Disco a 99% nesta máquina (CLAUDE.md) — o código
# NUNCA pode presumir que o schema do inquilino continua pequeno como o de demonstração: o dump é recusado
# (FalhaDefinitiva, arquivo apagado) acima deste teto, ANTES do upload. Mesma ordem de grandeza de
# RASTER_BYTES_MAX/UPLOAD_BYTES_MAX (2 GiB) — não há hoje um schema de inquilino perto disso, mas o teto tem
# de existir mesmo assim (é o que o item pede: "o código não pode presumir").
BACKUP_DUMP_BYTES_MAX = 2 * 1024 * 1024 * 1024   # 2 GiB
BACKUP_DUMP_TIMEOUT_S = 3600                     # pg_dump -Fc do schema do inquilino
BACKUP_DRILL_TIMEOUT_S = 3600                    # download + pg_restore em schema temporário + COUNT(*)
BACKUP_LISTA_MAX = 200                           # linhas por página em GET /api/backup/backups e /ensaios

# --- construtor de formulário de atributos, arrasta-e-solta (item L5-03-form-builder): uma camada tem no
# máximo um plat.formulario, N versões; o desenho é grupo->campo com condicional/cálculo em expressão
# (item L2-10-c-linguagem-expressao). Tetos de negação-de-serviço do próprio desenho (a expressão em si já
# tem os seus, em app/expressao/avaliador_py.py: MAX_TEXTO/MAX_TOKENS/MAX_PROFUNDIDADE).
FORMULARIO_GRUPOS_MAX = 40
FORMULARIO_CAMPOS_POR_GRUPO_MAX = 60
FORMULARIO_DESENHO_BYTES_MAX = 512 * 1024   # jsonb bruto (nome+rótulo+expressões de até 60x40 campos cabe longe disso)
FORMULARIO_VERSOES_MAX = 200                # rascunhos guardados por formulário (histórico do construtor)

# --- telemetria da rede de utilidades (item L4-13-integracao-telemetria): leitura ligada ao ativo,
# particionada por mês (plat.rede_medicao). Lote pequeno de propósito — é publicação de sensor (20 sensores
# x poucas grandezas por tick), não upload em massa; o mesmo teto do item de campo (CAMPO_FILA_ALVOS_MAX) é
# ordem de grandeza maior do que qualquer simulador/gateway real manda de uma vez.
REDE_MEDICAO_LOTE_MAX = 2_000                 # leituras por POST /api/rede/medicao/leituras
REDE_MEDICAO_JANELA_FUTURO_S = 120            # tolerância de relógio do sensor (refutação "timestamp futuro")
REDE_MEDICAO_SERIE_DIAS_PADRAO = 7            # janela padrão do gráfico da ficha do ativo
REDE_MEDICAO_SERIE_DIAS_MAX = 92              # mesmo teto de LOG_JANELA_DIAS
REDE_MEDICAO_SERIE_PONTOS_MAX = 20_000        # linhas devolvidas por série (amostragem simples acima disso)
REDE_MEDICAO_ALARME_JANELA_MIN = 30           # "carregamento > 100% por 30 min" (portão do item)
REDE_MEDICAO_ALARME_LOOKBACK_MIN = 90         # quanto de histórico o motor olha para achar o início do surto
