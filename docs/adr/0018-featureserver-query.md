# 0018 — Operação `query` do FeatureServer (item L2-04-c)

Data: 2026-09-07 (turno T4, trilha `fsquery`).

## Contexto

O item L2-04-c pede compatibilidade REST com a operação `query` do FeatureServer/Feature Service Layer da Esri
(`developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/`, 45 parâmetros de pedido,
acesso registrado em 06/09/2026 no `estado.json`). É item de COMPATIBILIDADE, não de produto novo: o cliente que já
sabe falar com um FeatureServer (QGIS "ArcGIS REST Server", `arcgis`/Python, um web map JS) tem de conseguir falar
com esta plataforma sem mudar de ferramenta.

O item nasceu sobre duas fundações já entregues: `app/consulta/where_ast.py` (analisador SQL-92 do `where`, feito
no item L2-04-b, `COMPARAÇÃO/AND/OR/IN/LIKE/IS NULL`, compilação parametrizada) e `app/ingestao/carregar.py` +
`plat.camada_preparar` (item L0-04-c: toda camada hospedada vira `d_<slug>.c_<uuid16>` com `fid` OID de 32 bits,
`globalid` uuid, RLS FORCE por `tenant_id`, metadado de campo em `plat.item.dados`). L2-04-b (o diretório de
serviço completo — `/rest/services`, `/FeatureServer` raiz, `/layers`) continua pendente; este item expõe a
operação `query` já endereçável por UUID do item de catálogo, para que L2-04-b monte o resto do diretório por cima
sem reescrever o motor.

## Decisão

### D1 — `where_ast.py` ganha BETWEEN, NOT, literais de data/hora e UPPER/LOWER, na mesma dupla etapa (analisar/compilar)

O item pediu "funções de data e texto do dialeto Esri" além do que L2-04-b já tinha. Em vez de um segundo
analisador, a gramática existente ganhou 4 produções novas (ver docstring do módulo): `NOT` prefixo (liga mais
forte que AND, como em SQL padrão), `BETWEEN valor AND valor`, `DATE 'YYYY-MM-DD'`/`TIMESTAMP 'YYYY-MM-DD HH:MM:SS'`
(viram `datetime.date`/`datetime.datetime` Python — parâmetro tipado, nunca texto colado), `CURRENT_DATE`/
`CURRENT_TIMESTAMP` (palavras-chave do analisador, não texto do cliente — por isso podem virar literal SQL fixo
sem violar a regra de nunca concatenar), e `UPPER(campo)`/`LOWER(campo)` (só envolvem um identificador da lista
branca, nunca uma sub-expressão). 59 testes em `tests/unit/test_where_ast.py` (39 pré-existentes + 20 novos),
inclusive ataques (BETWEEN com sub-select, função não prevista, injeção dentro do literal DATE).

Custo de mudar depois: baixo (aditivo; nada do L2-04-b quebrou — os 39 testes antigos continuam passando sem
alteração de assinatura).

### D2 — Motor único (`app/consulta/motor.py`) que devolve um `Resultado*` tipado, nunca a resposta HTTP

`PedidoQuery` (dataclass com um campo por parâmetro Esri) entra, um de 5 tipos de resultado sai
(`ResultadoFeatures`/`ResultadoCount`/`ResultadoIds`/`ResultadoExtent`, mais o modo estatísticas dentro de
`ResultadoFeatures`). `app/consulta/serializar.py` traduz esse resultado para os 4 formatos (`json`/`pjson`/
`geojson`/`pbf`); a rota (`app/consulta/rotas_query.py`) só faz parsing de request e despacho. Motivo: o mesmo
motor serve tanto a rota HTTP quanto (mais tarde) `queryRelatedRecords`/OGC API Features sem duplicar a construção
de SQL — é o "único gerador de SQL parametrizado" que o C7 do L2_CONCEITO.md já pedia.

### D3 — PBF é o `.proto` OFICIAL da Esri, baixado e compilado nesta máquina, não reimplementado

`app/consulta/proto/FeatureCollection.proto` foi baixado de `raw.githubusercontent.com/Esri/arcgis-pbf/main/proto/
FeatureCollection/FeatureCollection.proto` (HTTP 200 em 07/09/2026 10:23 UTC; repositório `Esri/arcgis-pbf`,
Apache-2.0) e compilado com `protoc` (`protobuf-compiler` 3.21.12, instalado via apt nesta rodada — pacote pequeno,
`df -h /` conferido antes, 30 GB livres) para `FeatureCollection_pb2.py`. Nenhum campo do schema foi inventado:
`Geometry.coords` é `sint64` (só inteiro) — por isso `quantizationParameters` é obrigatório para exportar geometria
em PBF; quando o cliente não declara quantização, `serializar._quantizador_automatico` deriva uma (tolerância
1e-7, origem no canto da página) e a devolve em `FeatureResult.transform`, do mesmo jeito que o modo `view`
manual faria.

Custo de mudar: baixo (o `.proto` é canônico; recompilar é 1 comando `protoc` se a Esri publicar nova versão).

### D4 — Rota montada em `/rest/services/{item_id}/FeatureServer/0/query`, autenticação igual ao GeocodeServer

L2-04-b (diretório completo, pastas, `/FeatureServer` raiz) ainda não existe. Em vez de esperar por ele, a
operação `query` já fica endereçável pelo UUID do item de catálogo (`plat.item.id`, tipo `camada_vetorial`) —
mesma convenção de raiz `/rest/services` que o GeocodeServer compatível (`app/geocodificador/rotas_esri.py`, ADR
0013) já usa, e mesmo padrão de autenticação: sessão de usuário OU token com escopo `camada:ler` (opcional
`camada:ler:<uuid>`, escopado a uma camada), aceito também por `?token=` na URL (é assim que Pro/AGOL se conectam
a um FeatureServer publicado — protocolo Esri nunca manda o token no cabeçalho para clientes de serviço externo).
Esta implementação publica **uma única camada por item** (`camada_id` sempre `"0"`); L2-04-b decide a numeração de
camada dentro de um "grupo publicado" com várias camadas — quando existir, ele reaproveita `motor.py` sem tocar
nele, só mudando a resolução `item_id/camada_id → schema.tabela`.

### D5 — `returnExceededLimitFeatures=false` devolve ZERO feições, não uma página truncada

Achado ao medir contra a doc: o padrão (`true`) devolve até o teto mesmo passando dele; `false` é "tudo ou nada"
— se o teto seria excedido, a Esri não devolve nenhuma feição (só `exceededTransferLimit: true`). A primeira
versão sempre devolvia a página truncada nos dois casos; corrigido e testado (`tests/esri/conformidade_query.py`,
parâmetro `returnExceededLimitFeatures`).

### D6 — `uniqueIds`/`returnUniqueIdsOnly` (11.5) equivalem a `objectIds`/`returnIdsOnly` nesta implementação

Não existe campo de unicidade separado do OID nas camadas hospedadas (D4 do L0-04-c: `fid` é o único identificador
estável). Declarado no PARIDADE.md como equivalência, não como lacuna: os dois parâmetros funcionam, só que
filtram/devolvem o mesmo `fid`.

## O ponto de segurança (não pode falhar)

`where`/`havingClause` só entram no SQL pelo `where_ast` (D1); geometria de filtro só entra por `ST_GeomFromEWKT(%s)`
com o WKT como PARÂMETRO (nunca colado no texto do SQL, mesmo sendo construído a partir de números já validados
em Python); `objectIds`/`uniqueIds` viram `= ANY(%s::bigint[])`; `sqlFormat=native` é RECUSADO (a plataforma não
expõe um caminho para dialeto cru do banco); `groupByFieldsForStatistics`/`outStatistics`/`havingClause` só
referenciam nomes da lista branca (`app/consulta/campos.lista_branca`) ou (para `havingClause`) a EXPRESSÃO
agregada por extenso — nunca o alias da projeção (Postgres não permite, e testar isso pegou um bug real: a
primeira versão tentava `HAVING "alias" > 1` e o banco devolvia "column does not exist").

Provado em `tests/esri/conformidade_query.py::_checar_where_invalido_nao_derruba`: `;DROP TABLE`, comentário SQL,
sub-select dentro de `IN`, `pg_sleep`, operador não previsto (`~~`) — todos 400, nenhum 500, nenhum efeito no
banco. `tests/unit/test_where_ast.py` tem os mesmos ataques no nível do analisador (aspas, `BETWEEN` com
sub-select, função não prevista) mais a garantia estática de que o módulo não usa `eval`/`exec`/`.format` com
texto do usuário.

## O que ficou de fora desta rodada (nomeado, não escondido)

- `time`/`historicMoment`/`timeReferenceUnknownClient`: a camada hospedada não tem `timeInfo` nem branch
  versioning (L2-03-d) — os três são recusados com 422 explícito, nunca ignorados em silêncio.
- `returnM`, `returnTrueCurves`, `multipatchOption`: sempre `false`/sem efeito, declarado — não há M, curva
  verdadeira nem multipatch armazenados.
- `datumTransformation`: aceito e ignorado; só o pipeline padrão do PROJ (via `ST_Transform`) é aplicado.
- `resultType`: só `standard` testado; `tile` não muda comportamento nesta implementação.
- QGIS carregando 100 mi de linhas e a consulta espacial ≤ 200 ms p95 em 7,36 mi de imóveis do acervo: ver
  `tests/medidas/L2-04-c-consulta-espacial-p95.json` (medido em `public.car_area_imovel`, 8.406.837 linhas reais,
  índice GIST — p95 = 1,6 ms com o padrão de consulta real do motor, LIMIT 2001; a contagem exaustiva
  `returnCountOnly` sobre a mesma tabela mede p95 = 986 ms, registrado à parte por não ser o que o portão pede).
  QGIS de verdade contra o endpoint publicado **não foi verificado nesta rodada** — falta ambiente gráfico/headless
  estável para QGIS Desktop dentro do orçamento deste turno; registrado como pendência, não como feito.
