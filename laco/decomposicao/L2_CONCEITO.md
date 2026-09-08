# L2 plataforma — decisões de conceito

Data: 05/09/2026. Par de `L2.json` (82 itens novos sob os 16 existentes da linha, mais 3 transversais). Tudo abaixo é o
que, se estiver errado, obriga a refazer. Para cada decisão: opções, o que custa mudar depois, recomendação com motivo
MEDIDO nesta máquina, LIDO em código que roda na casa ou DOCUMENTO OFICIAL com URL testada (HTTP 200 em 05/09/2026), e o
que a decisão obriga nas outras linhas. Nomes de cliente não aparecem: "SIG de teste interno" (`/home/dev/fgr/sig`, só
leitura), "motor logístico", "motor de LT", "observatório da casa".

## O que foi medido em 05/09/2026 e sustenta as escolhas

- Máquina: 12 vCPU, 23 GB de RAM com 3 GB disponíveis, discos `/` e `/mnt/pgdata` a 98 % (13 e 16 GB livres).
  PostgreSQL 16.13, PostGIS 3.6.3, pg_trgm 1.6, unaccent 1.1, pg_cron 1.6, timescaledb 2.26.4 (instalados);
  postgis_raster, address_standardizer, postgis_tiger_geocoder disponíveis sem instalar; pgRouting ausente, mas o
  pacote `postgresql-16-pgrouting` 4.0.1 está no apt (candidato medido com `apt-cache policy`).
- Binários: ogr2ogr/GDAL 3.8.4 (lê e escreve GPKG, Shapefile, GeoJSON, KML/LIBKML, DXF, CSV, XLSX, OpenFileGDB, MVT,
  PMTiles, FlatGeobuf, GML, SQLite, MBTiles; lê WFS e OAPIF; SEM driver Parquet/Arrow), tippecanoe v2.80.0 em
  `~/tools/tippecanoe`, node 22.22, docker (3 contêineres OSRM `osrm/osrm-backend` MLD ativos para outras frentes,
  Keycloak 26 de outro projeto), playwright com chromium-1234, pdftoppm, weasyprint 69. AUSENTES: martin, tipg,
  pg_featureserv, pg_tileserv, nominatim, valhalla, pelias, qgis_process, k6, mapshaper, inkscape.
- Python: fastapi 0.138, psycopg2 2.9.9, shapely 2.1.2, geopandas 1.1.3, rasterio 1.5, pyproj 3.7.2, duckdb 1.5.5,
  pyarrow 24, h3 4.5, numpy 2.4, scipy 1.17, networkx 3.6, jsonschema 4.26, pystac 1.14, matplotlib 3.10, reportlab 4.5,
  PIL 12.2, cv2 5.0, xlsxwriter, openpyxl, pyparsing 3.3. AUSENTES: mapbox_vector_tile, lark, pyxform, pyodk, owslib,
  arcgis, rio_tiler/titiler (só na venv de `plataforma/pipeline`), ifcopenshell, trimesh, laspy, ezdxf, paho/aiomqtt,
  redis, procrastinate, sqlalchemy, fiona, exactextract.
- SIG de teste interno (`app/services.py`, 320 linhas): FeatureServer só-leitura com where por expressão regular,
  envelope, outStatistics/groupBy, distinct, count/ids/extent, paginação, orderBy, queryRelatedRecords, attachments
  (leitura), applyEdits de atributos em 2 camadas; OGC API Features Part 1 (landing, conformance, api, collections,
  items, item) próprios; CORS aberto em `/svc` e `/ogc`; token por hash (`sigcorp.auth_token`), RLS no banco;
  MapLibre 4.7.1 em vendor (o mesmo arquivo já copiado para `enterprise/web/vendor/`), xeokit AGPL para 3D.
- Repositório `plataforma/enterprise` 0.1.0: schema `plat`, role `plat_app` sem BYPASSRLS, contexto por GUC
  `plat.tenant_id` com `set_config(..., true)`, funções `SECURITY DEFINER` de autenticação, portas 8150-8153 reservadas
  (api, martin, titiler, worker), módulos ES sem bundler, `make check` com varredura de marcador, medidas em
  `tests/medidas/<item>.json`.
- Doc Esri (05/09): a operação `query` do FeatureServer lista 45 parâmetros nomeados (com `fullText` e `returnEnvelope`
  novos em 11.4, `uniqueIds`/`returnUniqueIdsOnly` em 11.5, `resultPaginationToken` em 12.1) e 4 formatos de saída
  (html, json, geojson, pbf). O GeoAnalytics Server foi aposentado na 11.4 (o último é o 11.3). Martin v1.15.0 saiu em
  02/09/2026 com pós-processamento de hillshade e curvas de nível.
- Da casa: bench de tiles com cache (DOC.md 13: 1.080 tiles/s por cliente, 45.178 tiles/s com 4 clientes, 20 pedidos
  ao mesmo tile frio = 1 MISS + 19 HIT); TiTiler 36-56 ms/tile; chromium headless com SwiftShader (L5-29: 350 ms para
  2.000 polígonos, captura 25 ms, PDF 17 ms); nginx de um site da casa com `location ~* \.pmtiles$ { gzip off; }` por
  causa de Range; `ais_positions` com 164,9 mi de linhas contadas; CNEFE já carregado em três frentes.

---

## C1. Documento de mapa, cena, painel e estilo: JSON próprio com esquema publicado, referências só por uuid

Opções: (a) adotar o Web Map JSON da Esri como formato interno; (b) documento próprio com esquema em
`docs/esquemas/*.json`, e tabelas de conversão de/para Web Map Spec; (c) sem documento (configuração em colunas).

Custo de mudar depois: alto. Todo construtor (L5), a impressão, a migração, a incorporação e a API lêem esse documento;
trocar o formato é migrar todo item do catálogo.

Recomendação: (b). Motivo: LIDO na Web Map Spec (05/09) que as camadas se referenciam por URL absoluta e por `itemId`
do Portal, e DOCUMENTADO no L0-03-a que a irritação nº 1 da migração Esri é exatamente essa; o nosso documento
referencia por uuid do catálogo e resolve URL em `GET /api/mapas/{id}/completo`. O envelope, a versão e o JSON Schema
são os do L5-05 (um tipo de documento por família). A conversão Web Map → nosso é o L2-08-c; nosso → Web Map é o
L2-08-d (para o cliente não ficar preso).

Obriga: L0-03-a a aceitar os tipos `mapa`, `cena`, `estilo`, `mapa_base`, `layout`, `painel`, `notebook`, `parquet`,
`selecao`, `anotacao` e a tabela `plat.item_versao` (L5-05); L0-03-i a registrar dependência mapa → camada; L5 a ler o
mesmo esquema.

## C2. Formato de estilo: MapLibre Style Spec pura + bloco `plat_construtor`

Opções: (a) SLD/SE como formato canônico e conversão para MapLibre no cliente; (b) JSON de renderer Esri; (c) DSL
própria; (d) MapLibre Style Spec (v8) pura, com bloco lateral `plat_construtor` {tipo, campo, método, cortes, rampa,
símbolo, rótulos} para o editor reabrir.

Custo de mudar: alto (renderizador do navegador, impressão headless, legenda, WMS, VectorTileServer e L5-27 lêem isso).

Recomendação: (d). Motivo: MEDIDO que o mesmo `maplibre-gl-4.7.1.js` já desenha no navegador e no chromium headless
(L5-29), e o Martin serve sprites e glifos; logo um único estilo é WYSIWYG em tela, impressão e miniatura. O L5-27
pediu exatamente este formato. SLD 1.0 e renderer Esri são SAÍDAS por conversão de subconjunto declarado (L2-02-a,
L2-04-b, L2-04-i): a spec Esri (`renderer-objects.htm`) tem 9 tipos de renderer; cobrimos simple/uniqueValue/classBreaks/
heatmap e declaramos dotDensity, pieChart, dictionary, predominance e vectorField como fora.

Obriga: L5-27/L5-28 a gravar sempre estilo válido na Style Spec (validador no `make check`); L1-02 a documentar os
parâmetros de URL do TiTiler que o estilo raster grava (rescale, colormap_name, expression); L2-12 e L2-04-i a
renderizar pelo mesmo arquivo.

## C3. Tiles vetoriais: Martin com uma função PostgreSQL por camada e contexto por token; PMTiles estático acima do limiar

Opções: (a) ST_AsMVT na própria API FastAPI; (b) pg_tileserv/Tegola; (c) Martin em modo "auto-publish tables";
(d) Martin em modo "funções" (uma função `tile(z,x,y,query_params)` por camada) + PMTiles gerado por tippecanoe para
camadas estáticas ou muito grandes.

Custo de mudar: médio (o contrato de URL `/tiles/{token}/{camada}/{z}/{x}/{y}` fica estável; troca-se o gerador).

Recomendação: (d). Motivo: (1) a RLS do repositório depende do GUC `plat.tenant_id` definido por `set_config` na
transação (ADR 0001 §3.3); o modo "tabelas" do Martin não executa código por pedido, o modo "funções" executa, e é onde
`plat.contexto_por_token(query_params->>'token')` entra (L2-04-a); (2) MEDIDO na casa que o gargalo é cache, não
geração (DOC.md 13); (3) Python gerando MVT por pedido consome worker da API; (4) PMTiles resolve o caso "1 mi de
feições, dado que muda pouco" com Range no nginx (regra já paga na casa: `gzip off` na location). O Martin não está
instalado: o item L2-01-b baixa o binário v1.15.0 das releases com sha256 conferido pelo `install.sh` (é download de
binário, pelo gerente, com `df` antes).

Obriga: L0-04-c a criar, na ingestão, a função de tile da camada (nome derivado de `c_<uuid16>`) e a coluna `fid`;
L1-02 a usar o mesmo formato de token no caminho; L7-01 a instalar o Martin como unidade `plat-martin` (8151).

## C4. Identificadores de feição: `fid` inteiro por camada + `globalid` uuid + `versao` inteira

Opções: (a) só `fid bigserial` (como o L0-04-c propõe); (b) `fid` + `globalid uuid` + `versao int`; (c) uuid como
chave primária única.

Custo de mudar: muito alto (toda edição, sincronização, histórico, FeatureServer e réplica dependem disso).

Recomendação: (b). Motivo: DOCUMENTADO na Esri que `OBJECTID` é `esriFieldTypeOID` inteiro e que sincronização e
`applyEdits` com `useGlobalIds` exigem `globalIdField` uuid; a concorrência otimista (a refutação do L2-03 exige que a
última edição nunca sobrescreva em silêncio) precisa de um número de versão por linha; o rastreio de mudanças da
réplica (L2-13-b) e a invalidação de cache (L2-01-b) usam `(fid, versao, momento)`. Restrição declarada: `fid` é
`bigint` no banco, mas a plataforma garante valores abaixo de 2^31 por camada (verificação na sequência) porque
clientes Esri anteriores à 11.3 só entendem OID de 32 bits; camada que passar disso é dividida, nunca exposta com OID
de 64 bits sem aviso.

Obriga: L0-04-c a acrescentar `globalid uuid DEFAULT gen_random_uuid() UNIQUE` e `versao int NOT NULL DEFAULT 1` (com
gatilho que incrementa) em toda tabela `c_*`; L5-31 (criar camada vazia) idem.

## C5. Uma porta de escrita e gatilhos no banco para o que tem de valer por qualquer caminho

Opções: (a) toda validação na API; (b) toda validação em gatilhos/constraints; (c) domínio, obrigatório, histórico e
versão por GATILHO no banco (valem para SQL direto, réplica, lote, importação) e regras de expressão na API (L2-03-a é a
única rota de escrita, chamada por navegador, FeatureServer, OGC Part 4, WFS-T, PWA e lote).

Custo de mudar: alto (reescrever caminhos de escrita e testes de concorrência).

Recomendação: (c). Motivo: LIDO no SIG de teste interno o padrão `fn_historico` (antes/depois em JSON por gatilho) que
sobreviveu a 3 OOM do Postgres; MEDIDO na casa que o pool psycopg2 devolve conexão morta e a API pode repetir a
preparação, mas nunca pode repetir uma escrita parcial — daí a transação única por lote. Regras de expressão ficam na
API porque a linguagem (C6) roda em Python e não há plpython3u instalado (e não se quer executar código de usuário
dentro do banco).

Obriga: L4-03 (edição de rede) e L5-03 (formulários) a escrever pelo L2-03-a; L0-10 a receber 1 evento por lote.

## C6. Linguagem de expressão própria, gramática EBNF fechada, AST em JSON, dupla implementação com vetores compartilhados

Opções: (a) adotar o Arcade (não há implementação aberta; é da Esri); (b) JavaScript avaliado no navegador
(`Function`) e Python `eval` no servidor (inseguro e não determinístico); (c) CQL2 como linguagem geral (só filtro,
sem cálculo); (d) linguagem própria pequena, analisador descendente recursivo escrito à mão em Python e em JavaScript
(L5-11), AST em JSON gravado junto com o texto, vetores de teste `tests/expressoes/*.json` como contrato, compilação
para expressão MapLibre (rótulos/estilo) e para SQL (filtros, cálculo em lote) em subconjuntos declarados.

Custo de mudar: muito alto (popups, rótulos, formulários, regras de atributo, painéis, alertas e a migração dependem).

Recomendação: (d). Motivo: DOCUMENTADO no Arcade (function reference e profiles, 05/09) o vocabulário que o usuário
Esri espera (perfis popup, labeling, calculation, constraint, validation, dashboard); a paridade é por FUNÇÃO
(feito/parcial/fora), não por sintaxe. O L5-11 já exigiu EBNF + vetores compartilhados. O `pyparsing` presente na
máquina não é usado no runtime porque o mesmo analisador precisa existir em JavaScript; gramática pequena escrita duas
vezes é mais barata do que um gerador em duas línguas. Limites: 10^5 passos, 50 ms no cliente e 500 ms no servidor,
sem rede, sem acesso a camada não permitida.

Obriga: L5-11 a consumir o AST (não só o texto); L5-03-b, L5-17, L5-26 a usar só funções da tabela; L2-08 a marcar
Arcade não traduzível como "fora" com o trecho.

## C7. Filtro canônico = CQL2-JSON; `where` Esri e FES 2.0 viram a mesma árvore

Opções: (a) `where` SQL-92 como formato interno (é o que a Esri grava); (b) CQL2-JSON como formato interno, com
tradutores `where` → árvore, CQL2-text → árvore, FES XML → árvore, e um único gerador de SQL parametrizado.

Custo de mudar: alto (vistas L5-07, seleções, painéis, OGC Part 3, réplicas gravam o filtro).

Recomendação: (b). Motivo: DOCUMENTADO (OGC 21-065r2) que CQL2-JSON é padrão aberto com operadores espaciais e
temporais; LIDO no SIG de teste interno que o `where` por expressão regular (`_where_seguro`) é frágil (recusa
funções e datas); um único gerador de SQL parametrizado é o ponto de auditoria de injeção. O L5-07 já serializa em
CQL2-JSON.

Obriga: L5-07/L5-32 a gravar CQL2-JSON; L6-02-c (cliente WFS) a reusar o mesmo parser FES.

## C8. Modelo de job: fila L0-05 com estados GP-compatíveis; síncrono só abaixo de um custo declarado; resultado é item com proveniência

Opções: (a) tudo síncrono na API com timeout; (b) tudo como job; (c) job por padrão, execução síncrona
(`/execute`) quando a estimativa de custo (contagem × complexidade declarada no manifesto) fica abaixo do teto; 1 job
pesado por vez (guardrail de RAM), estados mapeados para `esriJobSubmitted/Executing/Succeeded/Failed`.

Custo de mudar: médio (o manifesto e a proveniência são o contrato; o executor pode mudar).

Recomendação: (c). Motivo: guardrail medido (3 GB disponíveis; 20 sessões derrubaram o Postgres em 30/08); DOCUMENTADO
na Esri o contrato de GPServer (`submit-gp-job`) que Pro e apps JS esperam; LIDO no motor de LT o manifesto de
proveniência (commit + sha256) que a casa já exige para número em documento.

Obriga: L0-05 a expor sub-passos e cancelamento cooperativo (pedido do L5); L5-02 a chamar as mesmas funções de
ferramenta; L3-12/L3-13 a registrar resultado como item com o mesmo bloco de proveniência.

## C9. Contrato de API dos serviços externos: token no caminho, três raízes, código HTTP real com corpo no formato do cliente

Opções: (a) só `Authorization: Bearer`; (b) só token no caminho; (c) os dois — `/svc/{token}/rest/...` (Esri),
`/ogc/{token}/...` (OGC API, WFS, WMS, WMTS), `/tiles/{token}/...` (TileJSON/PMTiles) — porque AGOL/Portal não guardam
credencial de serviço externo (DOC.md 17.1) e o token precisa viajar na URL; erros com o código HTTP real (401/403/404/
422) E corpo no vocabulário do cliente (`{error:{code,message}}` para Esri, `application/problem+json` para OGC).

Custo de mudar: alto para clientes já configurados (URL gravada em web maps do cliente).

Recomendação: (c). Motivo: LIDO no SIG de teste interno (`/svc/{token}` e `/ogc/{token}`, CORS aberto nesses prefixos,
"AGOL e Pro já carregaram" no DOC.md 17.2); DOCUMENTADO que o Esri devolve HTTP 200 com erro no corpo — nós devolvemos
o código real e o corpo Esri, e o teste com o cliente Python `arcgis` (L2-04-j) prova que ele interpreta os dois.
Escopo e revogação são do L0-02-d; log de cada leitura é exigência da spec (17.4).

Obriga: L0-02-d a aceitar escopo por lista de itens e restrição de Referer/IP; L0-12 a admitir corpo de erro
alternativo nessas três raízes; L7-03 a aplicar rate limit por token.

## C10. Renderização no servidor: chromium headless com o MapLibre do vendor (WYSIWYG), num serviço próprio com pool e MemoryMax

Opções: (a) MapServer/QGIS Server/GeoServer para WMS e impressão (nenhum instalado; estilo teria de ser convertido para
SLD/QML — dupla verdade); (b) maplibre-native (binário, sem pacote pronto aqui); (c) chromium do playwright já
instalado, página mínima com o mesmo `maplibre-gl-4.7.1.js`, pool de páginas quentes em `plat-render` (8154).

Custo de mudar: médio (a entrada é documento de mapa + extensão + tamanho + DPI; a saída PNG/PDF; troca-se o motor).

Recomendação: (c). Motivo: MEDIDO no L5-29 nesta máquina (350 ms para 2.000 polígonos, captura 25 ms, PDF 17 ms,
WebGL por SwiftShader sem flag) e regra da casa: o google-chrome do sistema quebra, o chromium do playwright funciona.
A escala impressa é conferida com régua sobre o PDF (refutação do L2-12). Limite explícito: WMS/MapServer export por
este caminho serve dezenas de pedidos por segundo com cache nginx, não centenas; WMTS de vetor é pré-renderizado por job.

Obriga: L5-29 a usar o mesmo serviço (não um segundo chromium); L7-02 a incluir o render no teste de carga; decisão
D30 do dono (páginas quentes × RAM).

## C11. CRS: nativo preservado, exibição em 3857, entrega em qualquer EPSG, geodésico sempre, grades do IBGE

Opções: (a) converter tudo para 4326 na ingestão; (b) tudo em 3857; (c) SRID do arquivo preservado (L0-04-c), tiles
em 3857, serviços com `outSR`/`crs`/`srsName` por `ST_Transform`, medição e área geográficas, transformação de datum
SAD69/Córrego Alegre → SIRGAS 2000 pelas grades oficiais (ProGriD) instaladas com sha256.

Custo de mudar: alto (dado gravado).

Recomendação: (c). Motivo: regra da casa (comprimento geodésico; CRS explícito em toda comparação; terrain-RGB nunca
reamostrado); LIDO no SIG de teste interno (dado em 31982, serviços em 4326/3857/31982). Limite declarado: o MapLibre
não desenha em projeção que não seja Mercator; exibir em UTM fica FORA (o Map Viewer tem a mesma restrição por mapa
base).

Obriga: L0-04-c a nunca converter na ingestão; L3 a declarar CRS de trabalho por modelo (A7); L7-01 a instalar as
grades no diretório do PROJ.

## C12. Versionamento: histórico por feição para TODAS as camadas; ramos (branch) só para camadas marcadas

Opções: (a) tabelas temporais completas em toda camada (custo de escrita e disco); (b) nada além do histórico; (c)
histórico por gatilho em toda camada (L2-03-d) e modelo de ramo com colunas `versao_id/momento_inicio/momento_fim` só
nas camadas versionadas, com view por ramo, reconciliar/publicar e VersionManagementServer compatível.

Custo de mudar: alto para as camadas versionadas (colunas extras e views).

Recomendação: (c). Motivo: DOCUMENTADO nos cenários de branch versioning do Pro (05/09) que o ramo lê "linhas do ramo +
linhas do padrão anteriores ao momento base"; reproduzir isso exige colunas de momento, que seriam custo morto em
camadas que nunca ramificam. O histórico por gatilho já dá `historicMoment` e restauração.

Obriga: L4-03 (edição de rede) a decidir se a rede é versionada (recomendado: sim); L2-07/L2-13-b a usar
`(fid, versao, momento)` como rastreio.

## C13. Offline e sincronização: um mecanismo de réplica (GeoPackage + rastreio de mudanças + idempotência) para PWA, clientes Esri e QField

Opções: (a) mecanismo próprio para a PWA e outro para `createReplica`; (b) adotar QFieldCloud ou ODK Central como o
mecanismo; (c) réplica própria em `plat.replica` com GeoPackage gerado por ogr2ogr, mudanças por `(fid, versao,
momento)`, ids de idempotência do dispositivo, políticas de conflito; o `createReplica/synchronizeReplica` Esri
(L2-04-k) e a fila da PWA (L2-07-c) são fachadas sobre ele; QField lê o mesmo GeoPackage.

Custo de mudar: muito alto (dado em campo não sincronizado é perda).

Recomendação: (c). Motivo: a refutação do L2-07 ("sem rede, relógio errado, sincroniza duas vezes: sem duplicata e sem
perda") exige idempotência no servidor, que nenhum dos dois produtos externos dá sobre a NOSSA tabela com RLS;
DOCUMENTADO que o Esri sync usa gerações por camada e GeoPackage/SQLite como transporte. A spec 17.2 citava QFieldCloud
+ ODK; o estado do laço pede PWA própria: decisão D35 registrada.

Obriga: L5-34 (captura rápida) a usar a mesma fila; L0-04-a a oferecer upload retomável para anexos da sincronização.

## C14. Tempo real: processo próprio, partição nativa + BRIN, SSE por `pg_notify`, sem TSL em dado do inquilino

Opções: (a) TimescaleDB (hypertable, compressão, agregados contínuos); (b) tabela simples; (c) `plat-fluxo` (8155)
escrevendo em lote (COPY, 1/s) em tabela particionada nativamente por mês com BRIN em tempo e GIST em geometria,
agregados por job, expurgo por partição; `pg_notify` → SSE (`/api/eventos`) para mapa e painel.

Custo de mudar: alto (dado histórico e regras).

Recomendação: (c). Motivo: DOC.md 22 e a licença TSL (URL testada): compressão e agregados contínuos são TSL, que
proíbe database-as-a-service; o dado do cliente não pode depender disso (D33 para confirmar). MEDIDO que a casa tem
`ais_positions` com 164,9 mi de linhas em PostGIS: partição nativa basta na escala prevista; acima disso o histórico
frio vai para Parquet (C15). SSE em vez de WebSocket para dado de mapa/painel porque passa por nginx e proxies sem
configuração extra; WebSocket fica para o StreamServer compatível.

Obriga: L7-06 a monitorar atraso e perda do fluxo; L7-08-a a entregar webhooks assinados; L5-19 a usar `/api/eventos`.

## C15. Analítica grande: DuckDB sobre GeoParquet no Garage; PostGIS continua sendo a verdade

Opções: (a) Spark/Sedona (JVM, RAM); (b) tudo em PostGIS; (c) exportar para GeoParquet 1.1 (via DuckDB, porque o GDAL
3.8.4 não tem driver Parquet — medido) e consultar com DuckDB spatial num worker com `memory_limit`, 1 consulta grande
por vez; resultado materializado como camada/tabela/Parquet; área e comprimento geodésicos calculados na materialização
pelo PostGIS ou por projeção declarada (o DuckDB spatial é planar).

Custo de mudar: baixo-médio (Parquet é formato aberto; o motor pode trocar).

Recomendação: (c). Motivo: MEDIDO na casa (DOC.md 22: 1,31 bi de linhas em 5,2 GB; Overture 596 mil edifícios em 87 s
com DuckDB) e 3 GB de RAM disponíveis (Sedona/Spark não cabem). O GeoAnalytics Server foi aposentado na 11.4: a
paridade é contra as ferramentas big data da 11.3 e o que sobrou no Map Viewer 11.4.

Obriga: L6-02-f (GeoParquet por URL) e L6-01-i a usar o mesmo leitor; L7-09 a medir bytes lidos do bucket por
inquilino.

## C16. Geocodificação e rota: geocodificador próprio em PostgreSQL sobre CNEFE; OSRM em contêiner + pgRouting; isócrona por matriz

Opções: (a) Nominatim/Pelias (OSM completo em disco, serviços Java/Node/Elasticsearch); (b) geocodificador próprio
sobre dado aberto brasileiro já na casa (CNEFE 2022 por face de quadra, localidades, municípios; `pg_trgm` + `unaccent`
instalados; `address_standardizer` disponível); (c) rota: OSRM em contêiner (padrão já usado na casa) + pgRouting 4.0.1
do apt para rede própria; isócrona por matriz OSRM sobre grade + casco côncavo, ou `pgr_drivingDistance`.

Custo de mudar: médio (API própria e Esri-compatível são estáveis; o motor por trás pode trocar).

Recomendação: (b) + (c). Motivo: disco a 98 % (D28) e ausência dos binários; CNEFE já usado em três frentes; OSRM
medido (três contêineres MLD ativos); o OSRM não tem serviço de isócrona (doc testada lista route/table/nearest/
match/trip/tile). A qualidade é medida contra o próprio CNEFE (refutação do L2-11: 50 endereços, erro mediano).

Obriga: L3-11 (fator de rede) e L2-05-f a chamar a mesma API; L4 a fornecer a rede para o pgRouting.

## C17. 3D: MapLibre (terrain-RGB próprio, extrusão) + three.js para glTF + deck.gl para OGC 3D Tiles; nada de AGPL; i3s fora

Opções: (a) CesiumJS (Apache-2.0, motor separado, dois visualizadores); (b) xeokit (AGPL, presente no SIG de teste,
vetado pelo DOC.md 22); (c) MapLibre com terreno e extrusão + camadas personalizadas (three.js MIT para glTF posicionado,
deck.gl MIT `Tile3DLayer` para 3D Tiles), IFC convertido para glTF/3D Tiles por job (IfcOpenShell no GPU box, D32).

Custo de mudar: médio (documento de cena é nosso; o motor pode trocar).

Recomendação: (c). Motivo: um só visualizador e um só estilo (C2); DOCUMENTADO que o Pro consome 3D Tiles por URL
(DOC.md 22) e que 3D Tiles é Community Standard OGC (18-053r2, URL testada); i3s tem spec aberta mas nenhum produtor
aberto na pilha → declarado fora. Codificador terrain-RGB próprio em numpy porque a armadilha do degrau de 128 m já
custou na casa.

Obriga: L1-01 a aceitar MDT do inquilino como COG; L5-01-b (perfil de elevação) a usar `L2-09-a`.

## C18. Isolamento por inquilino nos serviços: schema `d_<slug>` + RLS + role só-leitura `plat_leitor` + contexto por token; sem SQL de cliente fora do tradutor

Opções: (a) um banco por inquilino; (b) um schema por inquilino com RLS e GUC (o do ADR 0001); (c) (b) + role
`plat_leitor` separada para Martin/leitores externos + `contexto_por_token` SECURITY DEFINER que grava o uso.

Custo de mudar: muito alto.

Recomendação: (c). Motivo: LIDO no ADR 0001 §3.3 que o contexto é um GUC que a própria role define, portanto "uma rota
que aceitasse SQL do cliente trocaria de inquilino sem passar pela RLS" — por isso toda entrada de usuário (where, CQL2,
FES, expressão, SQL da camada de consulta) passa por tradutor com lista fechada e a camada de consulta (L2-18) só cria
VIEW após `EXPLAIN` em transação abortada com verificação das relações citadas. A varredura cruzada do L0-02-e é
estendida às funções de tile e a todas as rotas `/svc`, `/ogc` e `/tiles`.

Obriga: L0-02-e a incluir as três raízes na varredura; L6-01-b a expor o acervo por VIEW no mesmo padrão.

## C19. Extensibilidade: registros em código com manifesto + JSON Schema e vocabulários fechados; código de usuário só dentro de contêiner

Opções: (a) plugins carregados dinamicamente na API; (b) registros declarativos (ferramentas, widgets, tipos de fonte
de fluxo, tipos de conexão, tipos de item) com manifesto validado no `make check`; código de usuário (scripts, notebooks)
só no contêiner isolado do L2-16-b com token do usuário.

Custo de mudar: médio.

Recomendação: (b). Motivo: guardrail "sem placeholder" e P6: um manifesto sem teste é erro de build; DOCUMENTADO que a
Python toolbox da Esri é exatamente um cabeçalho declarativo + código, e o Notebook Server roda em contêineres docker
isolados. RAM medida (3 GB) → 1 contêiner ativo por vez e fila.

Obriga: L0-05 a ganhar o executor em contêiner (L0-05-e proposto); L5-36 (SDK de widget) a usar o mesmo registro.

## C20. Paridade: matriz gerada por script, "feito" só com teste, Pro/AGOL pendentes até D20

Opções: (a) tabela escrita à mão; (b) `tests/paridade/l2.json` + `tests/esri/conformidade.json` gerados por script,
cruzados com `tests/medidas` e e2e; QGIS em contêiner docker como cliente de teste (D36); Pro/AGOL reais só com o
parceiro (D20), registrados como PENDENTE.

Custo de mudar: baixo, mas o custo de NÃO fazer é vender o que não existe.

Recomendação: (b). Motivo: guardrail P4 e a regra da casa "número em documento sai de JSON gerado por script".

---

## O que estas decisões obrigam nas outras linhas (resumo)

- L0-03-a: tipos de item novos (mapa, cena, estilo, mapa_base, layout, painel, notebook, parquet, selecao, anotacao);
  L0-03-i: dependência mapa → camada → estilo; L5-05: `plat.item_versao` para todos.
- L0-04-c: colunas `globalid uuid` e `versao int` + gatilho; função de tile por camada; SRID nativo preservado;
  L0-04-h: exportação chamada pelo mapa (L2-01-l) com filtro/seleção.
- L0-02-d: escopo por lista de itens e restrição Referer/IP; L0-02-e: varredura cruzada em `/svc`, `/ogc`, `/tiles` e
  nas funções de tile; L0-12: corpo de erro alternativo nas três raízes.
- L0-05: sub-passos, cancelamento cooperativo, executor em contêiner (L0-05-e proposto).
- L1-02: vocabulário de parâmetros do TiTiler documentado (estilo raster grava); L1-04: controle de tempo como módulo ES
  reutilizável; L1-01: MDT do inquilino como COG.
- L3-11/L3-12/L3-13: mesma API de rota, mesmo manifesto de ferramenta, mesmo bloco de proveniência.
- L4-03: escrita pelo L2-03-a; rede versionada; rede como grafo do pgRouting.
- L5-07/L5-32: CQL2-JSON; L5-11: AST + vetores; L5-27: Style Spec + `plat_construtor`; L5-26: motor de popup do
  L2-01-d; L5-29: `plat-render`; L5-34: fila do L2-07-c; L5-36: registro de widgets.
- L6-02-a: tipos de conexão `portal_esri`, `odk_central`, `mqtt`, `http_sondagem`; L6-02-c: parser FES compartilhado;
  L6-01-b: acervo por VIEW no padrão de isolamento.
- L7-01: unidades `plat-martin` (8151), `plat-render` (8154), `plat-fluxo` (8155), pgRouting do apt, grades do PROJ;
  L7-02: carga em tiles + render + fluxo; L7-03: rate limit por token e antivírus em anexos (L7-03-b proposto);
  L7-06: métricas de fluxo; L7-08-a: webhooks assinados.

## Decisões que ficam com o dono (para `decisoes_do_dono`)

D27 mapa base (volume × disco 98 %) · D28 CNEFE e .pbf por UF (volume) · D29 ODK Central self-host · D30 pool de
renderização × RAM · D31 broker MQTT próprio · D32 IFC → glTF no GPU box ou aqui · D33 TSL do TimescaleDB confirmada
como não usada em dado do inquilino · D34 SQL livre do usuário aceito no produto · D35 PWA própria × QFieldCloud/ODK
como caminho principal do campo · D36 QGIS em docker para conformidade. D20 (credencial Pro/AGOL do parceiro) continua
aberta e trava só a coluna "Pro/AGOL real" da paridade, nunca a construção.
