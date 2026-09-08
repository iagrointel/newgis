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
