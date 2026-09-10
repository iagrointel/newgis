# ADR 0018 — Exportação de camada para outros formatos

Item `L0-04-h-exportar` (linha L0, fundação). Estado: aceito, implementado em 06/09/2026.
Numeração: 0014 e 0017 já estavam em uso em outras trilhas desta mesma sessão; o próximo livre é 0018.

## Contexto

A plataforma já ingere dado vetorial (ADR 0005) e o guarda como tabela PostGIS por inquilino
(`d_<slug>.c_<uuid16>`). Faltava o caminho de volta: tirar aquele dado da plataforma no formato que o
cliente usa. Na Esri esse recurso é "Export Data" do item hospedado, com uma opção do dono ("Allow others
to export to different formats") desligada por padrão.

Exportação mexe com dado de cliente e cria um arquivo que sai da plataforma. Duas perguntas mandam no
desenho: **a exportação de um inquilino pode trazer linha de outro?** e **um arquivo grande derruba a
máquina?** (a casa já derrubou o Postgres uma vez, em 30/08/2026, com processos que seguraram tudo em RAM).

## Decisão

### 1. Job, nunca requisição síncrona

`POST /api/exportacoes` valida tudo e enfileira `exportacao.gerar` (202 com `exportacao_id` e `job_id`).
O arquivo nasce no diretório de trabalho do job, vai ao Garage e vira um item `arquivo` na pasta do usuário,
com validade de 7 dias (`plat.exportacao.expira_em`); o periódico `exportacao.expirar` apaga o objeto e o
item quando a validade vence e deixa a linha como `expirada` (o registro de quem exportou o quê fica: é
auditoria).

### 2. A RLS do PostgreSQL vale DENTRO do ogr2ogr

O `ogr2ogr` abre conexão própria, fora do pool da aplicação, então o `set_config('plat.tenant_id', …)` do
`app/db.py` não o alcança. A tentação seria acrescentar um `WHERE tenant_id = …` escrito por nós — que um
erro de programação apagaria em silêncio. Em vez disso, o inquilino entra na PRÓPRIA string de conexão:

    PG:dbname=… user=… options='-c plat.tenant_id=7 -c plat.usuario_id=12'

e a política de RLS da tabela de camada (criada por `plat.camada_preparar`, ADR 0005) faz o corte.

**Medido em 06/09/2026** (tabela com 50 mil linhas de cada um de dois inquilinos, mesma consulta):
sem a opção, o ogr2ogr exporta **0 feição**; com `-c plat.tenant_id=<A>`, exatamente as 50 mil de A.
`tests/api/exportacao/test_exportacao_cruzado.py` repete essa medida em três níveis (API, job com pedido
forjado no banco, e o ogr2ogr direto).

### 3. Nada do cliente entra no texto do SQL

O filtro passa por `app/consulta/where_ast.py` (lista branca de colunas vinda do ITEM, todo literal vira
parâmetro) e só então por `cursor.mogrify`, que escreve o literal com o escape do libpq. O `-sql` do ogr2ogr
exige um comando pronto (não aceita parâmetro); `mogrify` é o único jeito de produzir esse texto sem
concatenar string de usuário. Nome de schema, de tabela e de coluna nunca vêm do corpo do pedido: saem do
item de catálogo lido sob RLS.

### 4. O erro do banco vai ao cliente, saneado

Filtro que o parser aceita mas o banco recusa (tipo incompatível, por exemplo) é conferido com um
`SELECT 1 FROM (<consulta>) LIMIT 0` ANTES de criar o job, e volta como 400. A mensagem é montada a partir
de UM campo conhecido (`diag.message_primary`), com o nome interno da tabela, o comando, a posição e os
caminhos de arquivo retirados (`app/exportacao/erros.py`) — lista de permissão, não de bloqueio.

### 5. Onze formatos; dois deles não pelo caminho óbvio

`gpkg · geojson · shapefile(zip) · csv · xlsx · kml · kmz · fgb · gml · dxf · geoparquet`.

- **KML pelo driver `KML`, não `LIBKML`.** Medido: LIBKML consumiu 3,5 min de CPU e 255 MB de RSS para
  50 mil pontos SEM terminar; o driver `KML` fez o mesmo recorte em 0,34 s com 56 MB. KMZ é o zip do KML.
- **GeoParquet pelo DuckDB, num processo próprio.** O GDAL 3.8.4 desta máquina não tem driver Parquet; o
  ogr2ogr escreve um GPKG intermediário e o DuckDB (extensão `spatial`) copia para Parquet, com o metadado
  `geo` da especificação GeoParquet 1.0.0. É o único formato que o `ogrinfo` desta instalação não reabre — o
  teste do portão o reabre com o DuckDB, e isso está dito no catálogo de formatos e aqui.
  O DuckDB **não é seguro depois de um `fork`**, e o filho que roda um job é um fork do worker: MEDIDO em
  06/09/2026, a mesma conversão que leva 0,17 s num processo normal mata o processo forkado com
  `terminate called without an active exception` (SIGABRT), com `threads=1` e com `threads=2`, antes de
  escrever um byte. Por isso a conversão virou `python -m app.exportacao.parquet_cli`, um `exec` limpo
  rodado como neto pelo mesmo `ctx.subprocesso` que já roda o ogr2ogr (herda o `RLIMIT_DATA` do job e morre
  com o cancelamento). Dependência nova: `duckdb==1.5.5` em `requirements.txt` (21,5 MB); a extensão
  `spatial` vem do cache local `~/.duckdb/extensions` do usuário que roda o worker — sem esse cache e sem
  rede, só o GeoParquet falha, com mensagem própria, e os outros dez formatos seguem funcionando.
- **DXF não guarda atributo** (o driver recusa criar campo); **CSV e XLSX não guardam geometria** (o CSV
  ganha colunas X/Y ou WKT). São limites do FORMATO, declarados em `GET /api/exportacoes/formatos`.

### 6. CSV brasileiro é reescrita nossa, uma linha por vez

O driver CSV do GDAL só escreve ponto decimal e chama as colunas de coordenada de `X`/`Y`. Quem abre o
arquivo no Excel em português precisa de `;` e `,`. A reescrita (`app/exportacao/csv_saida.py`) passa
`csv.reader` → `csv.writer` linha a linha e troca o ponto só em campo que é um número inteiro-com-decimal
(um texto com ponto, uma data, um `1.2.3` nunca são tocados), depois `os.replace`.

### 7. Duas trancas para exportar o que é de outro

`conteudo.exportar` (privilégio novo, perfis editor e admin) **e** ser dono do item, ou ser admin
(`conteudo.ver_tudo`/`editar_tudo`), ou o dono ter ligado `dados.exportacao.permitir_outros` — que nasce
desligado. Entre inquilinos a resposta é 404, não 403: confirmar a existência do item alheio já seria
vazamento.

### 8. Limites que existem porque a máquina é pequena

`EXPORTACAO_POR_USUARIO_EM_CURSO = 3` (a refutação do item manda 5 em paralelo: as duas últimas tomam 429)
e uma guarda de disco medida com `shutil.disk_usage` ANTES do primeiro byte (`estimativa = tamanho da
tabela × 3` mais 2 GiB de folga). O disco desta máquina está a 98 %.

## Consequências

- Toda exportação é rastreável: `plat.exportacao` guarda formato, filtro, campos, CRS, sha256, bytes,
  feições e duração; os eventos `camadas/exportar` e `camadas/exportar_baixar` entram no log do inquilino.
- O arquivo entregue é o mesmo objeto guardado (sha256 conferido) e sai em blocos de 1 MiB
  (`objetos.ler_stream`), tanto no envio quanto na entrega.
- Fica de fora nesta passagem: exportação de VISTA de camada (o tipo `vista_de_camada` existe no catálogo,
  mas o item que o implementa — L0-04-j — ainda não foi entregue; quando for, o filtro da vista entra como
  mais um `where` neste mesmo motor) e exportação de camada REFERENCIADA (422 explícito).

## Alternativas descartadas

- **`WHERE tenant_id = <n>` escrito por nós no SQL do ogr2ogr**: funciona até alguém editar a consulta.
  A RLS não depende de o programador lembrar.
- **VIEW temporária no schema do inquilino** em vez de `mogrify`: evita o SQL literal, mas cria objeto no
  banco a cada exportação, com limpeza para esquecer.
- **Exportar direto para o Garage por streaming, sem arquivo temporário**: o ogr2ogr precisa de arquivo
  local (formatos com índice, como GPKG e FlatGeobuf, escrevem fora de ordem). O que dá para controlar é o
  DISCO (guarda antes de começar), não a existência do arquivo.
