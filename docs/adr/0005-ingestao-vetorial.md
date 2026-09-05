# ADR 0005 — Ingestão vetorial (item L0-04-ingest-vetor e filhos L0-04-a … L0-04-j)

Estado: **proposto** (T2, trilha de preparação; arquiteto+dados). O arquivo foi gravado por partes; a seção 20
fecha o ADR. Data: 2026-09-05.

Contexto herdado, sem repetir: ADR 0001 (schema `plat`, role `plat_app`, RLS `FOR ALL USING/WITH CHECK`, pool psycopg2
com preparação repetível, migrações `NNN_*.sql` imutáveis, `/saude`); ADR 0002 (privilégios `conteudo.criar`,
`conteudo.publicar_camada`, `feicoes.editar`, escopos `camada:ler[:uuid]`, `pode_ler/pode_editar`); ADR 0003 (fila
própria, `@tarefa`, `ContextoJob` com `progresso/log/entrada/subprocesso`, `RLIMIT_DATA` por filho, proveniência do
job); ADR 0004 (tabela `plat.item`, `tipo_item` com JSON Schema, `relacao_tipo`, `pode_ler`, contrato esperado do
L0-11 em 11.3, tipos `camada_vetorial`/`arquivo`/`vista_de_camada`/`conexao`); `L0_CONCEITO.md` D3, D4, D11, D13,
D16, D17; `L2_CONCEITO.md` C3, C4, C5, C11, C12; `L4_CONCEITO.md` C1, C10.

Regra de leitura: tudo o que está marcado **MEDIDO** foi executado nesta máquina em 05/09/2026 com o comando
indicado (Anexo A); o que está marcado **LIDO** vem de código que roda na casa (só leitura); o que está marcado
**DOC** vem da documentação do GDAL 3.8.4 instalado (`ogrinfo --format <driver>`, seção 0). Nenhum número deste ADR
foi digitado de cabeça.

---

## 0. O que foi medido antes de decidir (05/09/2026, 15:05–15:25 UTC)

Ambiente: GDAL 3.8.4 (`ogrinfo --version`), PostGIS 3.6.3 / GEOS 3.12.1 / PROJ 9.4.0 (`postgis_full_version()`),
PostgreSQL 16, 12 vCPU, RAM disponível 2–3 GB, disco 98 %. Dado de teste: **aberto**, gerado por script a partir de
tabelas do `iagro_sat` (malha municipal do IBGE de uma UF simplificada a 0,0005°, ferrovias do DNIT e heliportos do
DECEA no mesmo recorte) e 100 mil hexágonos sintéticos por `generate_series`; nada baixado, 7,1 MB no total, apagado
no fim. Schema temporário `adr0005_tmp` criado com `AUTHORIZATION plat_app` e apagado no fim.

### 0.1 Drivers e bibliotecas (o que existe de verdade sob a regra `PYTHONNOUSERSITE=1` da venv)

| o quê | resultado | consequência |
|---|---|---|
| `ogrinfo --formats` | ESRI Shapefile, GPKG, GeoJSON, GeoJSONSeq, ESRIJSON, TopoJSON, LIBKML, KML, CSV, GPX, XLSX, DXF, CAD (só leitura), OpenFileGDB, FlatGeobuf, GML, GMLAS, MapInfo File, SQLite, PostgreSQL, PGDUMP, MVT, PMTiles, OSM, WFS, OAPIF, GPSBabel; **`grep -ci parquet` = 0** | Parquet/Arrow fica fora do GDAL desta máquina |
| venv com `PYTHONNOUSERSITE=1` | presentes: `osgeo` 3.8.4, `shapely` 2.1.2, `pyproj` 3.7.2, `numpy` 2.4.6, `rasterio` 1.5.0, `openpyxl` 3.1.5, `chardet` 5.2.0, `charset_normalizer` 3.4.7, `magic`; **ausentes: `duckdb`, `pyogrio`, `lxml`, `ezdxf`, `python-multipart`** (os quatro primeiros existem só em `~/.local`, que a regra proíbe; o `L0_CONCEITO.md` listou `lxml` como presente por ter olhado sem a regra) | GeoParquet e DuckDB **não** entram nesta fase (seção 10.3); upload em partes não usa `multipart/form-data` (seção 3); XLSX lê-se pelo driver do GDAL; DXF pelo driver do GDAL |
| `dwg2dxf`/`dxf2dwg`/`dwgread` | ausentes aqui; no GPU box `/usr/local/bin/dwg2dxf 0.14.8583` (LibreDWG). Driver `CAD` do GDAL (libopencad 0.3.4): recusa DWG R2000 gerado pelo LibreDWG e o R2018 ("does not support this version") | DWG só por conversão externa (seção 12) |
| `/usr/bin/time`, `prlimit`, `zip/unzip/7z`, `file` | presentes | medições de RSS e testes de limite |

### 0.2 Inspeção (`ogrinfo -ro -json -so`) por formato — tempo, o que detecta, o que NÃO detecta

| arquivo (gerado) | ms | detecta | não detecta / erro |
|---|---|---|---|
| GPKG 3 camadas | 46 | 3 camadas, `MultiLineStringZ` 4674, `MultiPoint` 4674, campos tipados (`Date`) | camada de GeoJSON gravada como `Geometry` (tipo desconhecido) |
| Shapefile zipado (`/vsizip/`) | 49 | `Polygon` EPSG:4326, campos truncados a 10 bytes (`Código IB`, `Município`) | — |
| Shapefile **sem .prj** | 37 | tudo menos o CRS: `srs = AUSENTE` | CRS: tem de ser perguntado |
| Shapefile latin-1 **sem .cpg** | 49 | com `-oo ENCODING=ISO-8859-1` os nomes saem certos; sem a opção, `C�digo IBG`, `Munic�pio` (bytes inválidos em UTF-8; o JSON vem com U+FFFD) | codificação: tem de ser perguntada quando não há `.cpg` |
| zip com 2 shapefiles | 54 | 2 camadas | — |
| KML/KMZ com 3 pastas (LIBKML) | 64/66 | 3 camadas, sempre 4326, tipo `Geometry`, 9 campos fixos do KML antes dos do usuário | tipo real da geometria só por varredura |
| GML 3.2 gerado com campo `Área km²` | 44 | — | **XML mal formado na linha 17** (`<ogr:Área_km²>`): o próprio escritor GML do GDAL produz elemento inválido com nome não ASCII; exportação para GML usa só nomes normalizados (seção 8) |
| FlatGeobuf | 44 | `MultiLineStringZ` 4674 | — |
| GeoJSONSeq | 49 | `MultiPoint` 4326 | — |
| XLSX 2 planilhas | 37 | 2 camadas sem geometria; `latitude/longitude` como `Real`, `efetivacao` como `Date` | não aceita `-oo AUTODETECT_TYPE` (aviso) |
| GPX | 41 | 5 camadas fixas (`waypoints, routes, tracks, route_points, track_points`) | — |
| MapInfo TAB zipado | 72 | `Geometry`, **CRS como WKT sem código** (`unnamed`), nomes de campo em latin-1 corrompidos | CRS por WKT tem de virar pergunta com sugestão (seção 9) |
| GeoJSON com `crs` legado 31984 | 56 | EPSG:31984 reconhecido; carga preserva 31984 | RFC 7946 ignorado quando há `crs`: avisar |
| GeoJSON misto ponto+polígono | 42 | tipo `Geometry` | tipo real só por varredura |
| GeoJSON gravata (auto-intersecção) + anel não fechado | 42 | 3 feições `Polygon`; **aviso** `Non closed ring detected` | validade só no banco (0.4) |
| CSV `;` + vírgula decimal + BOM, **sem opções** | 37 | 8 campos, todos `String`, sem geometria | — |
| CSV `;` + vírgula decimal com `AUTODETECT_TYPE=YES`, `X_POSSIBLE_NAMES=long`, `Y_POSSIBLE_NAMES=lat` | 35 | `lat/long` como `Real` (o driver aceita vírgula decimal quando o separador é `;`), `Elevação (m)` `Real`, `Data` (`2024/02/08`) `Date`, geometria `Point`, `srs = AUSENTE` | `1.234,5` (milhar) fica `String`; `08/02/2024` fica `String`; `"12,5"` com separador `,` fica `String` (MEDIDO em `milhar_pv.csv`/`milhar_v.csv`) |
| CSV com coluna `WKT` | 36 | `Geometry` via `GEOM_POSSIBLE_NAMES=WKT` | CRS ausente |
| `.txt` com tabulação | — | **`not recognized as a supported file format`** | extensão `.txt` não abre: renomear para `.csv` no diretório de trabalho |
| CSV 300 colunas 0 linhas | 38 | 300 campos `String`, `n = 0` | — |
| CSV aspas desbalanceadas | 36 | 1 feição (a 2ª linha foi engolida pela aspa aberta) | silêncio do GDAL: a inspeção conta linhas por `csv` Python e compara (seção 11) |
| CSV campo duplicado `Município,Município` | 36 | devolve os dois com o mesmo nome; na carga o GDAL renomeia para `município2` com **aviso** | mapa de nomes tem de desduplicar (seção 8) |
| DXF (linhas do DNIT via escritor DXF) | 36 | 1 camada `entities`, 107 feições, campos `Layer, PaperSpace, SubClasses, Linetype, EntityHandle, Text`, `srs = AUSENTE` | CRS e unidade sempre perguntados |
| DXF com bloco `ARVORE` × 3 INSERT + LWPOLYLINE + LINE + TEXT (padrão `DXF_INLINE_BLOCKS=TRUE`) | 36 | 6 feições: os 3 INSERT viram `MultiLineString` (bloco explodido), 2 `LineString`, 1 `Point` (texto) | nome do bloco perdido |
| idem com `--config DXF_INLINE_BLOCKS FALSE` | 33 | 2 camadas: `blocks` (1 = a definição) e `entities` (6): os INSERT viram **`Point` com `BlockName=ARVORE`, `BlockScale`, `BlockAngle`** | é o modo que preserva o atributo do bloco (seção 12) |
| idem com `DXF_MERGE_BLOCK_GEOMETRIES=FALSE` | 36 | 9 feições (círculo e linha de cada bloco separados) | — |
| DXF binário (assinatura `AutoCAD Binary DXF`) | — | **`not recognized`** | recusa com mensagem própria (seção 12) |
| DXF com `$INSUNITS=1` (polegada) | 32 | igual ao de metros: o driver não expõe a unidade | unidade lida por nós no cabeçalho (seção 12) |
| GPKG com nome de camada com `\x01` | 46 | nome devolvido com o byte de controle | nome de camada é normalizado (seção 8) |
| 100 mil feições: GPKG (37 MB) / shapefile zipado (14 MB) | 40 / 50 | metadado sem varrer | contagem do shapefile vem do `.shx` (exata); do GPKG, de `gpkg_ogr_contents` |
| tipo real por varredura: `-dialect SQLITE -sql "SELECT ST_GeometryType(geom), COUNT(*) … GROUP BY 1"` (GPKG) / `-dialect OGRSQL -sql "SELECT DISTINCT OGR_GEOMETRY"` (shapefile) em 100 mil | 120 / 230 ms | `MULTIPOLYGON 100000` | — |

### 0.3 Carga (`ogr2ogr -f PostgreSQL` como `plat_app`, `PG_USE_COPY=YES`, `-nlt PROMOTE_TO_MULTI`, `-lco GEOMETRY_NAME=geom -lco FID=fid -lco SPATIAL_INDEX=NONE -lco PRECISION=NO`)

| arquivo | tempo | RSS | resultado e o que se aprende |
|---|---|---|---|
| GPKG municípios (75) | 2,89 s | 58 MB | coluna `geom geometry(Geometry,4326)`: **`PROMOTE_TO_MULTI` não tipa a coluna quando a camada de origem é `Geometry`**; com `-nlt MULTIPOLYGON` explícito sai `geometry(MultiPolygon,4326)` (MEDIDO, `gj_tipado`). Logo o tipo vem da varredura da inspeção e vai explícito no `-nlt` |
| Shapefile sem .prj | 0,47 s | 51 MB | `geometry(MultiPolygon)` **SRID 0** — o GDAL carrega em silêncio; por isso a carga só roda depois da confirmação do CRS (`-a_srs EPSG:NNNN`, 2,54 s → SRID 4674) |
| Shapefile latin-1 sem .cpg + `-oo ENCODING=ISO-8859-1` | 1,42 s | 57 MB | nome `Aracaju` e coluna `município` corretos |
| GeoJSON com `crs` 31984 | 0,89 s | 56 MB | `geometry(Geometry,31984)`, ponto em `681399 8827851` (metros): SRID nativo preservado (C11) |
| GeoJSON gravata | 0,59 s | 56 MB | as 3 feições entram; `ST_IsValid` = f só na gravata (`Self-intersection[-37.05 -10.85]`); `ST_MakeValid` devolve `MultiPolygon` com 2 partes e área 0,005 (soma dos dois triângulos); o anel não fechado é fechado pelo GDAL e fica válido |
| CSV `;` vírgula decimal | 0,46 s | 55 MB | `lat/long double precision`, `data date`, `geom geometry(MultiPoint,4674)` com `-a_srs` |
| XLSX | 1,16 s | 52 MB | `latitude/longitude double precision`, `efetivacao date` |
| DXF blocos com `-a_srs EPSG:31984` | 0,71 s | 56 MB | `geometry(Geometry,31984)`; campos do driver em minúsculo |
| MapInfo TAB latin-1 | falha | — | `invalid byte sequence for encoding "UTF8": 0xc3 0x5f` **no nome do campo**, mesmo com `-oo ENCODING`: nome de campo também passa pelo decodificador nosso (seção 8) |
| GML gerado | falha | — | XML mal formado (0.2) |
| CSV duplicado | 0,70 s | 50 MB | `município`, `município2` — o GDAL desduplica com aviso; o mapa nosso faz igual e **declara** |
| `LAUNDER=YES` (padrão) | — | — | `Código IBGE` → `código ibge`, `Área km²` → `Área km²`, `select` → `select`: **só baixa caixa ASCII, mantém acento, espaço, `²` e palavra reservada**. A normalização de nomes é nossa (seção 8) e vai no `-sql … AS …` da própria carga (MEDIDO: 100 mil feições com 8 aliases + `COLUMN_TYPES=classe_=smallint` em 1,25 s) |
| `-lco FID64=YES` | — | — | `fid bigint` com sequência `…_fid_seq` (C4: bigint no banco; teto 2^31 pela sequência, seção 7) |
| **100 mil feições, GPKG → PG** | **2,57 s** | 58 MB | |
| 100 mil, shapefile zipado → PG | 1,11 s | 61 MB | |
| 100 mil, GeoJSONSeq (55 MB) → PG | 2,57 s | 56 MB | streaming: memória plana |
| pós-carga (SQL como `plat_app`): `ST_IsValid` em 100 mil 0,19 s · `UPDATE … ST_MakeValid(ST_ReducePrecision)` 1,63 s · `ADD COLUMN globalid/versao/tenant_id/criado…` 2,32 s · `UNIQUE(globalid)` 0,34 s · `CREATE INDEX … gist` 0,75 s · `ANALYZE` 0,26 s · estatísticas (`count, ST_Extent, distintos, min/max`) 0,07 s | **5,6 s** | | **portão "≤ 60 s para 100 mil" fecha com folga de 10×: carga + pós-carga ≈ 8,2 s** (tabela final 45 MB) |

### 0.4 Memória: onde o GDAL quebra (é o que define o `memoria_mb` do job e a recusa por tamanho)

Armadilha reencontrada (já paga no ADR 0003 4.3): sob `RLIMIT_DATA` **sem** `OPENBLAS_NUM_THREADS=1`, `ogrinfo` e
`ogr2ogr` **travam na partida** (RSS ≈ 40 MB, nunca terminam; 9 execuções com `timeout` 45–90 s, rc 124, inclusive
sobre GPKG de 37 MB que sem limite carrega em 2,6 s) — as 12 threads do OpenBLAS ligado ao GDAL reservam endereço e o
`pthread_create` falha em laço. O filho do worker já exporta a variável; a tabela abaixo é com ela exportada.

| caso (todos com `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`) | RLIMIT_DATA | tempo | RSS | resultado |
|---|---|---|---|---|
| `ogrinfo -so` GeoJSON de **100 mil feições, 55 MB** | 256 MB | 1,19 s | 54 MB | rc 0 — o driver lê a `FeatureCollection` em fluxo |
| idem | 512 / 1024 MB | 1,18 / 1,21 s | 54 MB | rc 0 |
| `ogrinfo -so` GeoJSONSeq 55 MB | 256 MB | 1,63 s | 49 MB | rc 0 |
| `ogrinfo -so` GPKG 37 MB | 256 MB | 0,04 s | 52 MB | rc 0 |
| `ogr2ogr` GeoJSON 55 MB → PG | 512 / 1024 MB | 2,57 / 2,59 s | 60 MB | rc 0 |
| `ogr2ogr` GeoJSONSeq → PG | 256 MB | 2,60 s | 56 MB | rc 0 |
| `ogr2ogr` GPKG → PG / shapefile zipado → PG | 256 MB | 1,20 / 2,42 s | 58 / 60 MB | rc 0 |
| `ogrinfo -so` GeoJSON de **1 feição com 2 milhões de vértices (51 MB)** | 512 MB | 0,77 s | **555 MB** | **sinal 6** (`*** %n in writable segment detected ***`: falha de alocação na formatação do erro do GDAL) |
| idem | 1024 MB e sem limite | 0,95 s | 644 MB | rc 1 (`unable to open`: o driver recusa objeto acima de `OGR_GEOJSON_MAX_OBJ_SIZE`, 200 MB em memória) |
| GeoJSON de **1 feição com 10 milhões de vértices (255 MB)**, sem limite | — | 0,92 s | 645 MB | rc 1, mesma recusa |

Decisão que sai daqui (4.3): o tamanho do **arquivo** GeoJSON não é o problema (55 MB em fluxo com 54 MB de RSS); o
problema é **uma feição** grande, que o driver monta inteira em memória com cerca de 11× o tamanho em texto (51 MB →
555 MB). A inspeção faz uma pré-sonda de bytes (Python, em fluxo, sem `json`) que mede a maior feição
(distância entre marcadores `{"type": "Feature"` / linhas do GeoJSONSeq) e recusa acima de `FEICAO_BYTES_MAX`
(16 MiB, que a 11× cabe em `memoria_mb=768` com folga) com a mensagem exata da seção 4.3. Para KML/KMZ (LIBKML monta
DOM — DOC do driver) o mesmo teto vale para o **arquivo** descompactado (`KML_BYTES_MAX` = 64 MiB), **declarado e
não medido aqui**: o L0-04-d mede antes de ligar. GML e GeoJSONSeq leem por feição (DOC dos drivers) e não têm teto
além do da feição. A conversão GeoJSON → GeoJSONSeq como passo prévio não entra: custa 3,55 s e a mesma memória.

### 0.5 Tipo por conteúdo (`python3-magic`, para o L0-04-a conferir tipo declarado × bytes)

`magic` reconhece: DXF ASCII (`image/vnd.dxf` + versão), GPKG (`application/vnd.sqlite3`, "OGC GeoPackage file"),
XLSX, GeoJSON (`application/json`), GeoJSONSeq (`application/x-ndjson`), KML/GML/GPX (`text/xml`), CSV (`text/csv` ou
`text/plain`), zip (`application/zip`), DBF, `.shp` ("ESRI Shapefile version 1000 length … type Polygon"), DWG ("DWG
AutoDesk AutoCAD 2000/2018"). **Não** reconhece FlatGeobuf (`application/octet-stream`, "data"): o FGB tem assinatura
própria (`66 67 62` nos 3 primeiros bytes, DOC do formato) que a nossa conferência lê. Zip: `zipfile` do Python dá
entradas e razão total/comprimido em 1 chamada (medido: 5 entradas e razão 1,5 no shapefile; 6,5 no KMZ).

### 0.6 DWG (GPU box, LibreDWG 0.14.8583)

`dxf2dwg --as r2000` e `--as r2018` sobre o `blocos.dxf` gerado: rc 0, 0,00 s, 5 MB de RSS, arquivos de 1,2 KB (R2000)
e 302 KB (R2018), reconhecidos pelo `file` como "DWG AutoDesk AutoCAD 2000/2018". `dwg2dxf` de volta: rc 0, mas o DXF
resultante **perdeu as entidades** (0 INSERT/LWPOLYLINE/LINE/TEXT depois de `ENTITIES`) e **não abre nem no GDAL**
(`error at line 991`) **nem no `ezdxf` 1.x da venv do SIG de teste interno** (`missing ENDSEC tag`). O DXF de entrada
era mínimo (sem subclasse `AcDbPolyline`, que o `ezdxf` também recusa; o GDAL o aceita). Conclusão para o L0-04-e:
a conversão por LibreDWG **não está provada**; o portão daquele item exige medir com DWG reais do corpus da casa (654
IFC/DWG/DXF) antes de prometer, e a decisão D23 (ODA) continua aberta. O driver `CAD` do GDAL está descartado (0.1).

---

## 1. Resumo das decisões (uma linha cada; o detalhe está na seção indicada)

1. **Cinco estados, dois jobs, uma confirmação humana no meio.** `arquivo enviado` → job `ingestao.inspecionar`
   → `proposta` (JSON editável) → confirmação do usuário → job `ingestao.carregar` → `camada` no catálogo. Nada cria
   tabela antes da confirmação (D11); tudo o que dura > 1 s é job da fila do ADR 0003 (seção 2).
2. **Upload retomável em partes de 16 MiB pela nossa API** (não `multipart/form-data`, ausente na venv; corpo bruto
   `application/octet-stream` por parte), gravado em objeto do Garage por *multipart upload* S3 pelo contrato do L0-11,
   sha256 no servidor, cota reservada antes do 1º byte e conferida no fim, tipo declarado × bytes (seção 3).
3. **Inspeção = `ogrinfo -json` + varredura de tipo de geometria + sondas nossas** (codificação, separador, vírgula
   decimal, milhar, datas dd/mm, duplicatas, validade em amostra, unidade do DXF, WKT sem código), com limite de
   memória e recusas por tamanho medidas (seção 4).
4. **Nunca assumir**: CRS ausente ou WKT sem código, codificação sem `.cpg`, colunas de coordenada ambíguas, unidade
   de DXF, fuso de datas — tudo vira campo `perguntar` na proposta, com sugestão (seção 5; D4).
5. **Carga = `ogr2ogr` como neto do job com `RLIMIT_DATA`**, `-sql … AS <nome normalizado>`, `-nlt <tipo varrido>`,
   `-a_srs`/`-s_srs` confirmados, `COPY`, sem índice; depois, na mesma transação SQL, `ST_MakeValid` com relatório,
   colunas obrigatórias, gatilhos, RLS, GIST, `ANALYZE`, estatísticas, item, relações, função de tile, proveniência
   (seção 6). Cancelamento ou falha = `DROP` da tabela e nenhum item (seção 6.6).
6. **Tabela `d_<slug>.c_<uuid16>`** com `fid bigint` (sequência com teto 2^31−1), `globalid uuid UNIQUE`, `versao
   int`, `tenant_id` com RLS igual à do catálogo, `geom geometry(<Tipo>, <srid>)` tipada, `criado_em/atualizado_em/
   criado_por/atualizado_por`, gatilhos de versão e de rastreio (seção 7; D3, C4, C5).
7. **Nomes de coluna normalizados por algoritmo nosso** (o `LAUNDER` do GDAL não basta, MEDIDO): minúsculo, sem
   acento, `[a-z0-9_]`, ≤ 63 bytes, sem começar por dígito, reservados com `_`, duplicatas com `_2`, mapa
   original → novo guardado em `item.dados.campos[].nome_original` (seção 8).
8. **CRS do arquivo quando tem código EPSG; senão pergunta com sugestão** (4674 em graus no Brasil, 3197x/3198x em
   metros pela zona do extent); nunca reprojetar na carga; extent do item em 4326 (seção 9; D4, C11).
9. **Formatos por driver com regra escrita** e mensagem exata de recusa (seção 10): shapefile zipado, GPKG,
   GeoJSON/Seq, KML/KMZ, CSV/TXT, XLSX/XLS/ODS, GPX, DXF, FlatGeobuf, GML, GDB zipada, MapInfo; DWG por conversão
   externa (seção 12); GeoParquet fora desta fase (10.3).
10. **CSV e XLSX passam por normalizador nosso** antes do GDAL (codificação, separador, vírgula decimal e milhar,
    datas, colunas de coordenada, WKT, duplicatas, aspas) que grava um CSV canônico + `.csvt` no diretório de trabalho
    (seção 11).
11. **DXF** pelo driver do GDAL com `DXF_INLINE_BLOCKS=FALSE` (bloco vira ponto com `blockname/blockscale/blockangle`),
    uma camada por *layer* do DXF, unidade lida em `$INSUNITS`, georreferência por Helmert com RMSE (seção 12).
12. **Atualizar dados** como job com tabela nova + `RENAME` atômico e a anterior retida (seção 13); **exportação** como
    job `ogr2ogr` inverso com arquivo-item de 7 dias (seção 14); vista e fonte registrada seguem o ADR 0004 e têm
    só o que este ADR lhes obriga (seção 15).
13. **Contrato de API** em `/api/uploads`, `/api/importacoes`, `/api/camadas/{id}/…`, erros D18 (seção 16); telas
    `/conteudo/novo/arquivo` (assistente em 4 passos) e aba "Dados" da camada (seção 17); limites em `app/limites.py`
    seção `# --- ingestão (L0-04)` (seção 18); testes com um arquivo aberto por formato gerado por
    `tests/dados/gerar.py` (seção 19); migração `007_ingestao.sql` (seção 20).

---

## 2. Pipeline: estados, quem faz o quê, onde grava

```
navegador                         API (plat-api)                       worker (plat-worker)                 banco / Garage
─────────                         ──────────────                       ────────────────────                 ──────────────
1 escolhe arquivo  ──POST /api/uploads──▶ reserva cota, cria upload ─────────────────────────────────────▶ plat.upload (iniciado)
2 envia partes     ──PUT /api/uploads/{id}/partes/{n}──▶ grava parte no Garage (multipart S3) ───────────▶ objeto parcial
3 conclui          ──POST /api/uploads/{id}/concluir──▶ fecha objeto, sha256, tipo×bytes ─────────────────▶ item 'arquivo' + plat.arquivo
                                   cria job ingestao.inspecionar ──▶ [RLIMIT] ogrinfo -json + sondas ──────▶ plat.importacao (inspecionado, proposta jsonb)
4 vê proposta      ◀──GET /api/importacoes/{id}── (SSE do job do ADR 0003 avisa quando pronta)
5 edita e confirma ──PUT /api/importacoes/{id}/confirmar──▶ valida contra a proposta; cria job ingestao.carregar
                                                                     ──▶ [RLIMIT] ogr2ogr → d_<slug>.c_<uuid16>
                                                                         SQL pós-carga (uma transação)
                                                                         item 'camada_vetorial' + relações + tile()
                                                                         proveniência ────────────────────▶ plat.importacao (concluida, relatorio jsonb)
6 abre a camada    ◀──/conteudo/{item_id}── (resultado do job traz item_id, ADR 0003 3.3)
```

### 2.1 Máquina de estados de `plat.importacao` (uma linha por camada-alvo; um arquivo com N camadas = N linhas)

`inspecionando` → `proposta` → (`confirmada` →) `carregando` → `concluida` | `falhou` | `cancelada` | `expirada`.
`proposta` expira em 24 h sem confirmação (periódico `ingestao.expirar`); o arquivo-item continua existindo (o
usuário pode reinspecionar: `POST /api/importacoes` de novo sobre o mesmo `arquivo_id`). Estado final é imutável
(gatilho igual ao do `plat.job`). O `job_id` de cada etapa fica na linha; a tela de Tarefas do L0-05 mostra o job e a
tela de importação mostra a linha.

### 2.2 O que este ADR NÃO faz

Antivírus do upload (L7-03-a), geocodificação de CSV com endereço (L2-11-a), anexos (L2-03), edição (L2-03), serviços
Esri/OGC da camada (L2-04; aqui só se cria a **função de tile** que o C3 obriga), miniatura (job `catalogo.miniatura`
do ADR 0004, disparado no fim da carga), raster (L1-01), conexão externa completa (L0-04-i tem seção própria, curta).

---

## 3. Upload retomável (L0-04-a)

### 3.1 Forma

- `POST /api/uploads` `{nome, bytes, tipo_declarado, sha256?}` → `201 {id, parte_bytes: 16777216, partes: N,
  expira_em}`. `bytes > UPLOAD_BYTES_MAX` (2 GiB) → `413 arquivo_grande`. Cota: `SELECT … FOR UPDATE` no tenant
  (D16) e `UPDATE tenant SET uso_reservado_bytes += bytes`; se `uso + reservado + bytes > cota_bytes` → `413 cota`
  **antes de qualquer byte** (portão). `tipo_declarado` ∈ lista da seção 10 (senão `422 tipo_desconhecido`).
- `PUT /api/uploads/{id}/partes/{n}` com corpo `application/octet-stream` de exatamente `parte_bytes` (a última pode
  ser menor), cabeçalho `Content-Length` obrigatório, `X-Parte-SHA256` opcional (conferido se vier). Partes **fora de
  ordem e reenviadas** são aceitas (o `addPart` da Esri, DOC E11-additempart): a parte é enviada ao Garage como
  *UploadPart* do *multipart upload* aberto na criação (contrato do L0-11: `objetos.parte_iniciar/parte_enviar/
  parte_concluir`), e `plat.upload_parte (upload_id, n, bytes, etag, sha256, recebida_em)` guarda o recibo; reenvio
  substitui a linha e o *part* (S3 troca o ETag). Resposta `200 {n, recebidas: k, faltam: [..]}`.
  Motivo de não usar `multipart/form-data`: `python-multipart` está ausente (0.1) e o corpo bruto dispensa parser;
  o navegador manda `fetch(url, {method:'PUT', body: blob.slice(a, b)})`. `client_max_body_size` da `location`
  `/api/uploads/` = `20m` (16 MiB + folga); a API não guarda a parte em memória: passa o corpo em *stream* ao
  cliente S3 (o cliente S3 é o do L0-11; se ele exigir bytes inteiros, 16 MiB × 2 workers cabe no `MemoryMax=1G`).
- `POST /api/uploads/{id}/concluir` → conferências na ordem: (1) todas as partes presentes (`409 partes_faltando
  {faltam}`); (2) *CompleteMultipartUpload* no Garage; (3) sha256 do objeto **lido de volta** em *stream* (o Garage
  não calcula sha256 do todo; LIDO no SIG de teste interno `_save()`: sha256 do arquivo é o nome); se o cliente mandou
  `sha256`, tem de bater (`422 sha256_divergente`); (4) `bytes` real = declarado (`422 tamanho_divergente`); (5) tipo
  × conteúdo (3.3) (`422 conteudo_nao_corresponde`, mensagem exata: `conteúdo não corresponde ao tipo <t>: o arquivo é
  <o que o magic diz>`); (6) cota: `uso += bytes`, `reservado -= bytes`; (7) `plat.arquivo` (L0-11) + item `arquivo`
  (ADR 0004 tipo `arquivo`, `dados = {chave, sha256, bytes, content_type, nome_original}`) com o nome do objeto
  `arquivo/<item uuid>/<sha256>.<ext>`; (8) `202 {arquivo_id, item_id, importacao_ids: [..]}` — a inspeção é criada
  automaticamente (3.4) salvo `inspecionar=false`.
- `DELETE /api/uploads/{id}` aborta (`AbortMultipartUpload`, devolve reserva). Periódico `ingestao.uploads_expirar`
  (`*/30 * * * *`): uploads sem parte há 24 h → aborta e libera reserva (portão "some em 24 h").
- Concorrência: `plat.upload` tem `usuario_id`; parte de outro usuário/sessão do mesmo `id` → `404` (mesma regra dos
  itens); duas sessões do **mesmo** usuário podem alternar partes (refutação "duas sessões subindo o mesmo uploadId"):
  o `UPDATE … WHERE upload_id AND n` é atômico e a última gravação vence; `concluir` concorrente é serializado por
  `SELECT … FOR UPDATE` na linha do upload (o 2º recebe `409 ja_concluido`).

### 3.2 Zip: bomba e caminho

Antes de aceitar o zip como `shapefile.zip`, `gdb.zip`, `kmz`, `tab.zip` ou `zip`: `zipfile.ZipFile` em *stream* do
objeto (o cabeçalho central fica no fim: o L0-11 expõe leitura por *range*), conferindo **sem extrair**: entradas ≤
`ZIP_ENTRADAS_MAX` (1.000), soma de `file_size` ≤ `ZIP_DESCOMPRIMIDO_MAX` (8 GiB) e razão descomprimido/comprimido ≤
`ZIP_RAZAO_MAX` (100) (`422 zip_suspeito {entradas, razao}`), nenhum nome com `..`, `/` inicial, `\`, byte de
controle ou > 255 bytes (`422 zip_caminho_invalido {nome}`), nenhum zip dentro do zip com mais de 1 nível
(`422 zip_aninhado`), nenhum *symlink* (atributo externo `0xA000`). Extração, quando o driver não lê `/vsizip/`
(GDB, TAB e KMZ leem; shapefile lê), é feita pelo job de inspeção no `dir_trabalho` com `extractall` **após** essas
conferências e com `RLIMIT_FSIZE` = `ZIP_DESCOMPRIMIDO_MAX`.

### 3.3 Tipo declarado × bytes (o que se aceita como prova)

| tipo declarado | extensão(ões) | prova pelos bytes |
|---|---|---|
| `shapefile.zip` | `.zip` | zip com ≥ 1 trio `.shp/.shx/.dbf` de mesmo nome (case-insensitive) |
| `gpkg` | `.gpkg` | `SQLite format 3\0` nos 16 primeiros bytes + tabela `gpkg_contents` (`sqlite3` da stdlib, só leitura) |
| `geojson` / `geojsonseq` | `.geojson .json` / `.geojsonl .ndjson .jsonl` | 1º caractere não-branco `{`; `"type"` nos primeiros 4 KB; Seq: 1ª linha é um objeto completo |
| `kml` / `kmz` | `.kml` / `.kmz` | XML com `<kml` nos primeiros 4 KB / zip com `doc.kml` ou `*.kml` |
| `csv` / `txt` / `tsv` | `.csv .txt .tsv .psv` | texto (sem byte NUL nos primeiros 64 KB) |
| `xlsx` / `xls` / `ods` | idem | zip com `xl/workbook.xml` / assinatura OLE2 `D0 CF 11 E0` / zip com `content.xml` e `mimetype` ODS |
| `gpx` | `.gpx` | XML com `<gpx` |
| `dxf` | `.dxf` | texto começando por `0\r?\nSECTION` (após BOM/espaços) — **`AutoCAD Binary DXF` é recusado com mensagem própria** (seção 12) |
| `dwg` | `.dwg` | `AC10` nos 4 primeiros bytes (`AC1015` R2000 … `AC1032` R2018) |
| `fgb` | `.fgb` | bytes `66 67 62` |
| `gml` | `.gml .xml` | XML com namespace `opengis.net/gml` |
| `gdb.zip` | `.zip` | zip com diretório `*.gdb/` contendo `gdb` e `a00000001.gdbtable` |
| `tab.zip` / `mif.zip` | `.zip` | zip com `.tab/.dat/.map/.id` ou `.mif/.mid` |
| `parquet` | `.parquet` | `PAR1` no início e no fim — **aceito como arquivo, recusado na inspeção** (10.3) |
| `zip` (genérico) | `.zip` | zip válido; a inspeção lista o conteúdo e decide (3.4) |

### 3.4 O que a conclusão dispara

Uma `plat.importacao` por **arquivo**, em estado `inspecionando`, e o job `ingestao.inspecionar(arquivo_id)`. Quando
o arquivo tem N camadas, a inspeção **desdobra** em N linhas (uma por camada) com o mesmo `arquivo_id` e `grupo_id`
(uuid), para que a tela confirme em bloco e cada camada vire um job de carga próprio (portão do L0-04-c: "1 job por
arquivo, N camadas" é lido como 1 job de **inspeção** por arquivo e 1 job de **carga por camada**, para que uma camada
com erro não derrube as outras e o cancelamento seja por camada; o adversário do item pai exige "importar certo ou
recusar com mensagem exata" — por camada).

---

## 4. Inspeção (job `ingestao.inspecionar`, L0-04-b)

### 4.1 Registro

`@tarefa(nome="ingestao.inspecionar", parametros=InspecionarParametros{arquivo_id: uuid}, pesado=False,
memoria_mb=768, timeout_s=300, tentativas=1, chave=lambda p: f"arquivo:{p['arquivo_id']}", versao=1,
ferramentas=("gdal",), perfil_minimo="editor")`. `tentativas=1`: erro de inspeção é definitivo (`FalhaDefinitiva`)
e vira mensagem ao usuário, não retentativa. `memoria_mb=768` cobre `ogrinfo` sobre GeoJSON de 64 MB (0.4) com
folga; não é pesado (não segura a fila).

### 4.2 Passos (cada um grava `ctx.progresso`)

1. Baixa o objeto para `dir_trabalho/<nome_original saneado>` (URL pré-assinada do L0-11); confere sha256 de novo
   (`FalhaDefinitiva "arquivo corrompido: sha256 divergente"`). `ctx.entrada(item_id, sha256, nome)`.
2. Desempacota o que precisa (3.2); `.txt/.tsv/.psv` viram cópia `.csv` no diretório (0.2: `.txt` não abre).
3. **Pré-sondas sem GDAL** (Python, em *stream*, ≤ 4 MB lidos): codificação (BOM; `charset_normalizer` sobre os
   primeiros 256 KB para CSV, `.dbf` sem `.cpg`, `.dat`, DXF), separador do CSV (`csv.Sniffer` sobre 64 KB + contagem
   por linha de `, ; \t |`; empate = pergunta), aspas desbalanceadas (contagem de `"` ímpar em linha lógica → posição
   informada), unidade e versão do DXF (`$INSUNITS`, `$ACADVER`, `$EXTMIN/$EXTMAX`), contagem de linhas (CSV) para
   comparar com `featureCount` do GDAL (0.2: aspa aberta engole linhas em silêncio).
4. **`ogrinfo -ro -json -so`** (com `-oo` conforme o formato, seção 10) via `ctx.subprocesso` → camadas, campos,
   tipos, `featureCount`, `geometryFields[].coordinateSystem.projjson`, extent. `fields[].name` recebidos como bytes
   inválidos (U+FFFD) marcam `codificacao: perguntar`.
5. **Varredura de tipo de geometria** (0.2, 120–230 ms/100 mil): GPKG e SQLite por `-dialect SQLITE … GROUP BY
   ST_GeometryType`; os demais por `-dialect OGRSQL "SELECT DISTINCT OGR_GEOMETRY"`; resultado `{tipos: {MULTIPOLYGON:
   n, POLYGON: m, NULL: k}}`. Regra de promoção: um só tipo → ele; Polygon+MultiPolygon → MultiPolygon (idem
   linhas/pontos); ponto+polígono → **pergunta** (`geometria: perguntar`, opções: `separar em N camadas` ou
   `descartar tipo X` ou `geometria genérica` (coluna `geometry(Geometry, srid)`, sem tile por tipo, com aviso de que
   o FeatureServer do L2-04 a expõe como `esriGeometryAny` e clientes Esri antigos não abrem). `n(NULL) > 0` vira
   aviso `feicoes_sem_geometria`.
6. **Amostra de validade**: `ogr2ogr -f GPKG amostra.gpkg <fonte> -limit 1000` (ou a camada inteira se ≤ 1.000) e
   `-dialect SQLITE "SELECT COUNT(*) FILTER (WHERE NOT ST_IsValid(geom)) …"` (SpatiaLite embutido no GDAL, MEDIDO em
   0.2 que o dialeto funciona); resultado `invalidas_amostra/amostra` — é estimativa, marcada como tal.
7. **Sondas por coluna** (sobre a mesma amostra de 1.000 linhas lida por `-json -features -limit 1000`): vírgula
   decimal e milhar (`^-?\d{1,3}(\.\d{3})*(,\d+)?$` em ≥ 90 % dos valores não vazios), datas (`dd/mm/aaaa`,
   `dd-mm-aaaa`, `aaaa-mm-dd`, `aaaa/mm/dd`, com/sem hora), booleanos (`sim/não`, `S/N`, `true/false`, `0/1`),
   inteiros que não cabem em `int4`, textos > 254, colunas 100 % vazias, nomes duplicados, nomes que a normalização
   (seção 8) muda, colunas de coordenada por **nome** (`lat, latitude, y, lon, long, longitude, x, este, norte, e, n`,
   case-insensitive, com/sem acento) **e por faixa** (`-90..90` e `-180..180` com ≥ 99 % dentro; ou 6-7 dígitos com
   `1e5..1e6 / 1e6..1e7` = UTM), coluna `WKT/geometry/geom/the_geom` com texto que começa por `POINT|LINE|POLY|MULTI`.
8. **CRS** (seção 9): `EPSG:n` → `srid: n`; WKT sem código → `srid: perguntar` com sugestão por `pyproj.CRS.from_wkt(
   ).to_epsg(min_confidence=70)` e, falhando, pelo extent; ausente → `perguntar` com sugestão pelo extent.
9. Grava a **proposta** (4.4) em `plat.importacao.proposta`, estado `proposta`, uma linha por camada; `resultado`
   do job = `{importacao_ids: [...]}`.

### 4.3 Recusas da inspeção (mensagem exata; estado `falhou`; `FalhaDefinitiva`)

| condição | `erro` | mensagem |
|---|---|---|
| formato de documento inteiro (GeoJSON, KML/KMZ, GML, TopoJSON, ESRIJSON) com `bytes > GEOJSON_BYTES_MAX` (64 MiB) | `arquivo_grande_para_o_formato` | `arquivo <formato> de <n> MB excede 64 MB: converta para GeoJSONSeq, GeoPackage ou FlatGeobuf, que são lidos por feição` |
| `ogrinfo` rc ≠ 0 ou sem JSON | `formato_invalido` | `o GDAL não abriu o arquivo como <formato>: <última linha do stderr, saneada, ≤ 200 caracteres>` |
| `ogrinfo` morto por sinal/memória | `arquivo_excede_memoria` | `a inspeção excedeu <memoria_mb> MB de memória; divida o arquivo ou use um formato lido por feição` |
| 0 camadas | `sem_camadas` | `o arquivo não contém camada vetorial` |
| camada com 0 campos e 0 geometria | `camada_vazia` | `a camada <nome> não tem campos nem geometria` (a camada é pulada; as outras seguem) |
| CSV com aspa desbalanceada | `csv_aspas` | `aspas desbalanceadas na linha <n> do CSV; corrija o arquivo ou escolha "texto sem aspas"` (a proposta oferece `aspas: nenhuma` como opção, que reinspeciona com `-oo QUOTED_FIELDS_AS_STRING` desligado e caractere de aspa vazio) |
| shapefile sem `.shx` ou sem `.dbf` | `shapefile_incompleto` | `o zip tem <nome>.shp mas falta <nome>.shx/.dbf` |
| `.prj` presente mas ilegível | `prj_ilegivel` | vira `srid: perguntar` com o WKT bruto exibido (não é recusa) |
| DXF binário | `dxf_binario` | `DXF binário não é aceito; salve como DXF ASCII (R2000 ou superior)` |
| DWG sem conversor | `dwg_sem_conversor` | seção 12 |
| Parquet | `formato_nao_suportado_nesta_versao` | `GeoParquet ainda não é importado; exporte como GeoPackage ou FlatGeobuf` |
| GDB com raster/mosaico | não recusa: entra no `relatorio.nao_importado` |
| DXF com > `DXF_ENTIDADES_MAX` (2.000.000) entidades (contado por `^0\r?\n(INSERT|LWPOLYLINE|…)` na pré-sonda) | `dxf_grande` | `o DXF tem <n> entidades; o máximo é 2.000.000` |
| camada com > `CAMPOS_MAX` (500) campos (limite do JSON Schema do ADR 0004) | `campos_demais` | `a camada <nome> tem <n> campos; o máximo é 500` |

Silêncio nunca: toda saída de `ogrinfo`/`ogr2ogr` vai para `job_log` (o `ctx.subprocesso` já faz isso), e a última
linha de stderr saneada (sem caminho do disco, sem DSN) entra na mensagem.

### 4.4 A proposta (JSON, editável; é o contrato entre inspeção, tela e carga)

```json
{"importacao_id": "…", "arquivo_id": "…", "grupo_id": "…", "formato": "shapefile.zip", "driver": "ESRI Shapefile",
 "camada_origem": "municipios", "camada_indice": 0,
 "titulo": "municipios",                      -- editável; vira item.titulo
 "nome_tabela": "c_3f9a1c2b7e8d4a51",          -- fixo, gerado aqui (uuid16 do item futuro), mostrado só na aba Dados
 "feicoes": 75, "feicoes_exatas": true,        -- false quando o driver estima (KML, GML, CSV grande)
 "geometria": {"tipos": {"POLYGON": 75}, "escolhida": "MultiPolygon", "perguntar": false, "opcoes": ["MultiPolygon"],
               "z": false, "m": false, "descartar_z": true},
 "crs": {"origem": "prj", "srid": 4326, "perguntar": false, "wkt": null, "sugestao": null, "extent_origem": [..4..]},
 "codificacao": {"origem": "cpg", "valor": "UTF-8", "perguntar": false, "sugestao": null},
 "csv": null,                                  -- seção 11 quando CSV/XLSX
 "dxf": null,                                  -- seção 12 quando DXF
 "campos": [
   {"origem": "Código IBGE", "nome": "codigo_ibge", "tipo_origem": "String", "largura": 80, "tipo": "text",
    "opcoes_tipo": ["text", "bigint", "integer"], "nulos_amostra": 0, "distintos_amostra": 75, "exemplo": "2800100",
    "avisos": []},
   {"origem": "Área km²", "nome": "area_km2", "tipo_origem": "Real", "tipo": "double precision", "avisos": []},
   {"origem": "select", "nome": "select_", "tipo": "text", "avisos": ["palavra reservada: renomeado"]},
   {"origem": "Município", "nome": "municipio", "tipo": "text", "avisos": []},
   {"origem": "Município", "nome": "municipio_2", "tipo": "text", "avisos": ["nome duplicado: renomeado"]}],
 "validade": {"amostra": 75, "invalidas": 1, "exemplo": "Self-intersection[-37.05 -10.85]", "acao": "corrigir"},
 "fuso": {"perguntar": true, "sugestao": "America/Sao_Paulo", "aplica_a": ["data_hora"]},  -- só se há DateTime sem fuso
 "avisos": ["o arquivo declara crs EPSG:31984 dentro de GeoJSON (fora da RFC 7946); será respeitado"],
 "perguntas": ["fuso"],                       -- lista do que bloqueia a confirmação
 "custo_estimado": {"linhas": 75, "bytes_estimados": 262144, "cota_restante_bytes": 21000000000}}
```

Regras: `perguntas` não vazia → `confirmar` devolve `422 perguntas_pendentes {perguntas}`. A tela só mostra
"Importar" quando a lista está vazia. `nome_tabela` é decidido na inspeção para que o item e a tabela nasçam com o
mesmo uuid (`c_` + 16 hex do `item.id` gerado por `gen_random_uuid()` na criação da linha de `importacao`; o item é
criado na carga com **esse** id — `INSERT INTO plat.item (id, …) VALUES (:id, …)`, o ADR 0004 aceita id fornecido pela
migração/serviço e o gatilho `tg_item_imutaveis` só proíbe **mudar**).

---

## 5. Confirmação (`PUT /api/importacoes/{id}/confirmar`)

O corpo é a proposta editada (mesmo JSON, só os campos editáveis: `titulo`, `pasta_id`, `geometria.escolhida`,
`crs.srid`, `codificacao.valor`, `csv.*`, `dxf.*`, `campos[].nome/tipo/importar`, `validade.acao`, `fuso.valor`,
`tags`, `resumo`). A API valida **contra a proposta gravada** (não contra o arquivo): campo que não existe na
proposta → `422 campo_desconhecido`; tipo fora de `opcoes_tipo` → `422 tipo_nao_permitido`; `srid` inexistente em
`spatial_ref_sys` → `422 srid_inexistente`; nome normalizado que colide → `422 nome_colide {nome}`; pergunta sem
resposta → `422 perguntas_pendentes`. Regras de resposta:

| pergunta | quando | opções que a tela mostra | o que a carga faz |
|---|---|---|---|
| CRS ausente / WKT sem código | shapefile sem `.prj`, CSV, DXF, TAB com WKT `unnamed`, GeoJSON sem `crs` mas com valores fora de ±180 | sugestão da inspeção (seção 9) em destaque; busca por nome/código em `spatial_ref_sys` (`GET /api/crs?q=`); "os valores são graus/metros" como dica | `-a_srs EPSG:n` (atribui, não reprojeta) |
| CRS declarado parece errado | extent do arquivo fora do planeta ou fora do Brasil quando `tenant.config.pais = BR` | "manter" · "trocar por …" | `-a_srs` se trocou |
| codificação | `.dbf` sem `.cpg`; CSV/DXF/TAB sem BOM e sem detecção ≥ 0,9 de confiança | UTF-8 · ISO-8859-1 · Windows-1252 (com amostra de 3 nomes renderizados em cada) | `-oo ENCODING=` (shapefile, TAB) / normalizador (CSV) / `--config DXF_ENCODING` |
| tipo de geometria misto | 4.2 passo 5 | separar em camadas · descartar tipo · genérica | `-where "OGR_GEOMETRY='…'"` por camada ou `-nlt GEOMETRY` |
| colunas de coordenada | CSV/XLSX com ≥ 2 candidatas ou nenhuma | par X/Y, ou coluna WKT, ou "sem geometria (tabela)" | normalizador grava `.csvt` e `X_POSSIBLE_NAMES/Y_POSSIBLE_NAMES` |
| unidade do DXF | sempre (12) | metro · centímetro · milímetro · polegada · pé · "outra (fator)" | `ST_Affine` com o fator na pós-carga |
| georreferência do DXF | sempre (12) | "já está no CRS n" · "2-4 pontos de controle" | Helmert (12.3) |
| fuso horário | campo `DateTime` sem deslocamento | lista IANA, sugestão `America/Sao_Paulo` (`tenant.config.fuso`) | `AT TIME ZONE` na pós-carga; coluna vira `timestamptz` |
| Z/M | geometria com Z ou M | descartar (padrão) · manter | `-dim XY` / `-dim XYZ` |
| inválidas | `validade.invalidas > 0` | corrigir (`ST_MakeValid`, padrão) · descartar · recusar a carga | 6.4 |

A confirmação grava a proposta final em `plat.importacao.confirmacao`, estado `confirmada`, cria o job
`ingestao.carregar(importacao_id)` e devolve `202 {job_id}`. A confirmação em bloco (`PUT /api/importacoes/grupo/
{grupo_id}/confirmar` com `{importacoes: [{id, …}]}`) cria N jobs com a mesma `chave` de arquivo, que a fila
serializa (ADR 0003: mesma chave nunca roda em paralelo) — evita dois `ogr2ogr` lendo o mesmo GPKG.

---

## 6. Carga (job `ingestao.carregar`, L0-04-c)

### 6.1 Registro

`@tarefa(nome="ingestao.carregar", parametros=CarregarParametros{importacao_id: uuid}, pesado=True, memoria_mb=1024,
timeout_s=3600, tentativas=1, chave=lambda p: f"arquivo:{p['arquivo_id']}", versao=1, ferramentas=("gdal",),
perfil_minimo="editor")`. `pesado=True` porque um só `ogr2ogr` + `ST_MakeValid` em milhões de linhas satura I/O e o
guardrail é "1 job pesado por vez"; `memoria_mb=1024` cobre o GeoJSON de 64 MB (0.4). `tentativas=1`: a carga é
idempotente por reexecução manual (o usuário clica "repetir"), nunca por retentativa automática, porque a 1ª
tentativa pode ter deixado tabela parcial que o passo 0 apaga.

### 6.2 Passos (numerados; cada um é uma linha de `job_log` e um `ctx.progresso`)

0. **Limpeza defensiva**: `DROP TABLE IF EXISTS d_<slug>.<nome_tabela>` (tentativa anterior morta) e
   `DELETE FROM plat.item WHERE id = :item_id AND tipo = 'camada_vetorial'` se existir sem tabela (nunca acontece
   pela ordem dos passos, mas o adversário mata o worker no meio). `CREATE SCHEMA IF NOT EXISTS d_<slug>
   AUTHORIZATION plat_app` (a primeira camada do inquilino cria o schema; `plat.tenant_criar` do ADR 0001 passa a
   criá-lo também — alteração pequena, registrada na seção 20).
1. Baixa o objeto para `dir_trabalho` (como na inspeção), confere sha256, `ctx.entrada(...)`. Se CSV/XLSX: roda o
   normalizador (seção 11) e a fonte passa a ser `dir_trabalho/normalizado.csv` + `.csvt`.
2. **Reserva de cota**: estimativa = `bytes do arquivo × 3` (MEDIDO: shapefile 14 MB → tabela 45 MB com índice e
   colunas extras; GPKG 37 MB → 45 MB); `SELECT … FOR UPDATE` no tenant; se `uso + reservado + estimativa >
   cota_bytes` → `FalhaDefinitiva "cota do inquilino excedida: faltam <n> MB"` **antes** de criar tabela (portão:
   "sem tabela").
3. **`ogr2ogr`** via `ctx.subprocesso` (herda `RLIMIT_DATA` e `OPENBLAS_NUM_THREADS=1`):

   ```
   ogr2ogr -f PostgreSQL "PG:<PLAT_DSN> application_name=plat-ingestao" <fonte> [<camada_origem>]
     -nln d_<slug>.<nome_tabela> -nlt <geometria.escolhida em maiúsculo | GEOMETRY> [-dim XY]
     -lco GEOMETRY_NAME=geom -lco FID=fid -lco FID64=YES -lco SPATIAL_INDEX=NONE -lco PRECISION=NO -lco LAUNDER=NO
     -lco COLUMN_TYPES=<nome>=<tipo pg>,…      # tipos confirmados que diferem do padrão do driver
     -a_srs EPSG:<srid>                        # sempre explícito (o confirmado); nunca -t_srs (C11)
     [-oo ENCODING=…] [-oo AUTODETECT_TYPE=YES …] [--config DXF_INLINE_BLOCKS FALSE] [--config DXF_ENCODING …]
     [-where "OGR_GEOMETRY='POLYGON' OR OGR_GEOMETRY='MULTIPOLYGON'"]   # tipo misto separado
     -dialect OGRSQL -sql "SELECT \"<origem 1>\" AS <nome 1>, … FROM \"<camada_origem>\""  # só os campos com importar=true
     --config PG_USE_COPY YES --config OGR_TRUNCATE NO -progress
   ```

   Motivos medidos: `PROMOTE_TO_MULTI` não tipa coluna de origem `Geometry` (0.3) → `-nlt` explícito; `LAUNDER`
   mantém acento/espaço (0.3) → `-sql … AS`; `PRECISION=NO` evita `varchar(80)` e o truncamento de 254 do shapefile
   passa a ser só aviso; `SPATIAL_INDEX=NONE` porque o GIST é criado depois do `ST_MakeValid` (índice sobre geometria
   que vai mudar é trabalho perdido); `COPY` (2,6 s/100 mil). `-progress` escreve `0…10…20…100` no stdout, que o
   `ctx.subprocesso` já leva ao log; o progresso do job é atualizado ao final do passo (o `communicate` do
   `ctx.subprocesso` bufferiza — alteração pequena do L0-05 proposta na seção 20: um `subprocesso_stream` que chama
   `ctx.progresso` a cada linha de stdout). rc ≠ 0 → `FalhaDefinitiva "ogr2ogr falhou: <última linha do stderr
   saneada>"` e passo 9.
4. **Validade** (uma transação SQL, `ctx.db()` como o inquilino; `plat_app` é dono da tabela recém-criada):
   `SELECT count(*) FILTER (WHERE NOT ST_IsValid(geom)), count(*) FILTER (WHERE geom IS NULL), count(*)` →
   relatório; conforme `validade.acao`: `corrigir` → `UPDATE … SET geom = ST_Multi(ST_CollectionExtract(
   ST_MakeValid(ST_ReducePrecision(geom, 1e-9)), <dimensão da camada>)) WHERE NOT ST_IsValid(geom)`, contando
   `corrigidas` e, entre elas, `descartadas` (as que viraram vazias: `ST_IsEmpty` → linha apagada, fid anotado no
   relatório até 1.000 fids); `descartar` → `DELETE … WHERE NOT ST_IsValid(geom)`; `recusar` → se `invalidas > 0`,
   `FalhaDefinitiva` com o número e passo 9. `ST_ReducePrecision` a 1e-9° (graus) ou 1e-4 m (métrico), regra da
   casa (SKILL "ST_MakeValid + ST_ReducePrecision antes de operação booleana em massa"). MEDIDO: 1,6 s/100 mil.
5. **Colunas obrigatórias, gatilhos, RLS, índices** — o bloco SQL da seção 7 (função `plat.camada_preparar(schema,
   tabela, srid, tipo)` SECURITY DEFINER, para que a política e a sequência sejam sempre iguais). Unidade do DXF ≠
   metro → `UPDATE … SET geom = ST_Affine(geom, f, 0, 0, f, 0, 0)` **antes** do índice; georreferência Helmert idem
   (12.3). Fuso: `ALTER COLUMN … TYPE timestamptz USING (col AT TIME ZONE :fuso)`.
6. **`ANALYZE`** e **estatísticas** (SQL único): `count(*)`, `ST_Extent(geom)` (+ `ST_Transform(…, 4326)` para o item),
   por campo: `count(*) FILTER (WHERE c IS NULL)`, `count(DISTINCT c)` (limitado a 10 mil por `LIMIT` em subconsulta
   quando `n > 1 mi`), `min/max` para numérico/data, `max(length)` para texto. Gravadas em `item.dados.estatisticas`
   (7.4 do JSON Schema estendido, seção 20) com `calculadas_em`.
7. **Item + relações + tile**: `INSERT INTO plat.item (id = :item_id, tipo = 'camada_vetorial', titulo, resumo,
   tags, pasta_id, extent (4326), extent_origem = 'dado', dados = {schema, tabela, geometria, srid, campos[{nome,
   tipo, alias = nome_original, nome_original, tipo_origem}], fonte: 'hospedada', estatisticas, procedencia (6.3),
   importacao: {importacao_id, job_id, relatorio}}, tamanho_bytes = pg_total_relation_size, dono = usuário da
   importação)`; `plat.item_relacao (origem = item arquivo, destino = item camada, tipo = 'arquivo_de_camada')` e
   `(origem = camada, destino = arquivo, tipo = 'resultado_de_job')`? — não: `resultado_de_job` é para item produzido
   por job **a partir de outro item**; aqui a relação canônica é `arquivo_de_camada` (ADR 0004 5.1: origem `arquivo`
   → destino `camada`, `arrasta_dono`, `apaga_junto`), e a proveniência fica em `dados.procedencia`. Função de tile
   `d_<slug>.tile_<uuid16>(z int, x int, y int, query_params json) RETURNS bytea` conforme o C3 (corpo na seção 7.3);
   é a única coisa que este ADR cria para o L2-01/L2-04 — a publicação do serviço (FeatureServer/OGC) é do L2-04 e
   lê `item.dados`. Evento `itens/criar` + `camadas/importar` (vocabulário do L0-10; seção 20).
8. Cota: `uso_bytes += pg_total_relation_size`, `reservado -= estimativa`. `plat.importacao` → `concluida`,
   `relatorio` (6.5). Dispara job `catalogo.miniatura(item_id)` (ADR 0004 11.4). Resultado do job:
   `{"item_id": …, "feicoes": n, "corrigidas": c, "descartadas": d, "avisos": [...]}`.
9. **Falha ou cancelamento em qualquer passo** (`Cancelado` capturado e relançado; qualquer exceção): `DROP TABLE IF
   EXISTS` em conexão **nova** (a transação do passo 4-7 já foi revertida pelo `db()`), `DELETE FROM plat.item WHERE
   id = :item_id` (só existe a partir do passo 7, na mesma transação — logo nunca sobra item sem tabela), reserva de
   cota devolvida, `plat.importacao` → `falhou`/`cancelada` com `erro`. É o que o portão exige: "job cancelado deixa
   0 tabela órfã" e a refutação "não fica tabela sem item nem item sem tabela". Invariante testável: `SELECT
   count(*) FROM pg_tables WHERE schemaname LIKE 'd\_%' AND tablename NOT IN (SELECT dados->>'tabela' FROM
   plat.item WHERE tipo='camada_vetorial')` = 0, e o inverso (`tests/api/ingestao/test_orfaos.py`). O periódico
   `ingestao.orfaos` (`15 4 * * *`) mede e **avisa** (evento `sistema/orfaos`), nunca apaga sozinho.

### 6.3 Proveniência (bloco `dados.procedencia`, D17, mesmo esquema do L0-09-a)

`{fonte: nome_original, url: null, licenca: null, data_do_dado: null, data_de_acesso: <criado_em do arquivo>,
gerador: "plat ingestao.carregar v1", git_sha, gdal: "3.8.4", sha256: <do arquivo>, metodo: "ogr2ogr + ST_MakeValid",
confianca: null, limites: [avisos], frescor: null, proxima_verificacao: null, job_id, importacao_id}` — os campos
`null` são os que só o usuário pode preencher (a aba Metadado do ADR 0004 os edita). `job.proveniencia` do ADR 0003
recebe o mesmo `sha256` por `ctx.entrada`. Regra da casa: procedência errada é pior que nenhuma; por isso `url` e
`licenca` **nunca** são inferidas do nome do arquivo.

### 6.4 O que "corrigir" significa e o que não significa

`ST_MakeValid` (GEOS 3.12, método `structure` padrão do PostGIS 3.6 — DOC PostGIS) preserva área e devolve coleção;
`ST_CollectionExtract` mantém só a dimensão da camada (polígono → 3; linha → 2; ponto → 1) e descarta os restos de
dimensão menor (linhas degeneradas de um polígono, por exemplo) — **isso é contado em `descartadas_partes`** no
relatório. A gravata (0.3) vira `MultiPolygon` de 2 partes com a soma das áreas: geometria diferente da desenhada,
por isso o relatório lista até 1.000 fids corrigidos e a tela os destaca no mapa; "corrigido" não é "igual ao
original". Anel não fechado é fechado pelo GDAL na leitura (aviso `Non closed ring detected`, 0.2) e conta como
`avisos.aneis_fechados = n` (n vem do stderr).

### 6.5 Relatório (`plat.importacao.relatorio`, mostrado na tela e guardado em `item.dados.importacao.relatorio`)

`{feicoes_origem, feicoes_carregadas, sem_geometria, invalidas, corrigidas, descartadas, descartadas_partes,
fids_corrigidos: [...≤1000], aneis_fechados, campos_truncados: [{nome, largura_origem}], campos_renomeados: [{origem,
nome, motivo}], campos_nao_importados: [...], tipos_ajustados: [{nome, de, para}], z_descartado: bool, srid,
extent_4326, tempo_s: {download, ogr2ogr, validade, preparar, estatisticas, total}, bytes_tabela, avisos: [...]}`.

### 6.6 Concorrência e reexecução

Mesmo arquivo importado 2× em paralelo (refutação): são duas `importacao` com dois `item_id` e dois `nome_tabela`;
a `chave` do job (`arquivo:<id>`) serializa as cargas — as duas terminam, nenhuma falha. CRS mentido (refutação): a
inspeção já avisou (`crs parece errado`); a carga grava o que foi confirmado e o extent do item sai fora do planeta
→ `avisos.extent_fora_do_planeta` e o extent do item fica `NULL` com `extent_origem = NULL` (o CHECK do ADR 0004
recusa fora de ±180/±90), item marcado com aviso na tela. Worker morto no meio (SIGKILL): o L0-05 devolve o job
como `falhou` após o teto de reinícios; a próxima execução manual começa pelo passo 0 (limpeza).

---

## 7. A tabela de camada `d_<slug>.c_<uuid16>` (D3, C4, C5, L4 C1/C10)

### 7.1 DDL normativo (o que `plat.camada_preparar()` deixa depois do `ogr2ogr`; `migração 007` cria a função)

```sql
-- o ogr2ogr já criou: fid bigint (sequência), <campos normalizados>, geom geometry(<Tipo>, <srid>)
ALTER TABLE d_<slug>.c_<uuid16>
  ADD COLUMN IF NOT EXISTS globalid       uuid        NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS versao         int         NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS tenant_id      int         NOT NULL DEFAULT plat.tenant_atual(),
  ADD COLUMN IF NOT EXISTS criado_em      timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS atualizado_em  timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS criado_por     int,
  ADD COLUMN IF NOT EXISTS atualizado_por int;
ALTER TABLE d_<slug>.c_<uuid16> ADD CONSTRAINT c_<uuid16>_globalid_u UNIQUE (globalid);
ALTER SEQUENCE d_<slug>.c_<uuid16>_fid_seq MAXVALUE 2147483647 NO CYCLE;   -- C4: OID de 32 bits para clientes Esri < 11.3
ALTER TABLE d_<slug>.c_<uuid16> ALTER COLUMN tenant_id SET NOT NULL;
UPDATE d_<slug>.c_<uuid16> SET criado_por = :usuario_id, atualizado_por = :usuario_id;   -- só na carga (uma vez)
CREATE INDEX c_<uuid16>_geom_gix ON d_<slug>.c_<uuid16> USING gist (geom);
CREATE INDEX c_<uuid16>_versao_ix ON d_<slug>.c_<uuid16> (atualizado_em);              -- rastreio de mudança (L2-13-b)
ALTER TABLE d_<slug>.c_<uuid16> ENABLE ROW LEVEL SECURITY;
ALTER TABLE d_<slug>.c_<uuid16> FORCE ROW LEVEL SECURITY;                              -- vale até para o dono (plat_app)
DROP POLICY IF EXISTS p_c_<uuid16> ON d_<slug>.c_<uuid16>;
CREATE POLICY p_c_<uuid16> ON d_<slug>.c_<uuid16> FOR ALL TO plat_app, plat_leitor
  USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual());
CREATE TRIGGER tg_versao BEFORE UPDATE ON d_<slug>.c_<uuid16>
  FOR EACH ROW EXECUTE FUNCTION plat.feicao_versao();      -- versao = OLD.versao + 1; atualizado_em = now(); atualizado_por = plat.usuario_atual()
CREATE TRIGGER tg_tenant BEFORE INSERT ON d_<slug>.c_<uuid16>
  FOR EACH ROW EXECUTE FUNCTION plat.feicao_inserir();     -- tenant_id := plat.tenant_atual() (recusa NULL), criado_por/atualizado_por := plat.usuario_atual()
COMMENT ON TABLE d_<slug>.c_<uuid16> IS 'plat camada <item uuid>';                     -- para o inventário de órfãos
GRANT SELECT ON d_<slug>.c_<uuid16> TO plat_leitor;                                     -- Martin/leitores (C18)
```

Notas: (1) `FORCE ROW LEVEL SECURITY` porque a tabela é **de propriedade** de `plat_app` (o `ogr2ogr` conecta como
`plat_app`) e a RLS por padrão não se aplica ao dono — sem `FORCE`, o portão P6 falharia em silêncio; a política do
catálogo (ADR 0001) não precisa disso porque as tabelas de `plat` são do `postgres`. Testado no item por `pg_class.
relrowsecurity AND relforcerowsecurity`. (2) `plat_leitor` é a role só-leitura que o L2 C18 cria; a migração 007 cria
a role se não existir (`DO $$ … CREATE ROLE plat_leitor NOLOGIN $$`, sem senha, sem `pg_hba`), e o L2-01 lhe dá
LOGIN. (3) O histórico por feição (`fn_historico` do C5/L2-03-d) **não** é criado aqui: é do L2-03-d, que o liga
por `ALTER TABLE … ADD TRIGGER` em todas as `c_*` existentes na sua migração. (4) `fid` continua sendo a chave do
FeatureServer (`objectIdField`), `globalid` o `globalIdField` (C4). (5) Nome `c_<uuid16>` = `'c_' ||
substr(replace(item.id::text,'-',''),1,16)`; colisão em 16 hex é 2^-64 e ainda assim é conferida
(`pg_tables`) antes do `ogr2ogr` (`FalhaDefinitiva "nome de tabela colide"`, nunca aconteceu, nunca vai passar em
silêncio).

### 7.2 Tipos de coluna (mapa OGR → PostgreSQL, aplicado por `COLUMN_TYPES` quando difere do padrão do driver)

| OGR (`ogrinfo -json fields[].type/subType`) | PostgreSQL | observação |
|---|---|---|
| `String` | `text` | `PRECISION=NO` evita `varchar(n)`; largura de origem vai para `campos[].largura` |
| `Integer` / `Integer/Boolean` / `Integer/Int16` | `integer` / `boolean` / `smallint` | GPKG expõe `Boolean`; shapefile nunca (é `Integer`) |
| `Integer64` | `bigint` | |
| `Real` / `Real/Float32` | `double precision` / `real` | |
| `Date` / `Time` / `DateTime` | `date` / `time` / `timestamp with time zone` (com fuso confirmado) | DateTime sem fuso é pergunta (seção 5) |
| `Binary` | `bytea` | |
| `StringList/IntegerList/RealList` | `text[]/integer[]/double precision[]` | DXF `BlockScale` é `RealList` |
| `String/JSON` | `jsonb` | GPKG e GeoJSON com objeto aninhado |
| `String/UUID` | `uuid` | `globalid` de GDB (`GlobalID`) entra como campo comum `globalid_origem` para não colidir com o nosso |

`opcoes_tipo` na proposta permite promover `text` → `integer/bigint/double precision/date/boolean` quando a amostra
inteira converte (sonda 4.2-7); a carga usa `COLUMN_TYPES` e o `ogr2ogr` converte; valor que não converte vira NULL
**e é contado** (`tipos_ajustados[].nulos_gerados`, via `count(*) FILTER (WHERE c IS NULL)` antes/depois).

### 7.3 Função de tile por camada (o que o C3 obriga; corpo mínimo, o L2-01 estende com simplificação por zoom)

```sql
CREATE OR REPLACE FUNCTION d_<slug>.tile_<uuid16>(z int, x int, y int, query_params json) RETURNS bytea
LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE r bytea;
BEGIN
  PERFORM plat.contexto_por_token(query_params->>'token');         -- L2-04-a: define plat.tenant_id na transação; sem token = sem contexto = 0 linhas
  SELECT ST_AsMVT(q, 'c_<uuid16>', 4096, 'geom', 'fid') INTO r
  FROM (SELECT fid, <campos normalizados>, ST_AsMVTGeom(ST_Transform(geom, 3857), ST_TileEnvelope(z, x, y), 4096, 64, true) AS geom
        FROM d_<slug>.c_<uuid16> WHERE geom && ST_Transform(ST_TileEnvelope(z, x, y), <srid>)) q;
  RETURN r;
END $$;
```

`plat.contexto_por_token` ainda não existe (é do L0-02-d/L2-04-a); a migração 007 cria um **stub** que devolve
`NULL` sem definir contexto (logo a função devolve tile vazio até o L2-04-a existir) — e o teste do item confere que
o tile é vazio sem contexto e cheio com `set_config` manual. Isso não é uma casca vazia: é a semântica correta do RLS
(sem contexto, nada), e o Martin (`plat-martin`, L2-01-b) só entra depois.

### 7.4 `item.dados` de `camada_vetorial` (extensão do esquema do ADR 0004 3.2, versão 2 do tipo; migração 007)

Acrescenta a `{schema, tabela, geometria, srid, campos, fonte, edicao?}`: `campos[].{nome_original, tipo_origem,
largura?, alias}`, `estatisticas: {feicoes, extent_nativo: [4], calculadas_em, por_campo: {nome: {nulos, distintos,
min?, max?, max_len?}}}`, `procedencia` (6.3), `importacao: {importacao_id, job_id, relatorio}`, `z: bool`,
`unidade?: {origem, fator}` (DXF), `georreferencia?: {pontos: [...], rmse_m}` (DXF). `additionalProperties: false`
continua; o ADR 0004 3.3 diz que mudar esquema é `esquema_versao++` + `catalogo.migrar_dados` — como ainda não há
item desse tipo no banco, a 007 apenas atualiza a linha de `tipo_item` (`ON CONFLICT DO UPDATE`).

---

## 8. Normalização de nomes (camada, tabela e coluna)

Algoritmo `app/ingestao/nomes.py::normalizar(nome, usados) -> (nome_novo, motivo|None)` (função pura, testada com
a tabela abaixo em `tests/unit/test_nomes.py`):

1. decodificar bytes pela codificação confirmada; U+FFFD ou byte de controle → substituído por `_` (motivo
   `caractere_invalido`);
2. NFKD + remoção de diacríticos (`unicodedata`, sem `unaccent` do banco para não depender de conexão); `²`→`2`,
   `³`→`3`, `º/ª`→`o/a`, `ç`→`c` (cobertos pelo NFKD), `&`→`_e_`, `%`→`_pct`, `#`→`_n`;
3. minúsculo; qualquer sequência fora de `[a-z0-9]` → `_`; `_` repetidos comprimidos; `_` das pontas removidos;
4. vazio → `campo_<posição>`; começa por dígito → `c_` prefixado;
5. ≤ 63 **bytes** (limite do PostgreSQL) cortando antes do sufixo de desduplicação;
6. palavra reservada do PostgreSQL 16 (lista `pg_get_keywords() WHERE catcode IN ('R','T')` congelada em
   `nomes.py`, 96 nomes) ou nome das colunas obrigatórias (`fid, globalid, versao, tenant_id, geom, criado_em,
   atualizado_em, criado_por, atualizado_por`) → sufixo `_` (motivo `reservado`);
7. duplicata dentro da camada → `_2`, `_3`… (motivo `duplicado`).

| origem | resultado | motivo |
|---|---|---|
| `Código IBGE` | `codigo_ibge` | acento/espaço |
| `Área km²` | `area_km2` | |
| `select` | `select_` | reservado |
| `Município`, `Município` | `municipio`, `municipio_2` | duplicado |
| `fid` (vindo de GPKG) | `fid_` | coluna obrigatória |
| `123abc` | `c_123abc` | dígito inicial |
| `C�digo` (latin-1 lido como UTF-8) | `c_digo` + pergunta de codificação | caractere inválido |
| `mun\x01icipios` (nome de camada) | `mun_icipios` | caractere de controle |
| 70 caracteres com acento | cortado em 63 bytes | comprimento |
| `Layer` (DXF) | `layer` | |

O `alias` do campo (o que a tela e o FeatureServer mostram) é o **nome original** — quem importou não perde o nome
que conhecia; só o SQL usa o normalizado. Nome de **camada** passa pelo mesmo algoritmo para virar `titulo` sugerido
(sem cortar em 63); o nome da **tabela** nunca vem do usuário (`c_<uuid16>`).

---

## 9. CRS (D4, C11)

| situação | `crs.origem` | `srid` | `perguntar` | sugestão |
|---|---|---|---|---|
| `projjson.id` = `EPSG:n` | `prj/gpkg/…` | n | não | — |
| `EPSG:4326` em GeoJSON sem `crs` | `rfc7946` | 4326 | não | aviso quando extent fora de ±180/±90 |
| `crs` legado no GeoJSON (`EPSG::31984`) | `crs_legado` | 31984 | não | aviso "fora da RFC 7946; será respeitado" |
| WKT sem código (TAB `unnamed`, `.prj` ESRI antigo) | `wkt` | `pyproj.CRS.from_wkt(wkt).to_epsg(70)` | **sim** (mesmo com palpite) | o palpite + o WKT exibido |
| ausente (shapefile sem .prj, CSV, XLSX, DXF) | `nenhum` | — | **sim** | extent em graus dentro do Brasil (−74..−28, −34..6) → 4674; em metros → UTM SIRGAS 2000 pela zona do centro (`31978..31985` sul, `31972..31976` norte), com a lista das 3 zonas vizinhas; fora do Brasil em graus → 4326 |
| declarado mas extent fora do planeta ou fora do país (`tenant.config.pais`) | (a de cima) | o declarado | "parece errado" (não bloqueia) | idem |

Regras: `-a_srs` sempre explícito na carga (0.3: sem ele, shapefile sem .prj entra com SRID 0 em silêncio); nunca
`-t_srs` (C11: nativo preservado; reprojeção é do serviço e do L2-05); `srid` tem de existir em
`spatial_ref_sys`; extent do item = `ST_Transform(ST_Envelope(ST_Extent(geom)), 4326)`; SAD69/Córrego Alegre
(`4618, 4225, 29193…`) são aceitos como estão e o item recebe aviso `datum_antigo` (a transformação por grade do
C11 é do L7-01). `GET /api/crs?q=` lista `spatial_ref_sys` (`auth_srid`, `srtext` nome) com trigram, ≤ 20 linhas,
e uma lista fixa de favoritos brasileiros no topo (4674, 4326, 31981–31985, 3857, 5880 policônica, 4618).

---

## 10. Formatos: o que cada driver faz aqui, limites e recusas

### 10.1 Tabela normativa (L0-04-d, -e, -f)

| tipo | driver | abertura | camadas | CRS | codificação | regras e limites | recusas (além das de 4.3) |
|---|---|---|---|---|---|---|---|
| `shapefile.zip` | ESRI Shapefile via `/vsizip/` | `-oo ENCODING=<confirmada>` quando sem `.cpg`; `-oo ADJUST_GEOM_TYPE=ALL` para o tipo real | 1 por trio `.shp` no zip (N camadas) | `.prj` ou pergunta | `.cpg` ou pergunta (default sugerido: `charset_normalizer` sobre o `.dbf`) | nome de campo ≤ 10 (aviso `campos_truncados` na origem); `.dbf` ≤ 2 GB (limite do formato); Z/M perguntados; `.shp` sem `.dbf` = camada só-geometria (aceita) | `.shp` sem `.shx` → `shapefile_incompleto` |
| `gpkg` | GPKG | direto | todas as tabelas de `gpkg_contents` tipo `features` **e** `attributes` (tabelas sem geometria viram `tabela`, 10.2) | de `gpkg_spatial_ref_sys` (WKT sem código → pergunta) | UTF-8 (formato) | raster (`tiles`) listado em `nao_importado`; extensões `gpkg_rtree_index` ignoradas; `fid` de origem vira `fid_` | GPKG cifrado/corrompido → `formato_invalido` |
| `geojson` | GeoJSON | `-oo` nenhum; `--config OGR_GEOJSON_MAX_OBJ_SIZE 200` (padrão) | 1 | RFC 7946 = 4326; `crs` legado respeitado com aviso | UTF-8 | feição ≤ 16 MiB (0.4); `id` da feição vai para `id_origem` se não numérico; propriedades aninhadas → `jsonb` | feição > 16 MiB → `feicao_grande` (`a feição <n> tem <m> MB; o máximo é 16 MB`) |
| `geojsonseq` | GeoJSONSeq | direto | 1 | idem | UTF-8 | linha ≤ 16 MiB | idem |
| `kml` / `kmz` | LIBKML | direto (KMZ direto) | 1 por pasta/Document com Placemark (pastas vazias ignoradas) | sempre 4326 | UTF-8 | os 9 campos fixos do KML (`name, description, timestamp, begin, end, altitudemode, tessellate, extrude, visibility, draworder, icon`) importados só se não vazios na amostra (aviso `campos_kml_vazios_descartados`); estilo descartado com aviso `estilo_descartado`; `ExtendedData` vira campos; ≤ 64 MiB descompactado (declarado, 0.4) | > 64 MiB → `arquivo_grande_para_o_formato`; KML com só NetworkLink → `sem_camadas` |
| `csv` / `txt` / `tsv` | CSV (após normalizador, seção 11) | `-oo AUTODETECT_TYPE=YES -oo X_POSSIBLE_NAMES=<x> -oo Y_POSSIBLE_NAMES=<y>` ou `GEOM_POSSIBLE_NAMES=<wkt>`; `.csvt` gerado | 1 | pergunta (sugestão 4674 para lat/lon em graus) | detectada/perguntada | sem coordenada → `tabela` (10.2); endereço sem coordenada → item `tabela` + aviso "geocodificar no L2-11-a"; ≤ `CSV_COLUNAS_MAX` 500 | aspas (4.3); 0 linhas → aceita como tabela vazia com aviso |
| `xlsx` / `xls` / `ods` | XLSX / XLS / ODS → normalizador (11.4) | via `ogr2ogr -f CSV` para o normalizador | 1 por planilha | idem CSV | UTF-8 (formato) | datas como texto (`dd/mm/aaaa`) tratadas pelo normalizador; célula com fórmula: valor calculado (o driver lê o valor em cache) | planilha sem cabeçalho detectável → pergunta `cabecalho: linha n` |
| `gpx` | GPX | direto | 3 das 5 (`waypoints`, `tracks`, `routes`; `route_points/track_points` só se o usuário pedir) | 4326 | UTF-8 | `GPX_ELE_AS_25D` desligado: `ele` fica campo; extensões (`GPX_USE_EXTENSIONS`) importadas como campos | — |
| `dxf` | DXF | `--config DXF_INLINE_BLOCKS FALSE --config DXF_MERGE_BLOCK_GEOMETRIES TRUE --config DXF_ENCODING <confirmada>`; `DXF_CLOSED_LINE_AS_POLYGON TRUE` (polilinha fechada vira polígono) | 1 por *layer* do DXF (`-where "Layer='…'"`), mais a camada `blocos` (definições) opcional; tipo misto dentro do layer separado por 4.2-5 | pergunta (12) | `$DWGCODEPAGE` → sugestão | ≤ 2.000.000 entidades; `Text` de TEXT/MTEXT como campo; cotas (`DIMENSION`), hachuras (`HATCH`) e textos ficam em camadas próprias marcadas; `PaperSpace = 1` descartado com aviso | binário → `dxf_binario`; versão < R12 → `dxf_versao` |
| `dwg` | — (conversão externa, 12.4) | | | | | | `dwg_sem_conversor` até D23 |
| `fgb` | FlatGeobuf | `-oo VERIFY_BUFFERS=YES` | 1 | do cabeçalho (WKT sem código → pergunta) | UTF-8 | FGB sem índice espacial: aceito (o índice é nosso) | buffers inválidos → `formato_invalido` |
| `gml` | GML | `-oo FORCE_SRS_DETECTION=YES`; `.xsd` ao lado usado se existir | 1 por *feature type* | `srsName` (URN EPSG) ou pergunta | UTF-8 | ordem de eixo: `INVERT_AXIS_ORDER_IF_LAT_LONG` padrão; 2 GB (refutação) lê em fluxo (expat) | GML sem esquema e sem geometria detectável → `sem_camadas` |
| `gdb.zip` | OpenFileGDB (leitura direta em `/vsizip/`) | `-oo LIST_ALL_TABLES=NO` | feature classes e tabelas; *feature dataset* vira prefixo do título (`dataset · classe`); nome com espaço normalizado | do dataset | UTF-8 | domínios codificados (`ogrinfo -json` expõe `fieldDomains`) → `plat.dominio` do inquilino (L0-04-f cria a tabela) e `campos[].dominio`; subtipos → campo comum + aviso; anexos (`__ATTACH`) listados em `nao_importado` até L2-03; relacionamentos listados em `nao_importado` até L2-10; raster/mosaico → `nao_importado`; Z/M perguntados | GDB compactada (`.cdf`) → `gdb_compactada` |
| `tab.zip` / `mif.zip` | MapInfo File | `-oo ENCODING=` (nome de campo e dado) | 1 | WKT do `.tab` → pergunta quando sem código (0.2: `unnamed`) | perguntada | — | — |
| `parquet` | — | | | | | **fora desta fase** (10.3) | `formato_nao_suportado_nesta_versao` |
| `zip` genérico | (inspeção lista) | | | | | o zip é classificado pelo conteúdo (3.3) e reencaminhado; misto (shapefile + CSV) vira N importações | nada reconhecido → `sem_camadas` |

### 10.2 Tabela sem geometria

Camada com `geometryFields = []` (XLSX, CSV sem coordenada, `attributes` do GPKG, tabela de GDB) vira item
`tabela` (tipo novo, família `camada`, `dados = {schema, tabela, campos, estatisticas, procedencia}`, sem `geom`,
sem função de tile, `abre_em: tabela`; registrado na 007 com `linha_dona = 'L0-04'`), na mesma `d_<slug>.c_<uuid16>`
com as mesmas colunas obrigatórias menos `geom`. O L2-04 a expõe como *table* do FeatureServer.

### 10.3 GeoParquet: por que fica fora e o que custa entrar

MEDIDO: nem o GDAL do sistema tem o driver, nem `duckdb`/`pyogrio` existem sob a regra da venv (0.1). Entrar exige
uma destas instalações pelo gerente (apt/pip, com `df` antes): (a) `duckdb` na venv (roda de `~/.local`: 1.5.5) com
`INSTALL spatial` (download de extensão, ≈ 60 MB); (b) `pyogrio` (traz GDAL 3.9+ com Parquet dentro da *wheel*,
≈ 90 MB) — que também resolveria a leitura em processo; (c) libgdal com Arrow do PPA. Recomendação para o L0-04-f:
(b), porque é uma dependência só, MIT, e dá `ogr2ogr` equivalente por Python (`pyogrio.write_dataframe` não; usar
`pyogrio.read_arrow` + `COPY` binário — medir). Até lá: `formato_nao_suportado_nesta_versao`, e a exportação para
GeoParquet (L0-04-h) idem.

---

## 11. CSV, TXT e planilhas: o normalizador (`app/ingestao/csv_normalizar.py`)

Por que existe (MEDIDO em 0.2/0.3): o driver CSV do GDAL 3.8.4 aceita `;` e vírgula decimal quando o separador é
`;`, mas (a) não lê separador de milhar (`1.234,5` fica texto), (b) não lê `dd/mm/aaaa` (fica texto; só `aaaa/mm/dd`
vira `Date`), (c) não lê `"12,5"` com separador `,`, (d) engole linhas depois de aspa desbalanceada em silêncio,
(e) não abre `.txt`, (f) desduplica nome com aviso mas sem contrato, (g) não detecta codificação. O normalizador
resolve tudo isso **uma vez**, em Python puro (`csv`, `charset_normalizer`, `re`), em fluxo, e entrega ao GDAL um
CSV canônico: UTF-8 sem BOM, separador `,`, aspas `"`, ponto decimal, datas ISO 8601, cabeçalho normalizado (seção
8), mais um `.csvt` com os tipos confirmados (`Integer, Integer64, Real, String, Date, DateTime, Time`) e, quando há
coordenadas, `X_POSSIBLE_NAMES/Y_POSSIBLE_NAMES` apontando para as colunas escolhidas (mantidas também como campos:
`KEEP_GEOM_COLUMNS=YES`, porque o usuário costuma querer ver lat/lon na tabela).

Proposta (`csv` no JSON da 4.4): `{codificacao, separador ∈ {",", ";", "\t", "|"}, aspas ∈ {'"', "'", null},
cabecalho: true|false|linha n, decimal ∈ {".", ","}, milhar ∈ {null, ".", ",", " "}, formato_data ∈ {"aaaa-mm-dd",
"dd/mm/aaaa", "mm/dd/aaaa", "dd-mm-aaaa", "aaaa/mm/dd"}, coordenadas: {modo ∈ {"xy", "wkt", "nenhuma"}, x, y, wkt,
candidatas: [{nome, faixa, pontuacao}]}, linhas_lidas, linhas_gdal}`. Cada campo tem `origem: detectado|perguntar`.
Ambiguidade `dd/mm` × `mm/dd` (todas as amostras ≤ 12 nos dois lugares) → `perguntar` com sugestão `dd/mm/aaaa`
(`tenant.config.locale = pt-BR`). `linhas_lidas ≠ linhas_gdal` → aviso com as linhas suspeitas.

Planilhas (11.4): `ogr2ogr -f CSV planilha_<n>.csv <arquivo.xlsx> <planilha> -lco SEPARATOR=COMMA` (o driver XLSX
entrega valores calculados, datas como `Date` quando a célula é data e texto quando é texto), e o CSV resultante
passa pelo mesmo normalizador. Uma importação por planilha não vazia. Cabeçalho na linha n (`HEADERS`) é pergunta
quando a 1ª linha tem células vazias ou numéricas.

---

## 12. DXF e DWG (L0-04-e; ativo da casa: `ingest.py`/`georef.py`/`05_importar_dxf.py` do SIG de teste interno, LIDOS)

### 12.1 O que o driver do GDAL dá e o que se escolhe

MEDIDO (0.2): com `DXF_INLINE_BLOCKS=FALSE` cada INSERT vira **ponto** com `BlockName`, `BlockScale [sx,sy,sz]`,
`BlockAngle`, e a camada `blocks` traz as definições; com o padrão (`TRUE`) o bloco é explodido em `MultiLineString`
e o nome se perde. O SIG de teste interno (LIDO em `camadas_do_dxf`/`ler_dxf`) trabalha por *layer* com `ezdxf`,
classifica LWPOLYLINE fechada como polígono e associa TEXT contido/próximo como código. Decisão: driver do GDAL (já
instalado, sem dependência nova) com `DXF_INLINE_BLOCKS=FALSE`, `DXF_CLOSED_LINE_AS_POLYGON=TRUE`,
`DXF_MERGE_BLOCK_GEOMETRIES=TRUE`; **uma camada por *layer* do DXF** (título = nome do layer; layers `0` e `Defpoints`
incluídos só se tiverem entidade); dentro do layer, tipo de geometria misto separado pela regra 4.2-5 (o comum:
`LOTES` com polígonos e linhas → 2 camadas `LOTES · polígonos`, `LOTES · linhas`); textos (`TEXT/MTEXT`) viram
camada de pontos com campo `text`; blocos viram pontos com `blockname/blockscale/blockangle` (a definição do bloco
não é importada, só listada no relatório); `HATCH` vira polígono; `DIMENSION` descartada com aviso; `PaperSpace=1`
descartado com aviso. A associação texto → polígono do SIG de teste interno (código do lote pelo TEXT contido) **não**
entra aqui: é regra de negócio de um cliente, vai para o L5/L2-05 como ferramenta "rotular polígono pelo texto
contido".

### 12.2 Unidade e georreferência: sempre perguntadas

`$INSUNITS` (0 sem unidade, 1 polegada, 2 pé, 4 mm, 5 cm, 6 m — DOC DXF Reference) é lido pela pré-sonda e vira
sugestão; o driver não a expõe (0.2: polegada e metro saem iguais). `$EXTMIN/$EXTMAX` mostram a faixa de coordenadas:
6-7 dígitos → sugestão "já está em UTM, zona pela faixa"; pequenos → "coordenadas locais: georreferenciar". A
proposta traz `dxf: {versao, unidade: {origem, sugestao, perguntar: true}, extent_local, georreferencia: {modo ∈
{"crs", "pontos"}, srid?, pontos?: [{x_local, y_local, x_crs, y_crs}] (2 a 4)}}`. Com `modo = pontos`, a API calcula
Helmert 2D (4 parâmetros: escala, rotação, translação; mínimos quadrados — LIDO em `georef.py::helmert_fit`,
reescrito em `app/ingestao/helmert.py` com `numpy`, presente) e devolve `rmse_m` e resíduo por ponto **antes** da
confirmação (`POST /api/importacoes/{id}/georreferencia` → `200 {parametros, rmse_m, residuos}`); a carga aplica
`ST_Affine` na pós-carga e grava `dados.georreferencia`. RMSE acima de `HELMERT_RMSE_AVISO_M` (2,0 m) é aviso, não
bloqueio. Adversário "DXF em polegada sem declarar": `$INSUNITS = 0` → `unidade.perguntar` com sugestão "metro" e
aviso "o arquivo não declara unidade"; nunca assumido.

### 12.3 DXF que o GDAL não abre

Binário (assinatura, 3.3) → `dxf_binario`; R11/R12 antigo com erro de parse → `formato_invalido` com a linha do
erro do GDAL (0.6 mostrou `error at line 991`); o `ezdxf` **não entra** nesta fase (ausente; e MEDIDO que também
recusa saídas do LibreDWG) — se o L0-04-e medir no corpus da casa que o driver do GDAL falha em > 10 % dos DXF
válidos, `ezdxf` (MIT, puro Python, ≈ 4 MB) entra como leitor de reserva por decisão do gerente, com a mesma proposta.

### 12.4 DWG

Sem conversor nesta máquina (0.1). Caminho desenhado: job `ingestao.converter_dwg` com `executor="gpu"` (ADR 0003
seção 8, gancho já existente) que roda `dwg2dxf -y -o <saida> <entrada>` no GPU box e devolve o DXF para a
inspeção normal — exatamente o `dwg_para_dxf()` do SIG de teste interno (LIDO), agora como job cancelável e com
proveniência. **Não está provado**: MEDIDO em 0.6 que o LibreDWG 0.14 converte DWG↔DXF sem erro (rc 0) mas o DXF
de volta perdeu entidades e não abre em GDAL nem ezdxf, para um DXF de entrada mínimo. O L0-04-e mede com DWG reais
do corpus (654 IFC/DWG/DXF) e, se a taxa de perda passar de 10 %, registra a decisão D23 (ODA File Converter,
binário gratuito com licença própria) como a única saída. Até lá, `dwg` é aceito como **arquivo** (item `arquivo`,
o usuário guarda e baixa) e a inspeção responde `dwg_sem_conversor`: `DWG ainda não é convertido nesta instalação;
exporte como DXF ASCII (R2000 ou superior) no seu CAD`. A versão do DWG (`AC1015` → "AutoCAD 2000") entra na
mensagem (portão: "DWG que o LibreDWG não lê devolve mensagem com a versão").

---

## 13. Atualizar dados (L0-04-g): substituir, acrescentar, acrescentar-e-atualizar

Rota `POST /api/camadas/{id}/atualizar` `{arquivo_id, modo ∈ {substituir, acrescentar, upsert}, chave?: nome do
campo, mapeamento?: [{origem, destino}]}` → inspeção normal do arquivo (mesma proposta) **mais** a comparação de
esquema: `{campos_novos, campos_ausentes, tipos_diferentes: [{nome, de, para}], geometria: {de, para}, srid: {de,
para}}` e `usado_por` da camada (ADR 0004 5.4: mapas/apps afetados). Regras: geometria de tipo diferente → `409
geometria_incompativel` (refutação ponto → polígono); SRID diferente → carga com `-t_srs` **só aqui** (é a única
reprojeção da linha, avisada: `srid_reprojetado`); campo ausente em `substituir` → `409 esquema_divergente {diff}`
salvo `forcar: true` (o usuário viu a lista de dependentes). Execução como job `ingestao.atualizar` (pesado): carrega
em `c_<uuid16>_novo` pelos passos 3-6 da seção 6, copia `globalid` quando `upsert`/`acrescentar` por chave (mantém
identidade das feições), e na transação final: `substituir` → `ALTER TABLE c RENAME TO c_<uuid16>_v<n>; ALTER TABLE
c_novo RENAME TO c; ALTER SEQUENCE …; ALTER FUNCTION tile_…` (atômico; DOC PostgreSQL: DDL transacional), a anterior
fica 30 dias em `d_<slug>` com `COMMENT 'lixeira até <data>'` (o periódico `ingestao.lixeira_tabelas` apaga);
`acrescentar` → `INSERT INTO c SELECT … FROM c_novo` (versão 1, `criado_por`); `upsert` → `INSERT … ON CONFLICT
(<chave>) DO UPDATE` (exige `UNIQUE` na chave: criado se não existir e a chave for única no dado; senão `409
chave_nao_unica {duplicatas}`) com o gatilho de versão incrementando. O item mantém uuid, título, estilo,
compartilhamento e relações; `dados.campos/estatisticas/importacao` são reescritos e `item_versao` grava a versão
(ADR 0004 gatilho). Job morto no meio: a tabela antiga nunca foi tocada antes do `RENAME` transacional (teste de
morte do L0-05 aplicado aqui).

---

## 14. Exportação (L0-04-h): job `ingestao.exportar`

`POST /api/camadas/{id}/exportar` `{formato ∈ {shapefile.zip, gpkg, geojson, geojsonseq, csv, xlsx, kml, kmz, fgb,
gml, dxf}, srid?: int, campos?: [nome], filtro?: CQL2-JSON (L2 C7; até o tradutor existir, só `{"op": "and", …}`
sobre `=`, `<>`, `<`, `>`, `in`, `like` em campos da camada — gramática fechada em `app/ingestao/filtro_simples.py`),
bbox?: [4] em 4326, decimal?: {".", ","}, separador?, codificacao?: {UTF-8, ISO-8859-1}, nome?}` → `202 {job_id}`;
exige `pode_ler` + (`permite_download` do item ou dono ou `conteudo.editar_tudo`) — ADR 0004 6.1 tem a coluna
`permite_download` (padrão `false`, como a Esri); sem ela → `403 exportacao_nao_permitida`. Vista de camada
(L0-04-j): a exportação lê a VIEW, logo o filtro/campos da vista valem sozinhos. O job roda `ogr2ogr -f <driver>
<dir_trabalho>/<nome>.<ext> "PG:…" -sql "<SELECT com campos e filtro traduzido>" [-t_srs EPSG:n] [-lco …]` com o
`-sql` **gerado por nós** (nomes de campo validados contra `dados.campos`; valores por parâmetro literal com
`quote_literal` via `psycopg2.extensions.adapt`; nunca texto do usuário no SQL — refutação "injeta SQL no where"
= `422 filtro_invalido {posicao}`); shapefile: campos truncados a 10 com o mapa devolvido no resultado, `ENCODING`
escolhido, zip com `.cpg`; CSV: `-lco GEOMETRY=AS_XY` para pontos e `AS_WKT` para o resto, `SEPARATOR`, vírgula
decimal por pós-processamento nosso (o driver não escreve vírgula decimal); DXF: um *layer* por valor do campo
escolhido (`camada_por: nome`) ou um só; GeoParquet fora (10.3). Resultado = objeto `exportacao/<item uuid>/
<sha256>.<ext>` + item `arquivo` na pasta do usuário com `dados.expira_em = +7 dias` (periódico `ingestao.
exportacoes_expirar` apaga item e objeto) e `resultado = {item_id, bytes, feicoes}`; download por `GET /api/
arquivos/{id}/conteudo` (L0-11, `X-Accel-Redirect`). Limites: `EXPORTACOES_SIMULTANEAS_POR_USUARIO` = 2 (a 3ª →
`429 exportacoes_demais`), `EXPORTACAO_FEICOES_MAX` = 5.000.000 (acima → `413 exportacao_grande`, o usuário filtra);
disco temporário: o job checa `shutil.disk_usage(dir_trabalho)` ≥ 3× a estimativa antes de começar (`503
disco_insuficiente`, refutação "5 exportações de 5 milhões"). EPSG inexistente → `422 srid_inexistente`.

---

## 15. Vista de camada (L0-04-j) e fonte registrada (L0-04-i): só o que este ADR obriga

Vista: `CREATE VIEW d_<slug>.v_<uuid16> WITH (security_barrier) AS SELECT fid, globalid, versao, tenant_id, <campos
visíveis>, geom FROM d_<slug>.c_<uuid16> WHERE <filtro traduzido>` + função de tile própria; RLS da tabela base já
filtra por inquilino (a VIEW herda porque roda como `plat_app` com `security_barrier`); item `vista_de_camada` (ADR
0004) + relação `vista_de_camada`; 20 por camada (`VISTAS_POR_CAMADA`). Fonte registrada: `postgres_fdw` (instalada)
com `CREATE SERVER` por conexão, credencial no cofre (`pgcrypto`, chave em `PLAT_SECRET`), `IMPORT FOREIGN SCHEMA …
LIMIT TO (…)` para `d_<slug>.f_<uuid16>` e VIEW com `tenant_id` constante por cima para a RLS; hosts proibidos =
`127.0.0.1/8, ::1, <PLAT_DSN host>` (refutação); superusuário recusado por `SELECT rolsuper FROM pg_roles` na
conexão de teste. Ambos têm ADR próprio quando entrarem (o gerente decide); aqui só se garante que a tabela base tem
o que eles precisam (7.1).

---

## 16. Contrato de API (todas exigem sessão S ou token T; erros D18)

| método | rota | privilégio | entrada | resposta | erros |
|---|---|---|---|---|---|
| POST | `/api/uploads` | `conteudo.criar` | `{nome, bytes, tipo_declarado, sha256?}` | `201 {id, parte_bytes, partes, expira_em}` | `413 arquivo_grande` · `413 cota` · `422 tipo_desconhecido` · `422 nome_invalido` |
| PUT | `/api/uploads/{id}/partes/{n}` | dono do upload | corpo bruto | `200 {n, recebidas, faltam}` | `404` · `413 parte_grande` · `409 concluido` · `410 upload_expirado` · `422 parte_sha256_divergente` |
| GET | `/api/uploads/{id}` | dono | | `200 {id, nome, bytes, recebidas, faltam, estado, expira_em}` | `404` |
| POST | `/api/uploads/{id}/concluir` | dono | `{inspecionar?: true, pasta_id?}` | `202 {arquivo_id, item_id, importacao_ids, job_id}` | `409 partes_faltando {faltam}` · `422 sha256_divergente` · `422 tamanho_divergente` · `422 conteudo_nao_corresponde` · `422 zip_suspeito` · `422 zip_caminho_invalido` · `422 zip_aninhado` |
| DELETE | `/api/uploads/{id}` | dono | | `204` | `404` |
| POST | `/api/importacoes` | `conteudo.publicar_camada` | `{arquivo_id}` (reinspecionar arquivo já guardado) | `202 {importacao_ids, job_id}` | `404` · `409 inspecao_em_curso` |
| GET | `/api/importacoes` | próprias (`jobs.gerir_todos` vê todas) | `estado, arquivo_id, grupo_id, limite, deslocamento` | `200 {itens, total}` | |
| GET | `/api/importacoes/{id}` | dono | | `200 importacao` (estado, proposta, confirmacao, relatorio, job_id, item_id, erro) | `404` |
| PUT | `/api/importacoes/{id}/confirmar` | `conteudo.publicar_camada` | proposta editada (seção 5) | `202 {job_id}` | `422 perguntas_pendentes {perguntas}` · `422 campo_desconhecido` · `422 tipo_nao_permitido` · `422 srid_inexistente` · `422 nome_colide` · `409 estado_invalido` · `410 proposta_expirada` · `413 cota` |
| PUT | `/api/importacoes/grupo/{grupo_id}/confirmar` | idem | `{importacoes: [{id, …}]}` | `202 {jobs: [...]}` | idem, por item em `detalhe` |
| POST | `/api/importacoes/{id}/georreferencia` | dono | `{pontos: [{x_local, y_local, x_crs, y_crs}], srid}` | `200 {parametros, rmse_m, residuos}` | `422 pontos_insuficientes` (< 2) · `422 pontos_colineares` |
| POST | `/api/importacoes/{id}/cancelar` | dono | | `202` (cancela o job em curso) | `409 estado_final` |
| DELETE | `/api/importacoes/{id}` | dono | | `204` (só `proposta/falhou/cancelada/expirada`) | `409` |
| GET | `/api/crs` | S/T | `q` | `200 [{srid, nome, tipo: geografico|projetado, unidade}]` ≤ 20 | |
| GET | `/api/camadas/{id}/campos` | `pode_ler` | | `200 [{nome, alias, tipo, nome_original, dominio?}]` | `404` |
| GET | `/api/camadas/{id}/estatisticas` | `pode_ler` | `recalcular?` (job) | `200 dados.estatisticas` | |
| GET | `/api/camadas/{id}/feicoes` | `pode_ler` / T `camada:ler[:id]` | `limite (≤ 1.000), deslocamento, campos, bbox, ordenar, formato ∈ {json, geojson}` | `200 {total, feicoes}` (a **aba tabela** da camada; o FeatureServer do L2-04 substitui para clientes Esri) | `422` |
| POST | `/api/camadas/{id}/atualizar` | `pode_editar` | seção 13 | `202 {importacao_id, job_id}` | `409 geometria_incompativel` · `409 esquema_divergente {diff, usado_por}` · `409 chave_nao_unica` |
| POST | `/api/camadas/{id}/exportar` | `pode_ler` + download | seção 14 | `202 {job_id}` | `403 exportacao_nao_permitida` · `422 filtro_invalido` · `422 srid_inexistente` · `429 exportacoes_demais` · `413 exportacao_grande` |
| GET | `/api/importacoes/formatos` | S/T | | `200 [{tipo, extensoes, rotulo, limites, avisos}]` (a tabela 10.1 em JSON, gerada de `app/ingestao/formatos.py`) | |

Páginas: `GET /conteudo/novo/arquivo` (assistente), `GET /importacoes/{id}` (acompanhamento), aba "Dados" em
`/conteudo/{id}` (ADR 0004 15.2 já a prevê: "tabela de atributos (L0-04)").

---

## 17. Telas (wireframe em texto; estilo `web/style.css`; módulos ES ≤ 60 kB; `web/js/ingestao/*.js`)

### 17.1 `/conteudo/novo/arquivo` — assistente em 4 passos (`assistente.js`, `upload.js`, `proposta.js`, `campos.js`)

```
┌ Novo item › Arquivo ──────────────────────────────────────────────────────────────────────────────────────┐
│ ① Enviar ─── ② Inspecionar ─── ③ Confirmar ─── ④ Importar                                                 │
│                                                                                                             │
│ ① [ arraste o arquivo ou clique ]   tipos aceitos: shapefile (.zip), GeoPackage, GeoJSON, KML/KMZ, CSV…    │
│    municipios_se.zip · 157 kB · shapefile (zip)   ████████████████████░░░░ 84 %  parte 6 de 7  [cancelar]  │
│    cota: 1,2 GB de 20 GB usados                                                                             │
│ ② inspecionando… (job 3f9a…, 2 s)  ✓ 1 camada encontrada                                                   │
│ ③ Camada "municipios" ─────────────────────────────────────────────────────────────────────────────────── │
│    Título [Municípios de teste           ]   Pasta [raiz ▾]   Tags [                  ]                    │
│    Geometria: MultiPolygon (75 feições, 1 inválida → ◉ corrigir ○ descartar ○ recusar)  Z: —              │
│    CRS: ⚠ o arquivo não tem .prj  →  [EPSG:4674 SIRGAS 2000 ▾ ▸ buscar…]  (sugestão pelo extent, em graus) │
│    Codificação: UTF-8 (.cpg)                                                                               │
│    Campos (5):  original        │ nome na tabela │ tipo            │ exemplo    │ importar                  │
│                 Código IBGE     │ codigo_ibge    │ [text ▾]        │ 2800100    │ ☑                         │
│                 Área km²        │ area_km2       │ [double ▾]      │ 95,40      │ ☑                         │
│                 select          │ select_ ⓘ      │ [text ▾]        │ SELECT     │ ☑                         │
│    Avisos: nome "select" é reservado e foi renomeado · campo "Município" duplicado → municipio_2            │
│    Pendências (1): escolher o CRS                                                          [Importar]▒▒▒   │
│ ④ importando… ████████░░ 60 % ST_MakeValid (1 corrigida)     → [abrir a camada] [ver relatório]             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Progresso por SSE do job (ADR 0003 seção 5); o botão "Importar" só ativa com `perguntas = []`; múltiplas camadas
viram abas em ③ com "confirmar todas". `blocos`/`unidade`/`georreferência` aparecem só para DXF (mapa pequeno com
os pontos de controle e RMSE). CSV mostra prévia das 10 primeiras linhas com o separador/decimal aplicados.

### 17.2 `/conteudo/{id}` aba "Dados" (`camada_dados.js`, `tabela.js`)

Tabela paginada (`/api/camadas/{id}/feicoes`), cabeçalho com alias e tipo, ordenação por coluna, filtro por bbox
do mapa (quando aberta ao lado do mapa do L2-01), estatísticas por campo em painel lateral, botões "Atualizar
dados" (13, abre o assistente no modo comparação de esquema com a lista de dependentes) e "Exportar" (14, diálogo
com formato/CRS/campos/filtro simples), relatório da importação (6.5) com os fids corrigidos.

### 17.3 `/importacoes` e `/importacoes/{id}` (`importacoes.js`)

Lista das importações do usuário (estado, arquivo, camada, quando, ações) e detalhe = a proposta em leitura +
relatório + link para o job.

---

## 18. Limites (`app/limites.py`, seção `# --- ingestão (L0-04)`; `docs/LIMITES.md` do L0-12)

| constante | valor | origem |
|---|---|---|
| `UPLOAD_BYTES_MAX` · `UPLOAD_PARTE_BYTES` · `UPLOAD_EXPIRA_HORAS` | 2 GiB · 16 MiB · 24 | L0-04-a (Esri aceita 500 GB; ampliar = 2 números) |
| `ZIP_ENTRADAS_MAX` · `ZIP_DESCOMPRIMIDO_MAX` · `ZIP_RAZAO_MAX` · `ZIP_NOME_MAX` | 1.000 · 8 GiB · 100 · 255 | 3.2 |
| `FEICAO_BYTES_MAX` · `KML_BYTES_MAX` | 16 MiB · 64 MiB | 0.4 (MEDIDO / declarado) |
| `INSPECAO_AMOSTRA` · `INSPECAO_MEMORIA_MB` · `INSPECAO_TIMEOUT_S` | 1.000 · 768 · 300 | 4 |
| `CARGA_MEMORIA_MB` · `CARGA_TIMEOUT_S` · `CARGA_FATOR_COTA` | 1.024 · 3.600 · 3 | 6 (MEDIDO 0.3) |
| `PROPOSTA_EXPIRA_HORAS` | 24 | 2.1 |
| `CAMPOS_MAX` · `CSV_COLUNAS_MAX` · `NOME_BYTES_MAX` | 500 · 500 · 63 | ADR 0004 esquema; PostgreSQL |
| `DXF_ENTIDADES_MAX` · `HELMERT_PONTOS_MIN/MAX` · `HELMERT_RMSE_AVISO_M` | 2.000.000 · 2/4 · 2,0 | 12 |
| `FIDS_RELATORIO_MAX` | 1.000 | 6.5 |
| `FID_MAX` | 2.147.483.647 | C4 |
| `VISTAS_POR_CAMADA` | 20 | Esri, L0-04-j |
| `EXPORTACOES_SIMULTANEAS_POR_USUARIO` · `EXPORTACAO_FEICOES_MAX` · `EXPORTACAO_EXPIRA_DIAS` | 2 · 5.000.000 · 7 | 14 |
| `TABELA_LIXEIRA_DIAS` | 30 | 13 |
| `FEICOES_PAGINA_MAX` | 1.000 | 16 |

---

## 19. Testes obrigatórios e dado de teste (`tests/dados/`)

### 19.1 Gerador `tests/dados/gerar.py` (dado aberto, ≤ 5 MB no total, comitado o **gerador**, não os arquivos)

Roda no `make check` antes da suíte (alvo `dados`): sem rede, sem banco, a partir de **um** GeoJSON de semente
comitado (`semente_municipios.geojson`, 583 kB, malha municipal de uma UF do IBGE simplificada — dado aberto, sem
nome de cliente; a UF não é nomeada no título do item de teste) e de geometria sintética. Gera, com `ogr2ogr` e
Python, os arquivos da tabela abaixo em `tests/dados/gerados/` (no `.gitignore`). É o `gerar.sh` da medição
(Anexo A) reescrito em Python, com as linhas do DNIT/DECEA substituídas por linhas/pontos sintéticos (para não
depender do banco).

| arquivo | serve a | fixture esperada (`tests/dados/esperado/<arquivo>.json`) |
|---|---|---|
| `municipios_shp.zip` | shapefile utf-8 | 75 · MultiPolygon · 4326 · 5 campos, `select`→`select_` |
| `municipios_semprj.zip` | **sem .prj** | `crs.perguntar = true`, sugestão 4674 |
| `municipios_latin1_semcpg.zip` | latin-1 sem .cpg | `codificacao.perguntar = true`; com `ISO-8859-1`, nome `Aracaju` presente |
| `dois_shapefiles.zip` | N camadas | 2 importações no mesmo `grupo_id` |
| `dados.gpkg` | 3 camadas, `MultiLineStringZ` 4674 | Z perguntado; srid 4674 preservado |
| `pastas.kmz` | pastas → camadas | 3 camadas, 4326, estilo descartado (aviso) |
| `municipios.gml` | GML 3.2 (com nomes normalizados) | 75 |
| `linhas.fgb` | FlatGeobuf | 4674 |
| `pontos.geojsonl` | GeoJSONSeq | |
| `municipios_31984.geojson` | `crs` legado | srid 31984 + aviso |
| `misto.geojson` | ponto+polígono | `geometria.perguntar = true` |
| `gravata.geojson` | auto-intersecção + anel aberto | `invalidas = 1`; após carga `corrigidas = 1`, `MultiPolygon` 2 partes, área 0,005 |
| `feicao_grande.geojson` (gerado na hora, 20 MB, 1 feição) | recusa | `feicao_grande` |
| `pontos_pv.csv` | `;` + vírgula decimal + BOM + `lat/long` | `Real`, Point, `crs.perguntar` |
| `milhar.csv` | `1.234,5`, `dd/mm/aaaa` | após normalizador: `1234.5`, `2024-02-08` |
| `pontos_wkt.csv` | WKT | Geometry |
| `tabela.txt` | tabulação, latin-1, sem coordenada | item `tabela` |
| `csv_300col_0lin.csv` · `csv_aspas.csv` · `csv_dup.csv` | adversário | 300 campos/0 linhas aceito; `csv_aspas` recusado com linha; `municipio_2` |
| `planilha.xlsx` | 2 planilhas | 2 importações; `Date` |
| `trilha.gpx` | waypoints/tracks | 2 camadas |
| `blocos.dxf` (escrito à mão pelo gerador, com subclasse `AcDbPolyline`) · `linhas.dxf` (via `ogr2ogr -f DXF`) · `polegada.dxf` · `binario.dxf` | DXF | blocos = 3 pontos `blockname=ARVORE`; unidade perguntada; binário recusado |
| `controle.gpkg` | nome de camada com `\x01` | título `mun_icipios` |
| `sint100k.gpkg` (gerado na hora, 37 MB, apagado depois) | portão 60 s | `tempo_import_100k_s` |
| `gdb.zip` · `tab.zip` | L0-04-f | gerados por `ogr2ogr -f OpenFileGDB` / `-f "MapInfo File"` (o GDAL escreve os dois) |

### 19.2 Suíte (o testador roda a inteira; o adversário repete sem ler os handoffs 30/31)

`tests/unit/test_nomes.py` (tabela da seção 8), `test_csv_normalizar.py`, `test_helmert.py`, `test_formatos.py`
(3.3: tipo × bytes para cada arquivo gerado e para 5 forjados), `test_zip.py` (bomba com 1 milhão de entradas
gerada em memória, `../`, aninhado, symlink); `tests/api/ingestao/test_upload.py` (100 MB em 7 partes com a 4ª
reenviada, sha256 igual; `.gpkg` com zip dentro → `conteudo_nao_corresponde`; 21 GiB declarado com cota 20 → 413
antes de byte; upload de outro usuário → 404; expiração pelo periódico com `PLAT_RELOGIO_TESTE`),
`test_inspecao.py` (cada arquivo → fixture; `tempo_inspecao_s` por arquivo; nenhum `pg_tables` novo em `d_%` durante
a inspeção), `test_confirmar.py` (perguntas pendentes; nomes; tipos), `test_carga.py` (100 mil ≤ 60 s medido em
`tests/medidas/L0-04-ingest-vetor.json` como `tempo_import_100k_s`; `relrowsecurity AND relforcerowsecurity`;
`plat_app` sem contexto vê 0 linhas; `plat_leitor` idem; estatísticas = `COUNT(*)`/`ST_Extent`; `select_`;
`municipio`; cota excedida sem tabela; cancelamento no passo 3 → 0 tabela órfã; 2 importações paralelas do mesmo
arquivo; CRS mentido → aviso e extent NULL), `test_orfaos.py` (invariante 6.2-9 após matar o worker com SIGKILL no
meio — reuso de `tests/jobs_sessao.py`), `test_formatos_carga.py` (cada arquivo da 19.1 importa ou recusa com a
mensagem exata da tabela 4.3/10.1 — a refutação do item pai), `test_atualizar.py`, `test_exportar.py` (10 formatos
reabertos por `ogrinfo` com a mesma contagem; `where` com injeção → 422; EPSG inexistente → 422; 5 exportações
paralelas → 429 na 3ª), `test_tile.py` (função de tile vazia sem contexto, cheia com); `tests/e2e/test_ingestao.py`
(um fluxo por formato com captura `L0-04-ingest-vetor_<formato>.png`; 0 erro de console; barra de progresso do
upload; pergunta de CRS respondida; relatório visível). Medidas gravadas: `taxa_upload_mb_s`, `tempo_inspecao_s`
(por arquivo), `tempo_import_100k_s`, `tempo_makevalid_100k_s`, `rss_ogr2ogr_mb`, `tempo_export_<formato>_s`.

---

## 20. Migração `007_ingestao.sql`, colisões e consequências

### 20.1 Ordem normativa (idempotente; sem BEGIN/COMMIT; aplicada como `postgres`)

```
20.1  DO $$ CREATE ROLE plat_leitor NOLOGIN $$ (se não existir); GRANT USAGE ON SCHEMA plat TO plat_leitor
20.2  plat.upload (id uuid, tenant_id, usuario_id, nome, bytes, tipo_declarado, sha256_declarado, chave_multipart, estado
      ∈ {iniciado, concluido, abortado, expirado}, partes int, recebidas int, criado_em, expira_em, concluido_em) + RLS;
      plat.upload_parte (upload_id, n, bytes, etag, sha256, recebida_em, PK(upload_id, n)) + RLS por join
20.3  plat.importacao (id uuid, tenant_id, usuario_id, arquivo_id uuid → item, grupo_id uuid, camada_origem text, camada_indice
      int, estado (2.1), proposta jsonb, confirmacao jsonb, relatorio jsonb, item_id uuid, job_inspecao uuid, job_carga uuid,
      erro text, criado_em, atualizado_em, expira_em) + RLS + gatilho estado_final_imutavel + índice (tenant_id, estado)
20.4  ALTER TABLE plat.tenant ADD COLUMN IF NOT EXISTS uso_bytes bigint NOT NULL DEFAULT 0, ADD COLUMN IF NOT EXISTS
      uso_reservado_bytes bigint NOT NULL DEFAULT 0   -- D16; o L0-07-c mede e reconcilia
20.5  funções: plat.feicao_versao(), plat.feicao_inserir() (gatilhos), plat.camada_preparar(schema, tabela, srid, tipo,
      usuario) SECURITY DEFINER, plat.camada_tile_criar(schema, tabela, srid, campos text[]), plat.camada_apagar(schema,
      tabela) (chamada pelo destruidor do ADR 0004 9.1), plat.contexto_por_token(text) stub (7.3), plat.cota_reservar(tenant,
      bytes) / cota_liberar / cota_confirmar (FOR UPDATE)
20.6  tipo_item: UPDATE camada_vetorial (esquema v2, 7.4); INSERT tabela (10.2) ON CONFLICT DO UPDATE
20.7  evento_tipo: camadas/importar, camadas/atualizar, camadas/exportar, uploads/concluir, sistema/orfaos
20.8  plat.tenant_criar: CREATE SCHEMA d_<slug> AUTHORIZATION plat_app + GRANT USAGE TO plat_leitor (CREATE OR REPLACE)
20.9  REVOKE EXECUTE … FROM PUBLIC; GRANT … TO plat_app (repetido)
```

Se a numeração `007` colidir com o que a trilha do L0-03 ou o L0-11 publicarem primeiro, esta vira `008` sem outra
mudança (regra do ADR 0004 18).

### 20.2 Dependências e colisões com as trilhas em curso (T2: A = L0-02, B = L0-05) e com o ADR 0004

| com quem | onde | como se resolve |
|---|---|---|
| **B (L0-05)** — `ctx.subprocesso` bufferiza a saída (LIDO em `contexto_job.py` 121-150: `communicate` em laço de 0,25 s) | progresso do `ogr2ogr -progress` só no fim | pedir ao L0-05 (ou fazer aqui, em `app/ingestao/subprocesso.py`, sem editar `app/jobs/`) um `subprocesso_stream(argv, ao_ler=callable)` que leia stdout linha a linha e chame `ctx.progresso`; até lá, o progresso do passo 3 é "0 → 100" em bloco e os outros 8 passos dão a granularidade |
| B — `PLAT_JOBS_DIR` e `memoria_mb ≤ PLAT_WORKER_MEMORIA_MB` (1.536 no `.env.exemplo`) | `ingestao.carregar` pede 1.024 e é pesado | cabe; `MemoryMax=2G` da unidade cobre 1 filho pesado |
| B — `executor="gpu"` para o DWG | ADR 0003 seção 8 é gancho, sem implementação | `ingestao.converter_dwg` fica declarado e **desligado** (não registrado) até o L1-05 implementar o executor; a rota responde `dwg_sem_conversor` |
| **A (L0-02)** — privilégios `conteudo.publicar_camada` e escopos `camada:ler:<uuid>` | rotas deste ADR | já semeados na 003; nada a pedir |
| **ADR 0004** — `plat.item` com `id` fornecido no INSERT; `tg_item_imutaveis` | 4.4 | conferir na integração que o gatilho só proíbe UPDATE de `id/tenant_id/tipo`; se proibir INSERT com id, trocar por "item criado primeiro, `nome_tabela` derivado depois" (custo: mover 1 passo) |
| ADR 0004 — esquema `camada_vetorial` com `additionalProperties: false` | 7.4 acrescenta chaves | a 007 atualiza a linha de `tipo_item` (esquema v2) — o ADR 0004 3.3 prevê |
| ADR 0004 — destruidor `camada_vetorial → DROP TABLE` (9.1) | tabela + função de tile + sequência | o destruidor chama `plat.camada_apagar(schema, tabela)` desta migração (que apaga tabela, função e VIEWs dependentes com `409` se houver vista) |
| ADR 0004 — `tamanho_bytes` do item | cota | a carga grava `pg_total_relation_size`; o L0-07-c recalcula diariamente |
| ADR 0004 — miniatura por job | fim da carga | `catalogo.miniatura(item_id)` enfileirado no passo 8 |
| **L0-11** (não iniciado) | cliente de objetos + `plat.arquivo` + multipart | este ADR usa o contrato 11.3 do ADR 0004 **estendido** com `parte_iniciar(chave) -> upload_s3_id`, `parte_enviar(upload_s3_id, n, stream) -> etag`, `parte_concluir(upload_s3_id, etags) -> {chave, bytes}`, `parte_abortar`, `ler_intervalo(chave, inicio, fim)` (para o cabeçalho central do zip), `url_assinada(chave, s)`; enquanto o L0-11 não existir, o mesmo adaptador local do ADR 0004 (`objetos_local.py`) ganha essas funções sobre disco (`PLAT_DADOS_DIR/arquivos/…`), com os mesmos testes — é armazenamento real, não casca |
| **L0-12** (contrato de API) | erros/paginação | seguido como está em `app/erros.py`; `docs/LIMITES.md` lê a seção 18 |
| L2-01-b (Martin) · L2-04 | função de tile, `plat_leitor`, `contexto_por_token` | criados aqui como o C3/C18 obrigam; o stub de contexto é substituído pela função real do L2-04-a sem tocar nas funções de tile |
| L2-03-d (histórico por feição) | gatilho nas `c_*` | não é criado aqui (7.1 nota 3) |

### 20.3 Consequências e o que custa mudar

| decisão | custo de reverter |
|---|---|
| inspeção → confirmação → carga (nada antes da confirmação) | nenhum: é contrato de interface; o motor por trás muda sem tocar na tela (D11) |
| `ogr2ogr` como neto com `RLIMIT_DATA` | trocar por `pyogrio`/`fiona` em processo = reescrever `carregar.py` passo 3 e medir memória de novo; o resto fica |
| `-nlt` explícito + `-sql AS` na carga | nenhum |
| tabela `c_<uuid16>` com as 9 colunas obrigatórias e `FORCE RLS` | muito alto (D3/C4): toda linha depende; por isso vem completa desde a 1ª camada |
| normalização de nomes nossa | baixo (função pura); mudar a regra exige migrar `dados.campos` dos itens existentes |
| CSV por normalizador próprio | baixo: se um GDAL futuro ler milhar/`dd/mm`, o normalizador vira passagem direta |
| DXF por driver do GDAL | médio: `ezdxf` como reserva já desenhado (12.3) |
| DWG desligado até prova | nenhum: rota e job já desenhados; ligar = registrar o tipo depois da medição |
| Parquet fora | baixo: `pyogrio` na venv (10.3) |
| upload em partes pela API (sem `multipart/form-data`) | nenhum: `python-multipart` pode entrar depois para o caso simples (< 16 MiB em 1 pedido) |
| `FEICAO_BYTES_MAX` 16 MiB | um número em `limites.py`, refeito quando `memoria_mb` mudar |

---

## Anexo A — medições (comandos literais; 05/09/2026; scratchpad `adr0005/`, apagado no fim; schema `adr0005_tmp` apagado: `pg_namespace` = 0)

A.1 Fonte aberta exportada por `/vsistdout/` (o único jeito de escrever GeoJSON como `postgres` num diretório do usuário):
`sudo -u postgres ogr2ogr -f GeoJSON /vsistdout/ 'PG:dbname=iagro_sat' -sql "SELECT cd_ibge AS \"Código IBGE\", nm AS \"Município\", cd_uf AS uf, ST_Area(geom::geography)/1e6 AS \"Área km²\", 'SELECT' AS \"select\", ST_SimplifyPreserveTopology(geom,0.0005) AS geom FROM tribuna_serving.municipio_geo WHERE cd_uf='28'" -nln municipios > municipios.geojson` (583 kB, 75 feições); ferrovias (`public.amc_dnit_ferrovias`, 107) e heliportos (`public.amc_decea_heliportos`, 239) por `ST_Intersects` com `ST_Transform(ST_Union(geom),4674)` (o primeiro erro foi `mixed SRID 4674 × 4326`: as tabelas do acervo estão em CRS distintos — a regra "CRS explícito em toda comparação" vale também para gerar dado de teste). `/vsistdout/` **não** funciona para GPKG nem FGB (`Read or update mode not supported`).

A.2 `gerar.sh` (derivação dos 30 arquivos; log em `medicoes/gerar.log`), `inspecionar.py` (`ogrinfo -ro -json -so` com cronômetro; `medicoes/inspecao*.log`), `carregar.sh` (`/usr/bin/time -f "TEMPO %e s RSS %M kB" ogr2ogr -f PostgreSQL "PG:$PLAT_DSN" …` como `plat_app`; `medicoes/carga.log`). Cópias em `laco/handoffs/T2/preparacao/L0-04-ingest-vetor/medicoes/`.

A.3 Sintético: `sudo -u postgres ogr2ogr -f GeoJSONSeq /vsistdout/ 'PG:dbname=iagro_sat' -sql "SELECT i AS id, 'feicao '||i AS nome, (i%97)::int AS classe, random()*1000 AS valor, (now()-(i||' minutes')::interval)::date AS data, (i%2=0) AS ativo, md5(i::text) AS hash, 'Município '||(i%5570) AS municipio, ST_Buffer(ST_SetSRID(ST_MakePoint(-45+random()*10, -15+random()*8),4674), 0.002, 'quad_segs=2') AS geom FROM generate_series(1,100000) i" > sint100k.geojsonl` (55,5 MB em 2,32 s) → GPKG 37 MB (2,10 s), shapefile zipado 14 MB (2,38 s), GeoJSON 55,6 MB.

A.4 Memória: `prlimit --data=<bytes> <comando>` com `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` exportados (sem elas: 9 execuções travadas, rc 124 por `timeout`, RSS ≈ 40 MB — a armadilha do ADR 0003 4.3). Feição gigante gerada por Python (`n` vértices num círculo de raio 0,5°: 2 mi → 51 MB; 10 mi → 255 MB).

A.5 Pós-carga (como `plat_app`, `\timing on`): `SELECT count(*) FILTER (WHERE NOT ST_IsValid(geom)) …` 190 ms; `UPDATE … ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_ReducePrecision(geom,1e-9)),3)) WHERE NOT ST_IsValid(geom) OR ST_NPoints(geom) <> ST_NPoints(ST_ReducePrecision(geom,1e-9))` 1.631 ms (0 linhas alteradas: o sintético é válido); `ALTER TABLE … ADD COLUMN globalid uuid NOT NULL DEFAULT gen_random_uuid(), versao int NOT NULL DEFAULT 1, tenant_id int NOT NULL DEFAULT 1, criado_em, atualizado_em, criado_por, atualizado_por` 2.321 ms; `UNIQUE (globalid)` 343 ms; `CREATE INDEX … gist (geom)` 750 ms; `ANALYZE` 262 ms; estatísticas 66 ms; `pg_total_relation_size` 45 MB.

A.6 DWG (GPU box): `dxf2dwg -y --as r2000 -o adr0005_r2000.dwg adr0005_blocos.dxf` rc 0 (1.221 B); `--as r2018` rc 0 (302.714 B); `dwg2dxf -y -o …_volta.dxf …dwg` rc 0; `ogrinfo` na volta: `error at line 991` / `1203`; `ezdxf.readfile` (venv do SIG de teste interno, só leitura): `DXFStructureError: missing ENDSEC tag`; `file`: "DWG AutoDesk AutoCAD 2000" / "2018/2019/2020". Arquivos apagados de `/tmp` do GPU box.

A.7 URLs: nenhuma consultada por HTTP neste ADR; toda referência a documentação é ao GDAL 3.8.4 instalado (`ogrinfo --format`, `--formats`, `--version`) e ao PostGIS 3.6.3 local. As URLs dos itens no `estado.json` (gdal.org, enterprise.arcgis.com) ficam para o papel `esri`/`pesquisador` do turno de construção.
