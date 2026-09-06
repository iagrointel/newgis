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
