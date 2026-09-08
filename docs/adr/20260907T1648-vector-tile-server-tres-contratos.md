# Servidor de tiles vetoriais em três contratos (item L2-04-e-vector-tile-server-tilejson)

Nomeado por carimbo de tempo (ADR 0014): número sequencial pode colidir com outra trilha ainda não
juntada.

## Contexto

O Martin (item L2-01-b) já serve o MVT cru por função de tile, com a verificação de token do L2-04-a
(`/internal/tiles/verificar`) sentada na frente via `auth_request` do nginx. Faltava o que os
clientes REALMENTE colam numa URL: TileJSON para MapLibre/QGIS, um serviço no formato que o
AGOL/Portal/Pro reconhecem como "Vector Tile Layer" sem crédito de hospedagem, e exportação por
arquivo para quem só quer os dados fora do mapa (Google Earth, planilha, scripts).

## Decisões

**C1 — Martin publica por FUNÇÃO com `source_id_format: "{function}"`.** Conferido rodando o binário
real (`martin-v1.15.0`) contra a base da trilha: o `source_id` é o nome puro da função de tile
(`t_<16 hex>`), sem o schema — únicos globalmente porque o hex é aleatório por camada
(`plat.camada_tile_garantir`, item L2-04-a). O tile HTTP nativo do Martin é
`GET /<funcao>/<z>/<x>/<y>` com a query string INTEIRA repassada ao 4º parâmetro
`query_params::json` da função — é assim que `?token=&item=` chegam a `plat.contexto_por_token`.

**C2 — a API é o front-door dos dois contratos de tile, não o nginx sozinho.** Diferente do
L2-01-b (que só tem `auth_request` + `proxy_pass` direto ao Martin), aqui `app/tiles/
vector_tile_server.py` chama o Martin via `httpx` (`app/tiles/martin_cliente.py`) DEPOIS de
autenticar com o MESMO código do FeatureServer/raster (`app.auth.sessao._auth_de_token` +
`app.auth.escopos.exigir_escopo`, escopo `camada:ler`). Isso porque a app pode devolver o 401
correto por conta própria (o Martin nunca devolve — `GetTileWithQueryError` classifica tudo como
500, ADR 20260907T0235) e porque o CONTRATO 2 (Esri, ordem z/y/x) e o CONTRATO 1 (MapLibre, ordem
z/x/y) precisam do MESMO tile — `_tile_bytes` em `vector_tile_server.py` é a ÚNICA função que fala
com o Martin; as duas rotas HTTP só trocam a ordem dos argumentos de entrada. Isso faz a cláusula
"byte a byte igual" ser verdade por construção, medida em `tests/api/test_vector_tile_server.py::
test_tile_esri_e_maplibre_sao_byte_a_byte_iguais` com Martin real.

**C3 — token no CAMINHO em todos os três contratos**, reusando a decisão já tomada pelo ladrilho
raster (item L1-02, `wt/tilestok`, ainda não mesclado nesta árvore mas citado como ativo da casa a
reusar pelo próprio item): nunca cookie, nunca URL assinada que expira. Cache de autorização de 2 s
em processo (`app/tiles/autorizacao.py`), mesmo desenho do `_AUTH`/`_autorizar` do raster.

**C4 — VectorTileServer de UMA camada por item**, mesma restrição do FeatureServer (item L2-04-c):
`{nome}` na URL Esri é o UUID do item do catálogo, não um nome amigável — não existe, nesta
plataforma, um registro de "nome de serviço" separado do item (fica para quando existir).

**C5 — estilo padrão é COMPUTADO, não gravado.** O item de camada (`camada_vetorial`) não carrega
uma referência a um item `estilo` (esse vínculo, se um dia existir, é de outra família — L2-02-b/c/d,
nenhuma delas construída). `root.json` chama `app.estilos.padrao.estilo_padrao` (item L2-02-a,
MESMO compilador determinístico que a ingestão usa para a cor padrão de uma camada nova) na hora,
pela geometria da camada — nunca um YAML/JSON novo reinventado aqui.

**C6 — sprite/glyphs são REAIS mas VAZIOS.** `L2-02-e` (sprites/fontes do Martin) não é dependência
declarada deste item e não está construído. Em vez de 404/500 — que quebraria o cliente Esri, que
sempre pede esses dois recursos ao carregar o estilo — a resposta é um documento SINTATICAMENTE
válido e vazio: `sprite.json` = `{}` (nenhum ícone), `sprite.png` = PNG 1x1 transparente de bytes
reais, `fonts/{stack}/{range}.pbf` = um protobuf `glyphs.proto` válido (`stacks[0].name`/`range`
preenchidos, `glyphs` vazio) montado à mão por wire format — sem adicionar dependência nova ao
venv compartilhado só para isto. Fronteira honesta, registrada no handoff; abre quando L2-02-e
entregar ícone/fonte de verdade.

**C7 — FlatGeobuf NÃO é gerado incrementalmente nesta versão do GDAL.** Tentativa medida:
`ogr2ogr -f FlatGeobuf /vsistdout/ ...` falha com `ERROR 1: Failed to create directory
/vsistdout/` no GDAL 3.8.4 desta máquina (o driver tenta abrir o destino como diretório). FGB e
GPKG (SQLite — nunca foi candidato a incremental) escrevem num arquivo TEMPORÁRIO via `ogr2ogr`
contra o Postgres (DSN com `options='-c plat.tenant_id=... '`, a mesma técnica de startup option do
libpq que dá RLS a um processo que abre a própria conexão, sem bypass) e a resposta HTTP é
streamada em pedaços de 64 KiB a partir do disco, apagado ao fim. GeoJSON/KML/CSV são os três que
cumprem a cláusula medida do portão (cursor nomeado do Postgres, nunca `fetchall`; RSS do worker
medido em 145 MB para 1.000.000 de feições, teto do portão 300 MB).

**C8 — `where`/`bbox` reusam o AST já construído (L2-04-b/c).** `app.consulta.where_ast.
compilar_where` + `app.consulta.campos.lista_branca` — nenhuma gramática nova, nenhuma
concatenação de texto do cliente. Para `ogr2ogr` (que não aceita `%s`), o SQL final é gerado com
`cursor.mogrify` (a mesma função que o psycopg2 usa por dentro), nunca uma f-string com o valor do
cliente.

## Refutação do adversário (medida)

- **root.json vs validador oficial**: `node ferramentas/estilo/validar.mjs` (pacote
  `@maplibre/maplibre-gl-style-spec`, o MESMO validador do item L2-02-a) — passou; e reprova de
  verdade quando um `layer.type` é corrompido (teste dedicado).
- **tile z25**: fora do intervalo que `plat.camada_tile_garantir` aceita (0-24) — o Martin recusa,
  `app.tiles.martin_cliente` mapeia para 502 (falha de infraestrutura nomeada), nunca uma exceção
  crua.
- **.csv de camada com geometria MULTI**: funciona (WKT de `MULTIPOLYGON`, testado). **.csv de
  "camada sem geometria"**: não existe esse conceito neste catálogo — `plat.camada_preparar` exige
  SRID/tipo para toda `camada_vetorial` — então o pedido do adversário aterrissa em 403 (token sem
  escopo para um item que ele não pediu) ou 404 (`camada_nao_encontrada`), nunca 500.
- **ETag depois de uma edição**: o ETag É o sha256 dos bytes do tile — muda de verdade quando o
  Martin relê do Postgres (confirmado: revogar o cache do Martin — `cache: expiry: 5m`,
  `deploy/martin.yaml`, decisão do L2-01-b — e pedir de novo devolve ETag diferente). ACHADO real:
  DENTRO da janela de 5 min de cache em memória do próprio Martin (chave = URI completa, incluindo
  a query com token/item), o mesmo pedido devolve o MESMO ETag mesmo depois de editar a geometria —
  isso é uma decisão JÁ TOMADA pelo item L2-01-b (`cache: size_mb: 64, expiry: 5m` em
  `deploy/martin.yaml`), não um defeito introduzido aqui. Quem precisa refletir uma edição em menos
  de 5 min pode acrescentar um parâmetro de versão à query (ex. `&v=<hash>`), que muda a chave do
  cache do Martin — não implementado neste item (fora do portão literal, que só pede "mede se o
  ETag muda depois de uma edição", sem prazo).

## O que fica de fora (fronteira honesta)

- Sprite/glyphs de verdade: depende de L2-02-e (não construído, não dependência deste item).
- Pro/AGOL de verdade: **D20, PENDENTE** — só QGIS foi medido aqui (PyQGIS headless, ver handoff).
- FlatGeobuf/GeoPackage incrementais: GDAL 3.8.4 desta máquina não permite; arquivo temporário.
- Nome de serviço amigável no VectorTileServer: usa o UUID do item, não um registro de nomes.
