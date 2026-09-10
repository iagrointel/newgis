# ADR 20260910T2330 — mosaico é uma busca STAC registrada, composta em casa

Item: `L1-07-mosaico-por-colecao-e-pegadas`. Situação: aceito. Depende de: L1-01-a (pgstac +
isolamento por coleção), L1-02-tiles-token (ladrilho de item, reaproveitado por dentro), L0-02-d
(token de serviço com escopo em lista).

## 1. Registro delega ao pgstac; composição de pixel fica em casa

`titiler-pgstac` (3.1.0, já na venv da aplicação) implementa `POST /searches/register` chamando a
função SQL `pgstac.search_query(_search, _metadata)`, que calcula um hash determinístico
(`pgstac.search_hash`) e faz upsert em `pgstac.searches`. **Usamos essa função SQL diretamente**
(psycopg2 síncrono, dentro da mesma transação por tenant que o resto da app usa) em vez do pacote
`titiler-pgstac` inteiro. Dois motivos, medidos antes de decidir:

1. `titiler-pgstac` é uma fábrica de rotas **ASGI assíncrona** com pool `asyncpg` próprio
   (`app.state.dbpool`), sem noção de RLS por inquilino — a casa inteira autoriza por
   `SET LOCAL plat.tenant_id` numa conexão psycopg2 síncrona (`app/db.py`). Encaixar as duas
   arquiteturas em 2h30 seria abrir uma segunda pilha de acesso a banco dentro do mesmo processo,
   não estender a existente — risco alto para o orçamento do turno.
2. O TiTiler já rodando em `127.0.0.1:8131` (unidade `plataforma-titiler`) **não tem
   `titiler-pgstac` instalado** (só `titiler-core`/`titiler-mosaic`/`titiler-extensions`, ver
   `pipeline/app.py`) e é um serviço de PROVA do pipeline, fora do controle de token/tenant desta
   app — nem o cliente (`?url=` restrito ao balde `demo`) nem o servidor sabem o que é um
   inquilino. Apontar mosaico de cliente para ele furaria o isolamento por RLS que o resto da API
   garante (P6).

Por isso a COMPOSIÇÃO do ladrilho (qual cena de qual candidata vira o pixel) roda em casa,
reaproveitando `app/imagens/tiles.py` (o mesmo `rio_tiler.io.Reader.tile()` que já serve
`/svc/<token>/raster/<item>/...` desde o L1-02) — exatamente o caminho que o esqueleto ad-hoc
`tile_mosaico` (existente antes deste item, "mosaico da coleção inteira, mais recente por cima")
já usava. Este item GENERALIZA esse caminho para aceitar também uma busca REGISTRADA (múltiplas
coleções, bbox, datetime, filtro CQL2, ordenação), não só "a coleção inteira".

Regra de seleção de pixel neste item: a PRIMEIRA cena (na ordem do `sortby` registrado, padrão
`datetime desc`) que tem dado no pixel vence — a mesma regra que o ad-hoc já tinha. Regras adicionais
(`median`, `mean`, `lock raster`, "mais recente sem nuvem" via máscara SCL) são do item irmão
L1-08, fora deste turno.

## 2. O id exposto é um uuid da casa, não o hash md5 do pgstac

`pgstac.search_hash` devolve md5 (32 hex, sem hífen). O vocabulário de escopo de token
(`app/auth/escopos.py`, `ESCOPO`/`COM_UUID`) só aceita `tiles:ler:<uuid-com-hífen>`, e a validação
na criação do token (`item_legivel`) exige uma linha em `plat.item`. Por isso todo mosaico
registrado ganha um `id uuid` PRÓPRIO (`plat.mosaico.id`, `gen_random_uuid()`) e uma linha-espelho
em `plat.item` (tipo `mosaico`) com o MESMO id — o mesmo padrão que todo item raster já segue
(`app/imagens/ingestao.py`: o STAC id É o `plat.item.id`). Um token pode então ganhar
`tiles:ler:<uuid-do-mosaico>` sem nunca ganhar `tiles:ler:<item-id>` de nenhuma cena que o compõe —
a cláusula do portão "token com escopo no mosaico não vê item avulso" vem de graça do MESMO
mecanismo genérico de escopo por item que já existia, sem mudar `app/auth/escopos.py`.

Idempotência ("a mesma busca registrada duas vezes devolve o mesmo id"): `UNIQUE(tenant_id, hash)`
em `plat.mosaico` — a segunda chamada com os MESMOS critérios calcula o mesmo hash pgstac, bate no
`ON CONFLICT` e devolve a linha existente (mesmo uuid). O `nome` do primeiro registro fica; só
`atualizado_em` muda.

## 3. Autorização: `plat.mosaico` é quem decide, pgstac.searches é só conteúdo

`pgstac.searches` não tem `tenant_id` — é uma tabela global, PK = hash. Isso é seguro porque
`collections` (sempre restrito à interseção com `pgstac.colecoes_do_tenant`, nunca aceito cru do
cliente — `app/imagens/pgstac.py::parametros_busca`) já embute o prefixo `<tenant_id>-` de cada
coleção; dois inquilinos nunca produzem o MESMO hash para um mosaico não-vazio porque as listas de
coleção divergem. Mesmo assim, **nenhuma rota de mosaico lê `pgstac.searches` para autorizar** — a
mesma separação de `raster_item.py` (pgstac guarda STAC; a tabela-espelho, com RLS, decide "este
inquilino pode ver isto"). Toda leitura de tile/tilejson/wmts/pegadas primeiro confere
`plat.mosaico WHERE id = :busca AND tenant_id = :tenant_id AND estado = 'ativo'` — 403 (nunca 404,
mesma regra do resto do módulo) se a linha não existir ou for de outro inquilino.

## 4. URL: reaproveita o contrato existente, sem colidir com os 2 testes que já dependiam dele

O ad-hoc `tile_mosaico` já ocupava `/svc/<token>/mosaico/<colecao>/{z}/{x}/{y}` (dois testes,
`test_mosaico_da_colecao_serve_ladrilho` e `test_mosaico_de_colecao_de_outro_inquilino_da_403`, em
`tests/api/imagens/test_tiles_token.py`, continuam valendo tal e qual). Em vez de abrir uma segunda
rota colidente, o parâmetro do caminho agora aceita **duas formas**, distinguidas pelo formato:
- uuid → mosaico REGISTRADO (`plat.mosaico`, este item): busca com múltiplas coleções, filtro,
  ordenação; escopo fino `tiles:ler:<uuid>`;
- `<tenant_id>-<slug>` → comportamento ANTIGO preservado (coleção inteira, sem registro, escopo
  `tiles:ler`/`imagens:ler` genérico).

`tilejson.json`, `wmts`, `wmts/1.0.0/WMTSCapabilities.xml` e `pegadas` são rotas NOVAS, só para
mosaico registrado (o ad-hoc nunca teve essas; não há colisão possível).

## 5. Fora deste turno (nomeado)

- Pegadas como camada vetorial por Martin (a hipótese do item cita isso como equivalente à sublayer
  "Footprint"): implementado só como GeoJSON pela API — o portão não exige Martin explicitamente e
  o orçamento de tempo não fechava as duas formas com qualidade. GeoJSON já abre no mapa com popup
  de data/nuvem, que é a cláusula testada.
- Regras de seleção de pixel além de "primeira com dado" (L1-08).
- Tela "Coleção → Mosaico" no construtor de mapa (L2): a API é completa e testada; UI fica para
  quando o item L2 correspondente abrir, ou como incremento seguinte deste mesmo item se sobrar
  tempo no turno.
