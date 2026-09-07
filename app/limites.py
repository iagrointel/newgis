"""Limites e faixas da plataforma, um lugar só (ADR 0002 seção 11; docs/LIMITES.md do L0-12 é gerado daqui).
Cada trilha acrescenta a sua seção abaixo da anterior; nenhuma edita a seção de outra."""

# --- identidade (L0-02)
# política de senha, sessão, bloqueio e token: (padrão, mínimo, máximo) por chave de tenant.config.auth
AUTH_PADROES: dict[str, tuple] = {
    "senha_min": (8, 8, 64),
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
TOKENS_POR_USUARIO = 20
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
DESTAQUES_POR_GRUPO = 24
BUSCA_Q_MAX = 1000
BUSCA_TERMOS_MAX = 200
BUSCA_TRGM_LIMIAR = 0.3
BUSCA_REFORCO_STATUS = 0.25
ITENS_PAGINA_MAX = 200
ITENS_DESLOCAMENTO_MAX = 10_000
LIXEIRA_DIAS = 30
COTA_ITENS = 100_000  # padrão por inquilino, tenant.config.catalogo.cota_itens
USADO_POR_PROFUNDIDADE_MAX = 5

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

# --- conexão externa e SSRF (L6-02-a-modelo-conexao-e-seguranca; app/conexao/): modelo genérico de conexão
# a serviço externo (WMS/WMTS/WFS/OGC API/ArcGIS REST/STAC/GeoParquet/PMTiles — só o MODELO nesta trilha, os
# conectores em si são itens futuros). Tempos curtos de propósito: o teste de saúde nunca prende a requisição
# e o proxy nunca vira um jeito de esgotar a máquina com um serviço lento de propósito (ADR 0012).
CONEXAO_TIPOS = (
    "wms", "wmts", "wfs", "ogc_api", "esri_rest", "stac", "geoparquet", "pmtiles", "postgres_fdw", "s3", "http",
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

# --- ingestão vetorial (L0-04; ADR 0005, reduzido a 4 formatos: shapefile.zip, gpkg, geojson, csv)
INGESTAO_AMOSTRA_VALIDADE = 1000          # feições lidas na amostra de ST_IsValid (ogr2ogr -limit, MEDIDO no ADR)
INGESTAO_MEMORIA_MB = 768                 # job ingestao.inspecionar (cobre GeoJSON de 64 MiB, ADR seção 0.4)
INGESTAO_TIMEOUT_S = 300
CARGA_MEMORIA_MB = 1024                   # job ingestao.carregar (ogr2ogr + ST_MakeValid)
CARGA_TIMEOUT_S = 3600
CARGA_FATOR_COTA = 3                      # estimativa = bytes do arquivo × 3 (MEDIDO: shapefile 14 MB -> tabela 45 MB)
INGESTAO_CAMPOS_MAX = 500                 # mesmo teto do JSON Schema de camada_vetorial (ADR 0004/0005)
INGESTAO_FIDS_RELATORIO_MAX = 1000        # fids corrigidos listados no relatório de ST_MakeValid

# --- intercâmbio de formatos em lote (L6-02-o): exportação por camada nos formatos extra, escrow do inquilino
# em GeoPackage + manifesto JSON e importação em lote, em app/intercambio/
INTERCAMBIO_EXPORTACAO_BYTES_MAX = 2 * 1024 * 1024 * 1024   # 2 GiB: pacote final guardado no Garage
INTERCAMBIO_DISCO_FOLGA = 3               # disco livre exigido = estimativa do pacote × 3 (disco a 98%)
INTERCAMBIO_CAMADAS_ESCROW_MAX = 500      # teto de camadas vetoriais num escrow (job único, timeout 3600 s)
INTERCAMBIO_XLSX_LINHAS_MAX = 500_000     # importação XLSX: acima disso a conversão p/ CSV estoura a memória
INTERCAMBIO_DBF_LARGURA_MAX = 254         # largura máxima de campo texto em DBF (limite do formato)
INTERCAMBIO_MVT_ZOOM = 14                 # zoom de geração/leitura de mbtiles/pmtiles (declarado no relatório)
INTERCAMBIO_MEMORIA_MB = 1024             # job intercambio.exportar_camada / exportar_inquilino / importacoes_lote
INTERCAMBIO_TIMEOUT_S = 3600              # relógio do job de intercâmbio (nome próprio: EXPORTACAO_TIMEOUT_S é do L0-04-h)
INTERCAMBIO_LOTE_ITENS_MAX = 200          # teto de arquivos/camadas por chamada de lote (import ou export)

# --- configurações da organização (L0-07-a-configuracoes-org; GET/PUT /api/org): nome, identidade visual
# (logotipo reaproveitando o adaptador genérico de arquivo do L0-11, classe 'org_logo'), mapa padrão, idioma
# padrão, cotas de armazenamento/usuários e a política de senha/2FA já lida de tenant.config.auth (app/auth/
# politica.py, L0-02) — esta tela só EXPÕE aquele esquema, nunca recria um novo.
ORG_NOME_MAX = 55                         # mesmo teto do "Organization name" da Esri (portão do item-pai L0-07-a)
ORG_COR_PADRAO = "#2463a8"                # mesmo azul de app/catalogo/miniatura.py TRACO, cor de marca padrão
ORG_IDIOMAS = ("pt-BR",)                  # só o que existe em web/js/i18n/; L7-10 acrescenta idioma novo aqui
ORG_ZOOM_MAX = 24                         # teto de zoom de um webmap (padrão MapLibre/Leaflet)
ORG_BASEMAP_MAX = 100
ORG_LOGO_BYTES_MAX = 1 * 1024 * 1024      # 1 MiB (portão do item-pai: "logo > 1 MB recusado")
ORG_LOGO_PIXELS_MAX = 25_000_000          # mesma defesa de bomba de descompressão de app/catalogo/miniatura.py
ORG_LOGO_LADO = 300                       # canvas quadrado 300×300 (portão do item-pai)
ORG_COTA_BYTES_MIN = 100 * 1024 * 1024    # 100 MiB: abaixo disso o próprio inquilino de demonstração não sobe
ORG_COTA_USUARIOS_MIN = 1
ORG_COTA_USUARIOS_PADRAO = 2000           # bem acima do maior lote (LOTE_MAX=100) e do uso medido em demo (T3: 59)

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
EXPORTACAO_CAMPOS_MAX = 500                   # mesmo teto de INGESTAO_CAMPOS_MAX (a lista vem do mesmo item)
EXPORTACAO_WHERE_MAX = 4000                   # caracteres do filtro `where` (o parser do L2-04-b recusa o resto)
EXPORTACAO_NOME_MAX = 120                     # nome do arquivo pedido pelo usuário (sem extensão)
EXPORTACAO_ERRO_BANCO_MAX = 300               # tamanho do erro do banco depois de saneado, no corpo do 400
EXPORTACAO_CODIFICACOES = ("UTF-8", "ISO-8859-1")
EXPORTACAO_CSV_SEPARADORES = (",", ";", "\t", "|")
EXPORTACAO_CSV_DECIMAIS = (".", ",")
EXPORTACAO_BLOCO_LEITURA_BYTES = 8 * 1024 * 1024   # leitura do arquivo pronto em blocos (sha256 e envio); NUNCA
                                              # o arquivo inteiro em memória, nem no envio ao Garage nem na entrega
