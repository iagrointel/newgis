# ADR 20260910T2056 — OGC API Tiles (20-057) e OGC API Maps sobre o motor raster do L1-02

## Contexto

Item `L1-02-i-ogc-api-tiles-e-maps`. A casa já serve WMTS 1.0.0, WMS 1.3.0, XYZ, TileJSON, STAC e um
ImageServer compatível Esri (todos por token no caminho, `app/imagens/rotas_tiles.py::_autorizar`).
Falta a família OGC API moderna que um catálogo/cliente novo (ArcGIS Pro >= 3.x, QGIS >= 3.34,
qualquer cliente que fale REST+JSON em vez de KVP+XML) procura primeiro: OGC API — Tiles (OGC
20-057, "map tiles" — a Tiles Core + a classe GeoData TileSets, que por definição da spec exige o
recurso Maps por baixo) e OGC API — Maps (`/collections/{collectionId}/map`).

Confirmado por leitura direta da 20-057 (`docs.ogc.org/is/20-057/20-057.html`, lida 10/09): os
caminhos do portão (`/collections/{item}/map/tiles/WebMercatorQuad` e
`/collections/{item}/map/tiles/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}`) são literalmente os
exemplos "Collection Map tiles" da Tabela 4 da spec — não uma invenção desta implementação — e a
ordem de path é `{tileMatrix}/{tileRow}/{tileCol}` = z/y/x (NÃO z/x/y do XYZ).

## Decisão

1. **Nada de segundo motor de pixel.** `app/imagens/ogc_tiles.py` só serializa JSON (landing,
   conformance, `tileMatrixSets`, tileset metadata, `collections`); `app/imagens/rotas_ogc_tiles.py`
   delega TODA leitura de pixel para o que já existe: ladrilho de item -> `rotas_tiles._servir` (a
   MESMA função que atende o XYZ); ladrilho de mosaico -> `rotas_tiles._tile_mosaico_impl` (a MESMA
   função que atende `/svc/<token>/mosaico/<alvo>/{z}/{x}/{y}`); `/map` (OGC API Maps) ->
   `tiles.recorte()` (a função IRMÃ de `ladrilho()`, a mesma que o WMS `GetMap` usa). Consequência
   testável: o ladrilho de `/collections/{item}/map/tiles/WebMercatorQuad/{z}/{y}/{x}` é
   BYTE-A-BYTE igual a `/svc/<token>/raster/<item>/{z}/{x}/{y}` porque é a mesma chamada de função
   com os mesmos argumentos — não uma reimplementação que por acaso bate.
2. **Mesma porta de entrada.** Token no caminho, `_autorizar` (403 sempre, nunca 401/404 para "não é
   seu"), mesmo cache de 5 s, mesmo cabeçalho de auth do nginx (`/api/tiles/autorizar` já cobre este
   prefixo — nenhuma rota nova de autorização de subrequisição).
3. **`{item}` no caminho vale para item raster OU mosaico**, exatamente como o portão pede ("vale
   para item e para mosaico"): `_resolver_colecao` tenta primeiro `plat.raster_item` (mesma consulta
   leve de `_eh_item_raster`); se não for um item do inquilino, tenta mosaico — UUID registrado
   (`mo.obter`) ou nome de coleção completo (`ps.colecao_pertence`, o modo "ad-hoc" que já existe
   desde antes do L1-07). Não há ambiguidade: um nome de coleção nunca é um uuid válido (mesma
   observação que já vale no módulo de tiles).
4. **Metadados de tileset só onde já existe extensão calculável.** `mosaico_tilejson`/
   `mosaico_wmts_rest` (código já em produção) só existem para mosaico REGISTRADO (uuid) — o modo
   ad-hoc (nome de coleção completo) nunca teve documento de capacidades, só ladrilho. Esta
   implementação segue a MESMA assimetria por consistência ("mesma casa"): tileset metadata funciona
   para item e para mosaico registrado; para coleção ad-hoc, o ladrilho funciona (mesmo motor do
   `tile_mosaico`) mas a metadata devolve 422 com a instrução exata para virar mosaico registrado.
   Registrado em `docs/PARIDADE.md`, não escondido.
5. **`/map` (OGC API Maps) só para item raster nesta passagem.** `tiles.recorte()` lê um retângulo
   arbitrário de UMA fonte; compor um retângulo arbitrário de VÁRIAS fontes (mosaico) exigiria motor
   novo (`ladrilho_composto`/`mosaic_reader` só sabe compor por CÉLULA da grade, não por bbox livre) —
   fora do escopo "reuse `recorte()`, não escreva outra leitura" do portão. Registrado como "fora"
   em `docs/PARIDADE.md`, não fingido.
6. **Grade única: WebMercatorQuad.** `/tileMatrixSets/{tileMatrixSetId}` só responde para
   `WebMercatorQuad` — mesma decisão C4 do conceito L1 (todo o motor de ladrilho já é só essa grade).
   Outro id: 404 (`tileMatrixSet_invalido`) — nunca 500, nunca silêncio.
7. **Conformance honesto.** Declarado: `ogcapi-common-1/core`, `ogcapi-common-2/collections`,
   `ogcapi-tiles-1/{core,tileset,geodata-tilesets,png,jpeg}`. NÃO declarado (não implementado):
   `collections-selection` (um tile de VÁRIAS coleções ao mesmo tempo — o modelo desta plataforma é
   uma coleção por serviço, mesma decisão da Features/`rotas_ogc_features.py`), `dataset-tilesets`
   (ladrilho do dataset inteiro sem escolher coleção — não existe "dataset" aqui, só coleções por
   token), `mvt`/`tiff`/`netcdf`/`geojson` (formatos não servidos por este motor), `oas30`/`html`/`xml`
   (sem documento OpenAPI próprio nem HTML nesta passagem — mesma lacuna que Features já tem e já
   documenta), `datetime` (sem dimensão de tempo por coleção nesta passagem).

## Consequência

Cliente ArcGIS Pro/QGIS moderno adiciona a camada por
`https://.../svc/<token>/ogc/tiles/collections/<item>/map/tiles/WebMercatorQuad` sem precisar
entender KVP nem XML. `docs/PARIDADE.md` ganha a tabela feito/parcial/fora deste item.
