# Esquemas OGC — validação sem depender de rede

`ogcapi-tiles-1.bundled.json` é a cópia local do documento OpenAPI **bundled** (todos os `$ref`
resolvidos dentro do mesmo arquivo) de OGC API — Tiles Part 1, baixado de
`https://schemas.opengis.net/ogcapi/tiles/part1/1.0/openapi/ogcapi-tiles-1.bundled.json` em
10/09/2026 (conferido: `paths./tileMatrixSets`, `paths./tileMatrixSets/{tileMatrixSetId}`,
`paths./collections/{collectionId}/map/tiles/{tileMatrixSetId}` e `paths./` e `paths./conformance`
apontam, via `$ref`, para `components.responses.{TileMatrixSetsList,TileMatrixSet,TileSet,
LandingPage,Conformance}` → `components.schemas.{tileMatrixSet-item,tileMatrixSet,tileSet,
landingPage,confClasses}` — os mesmos nomes usados pelo teste `tests/api/imagens/
test_ogc_tiles_schema.py`).

Usado por `tests/api/imagens/test_ogc_tiles_schema.py` (item L1-02-i-ogc-api-tiles-e-maps, cláusula
do portão "…ou em teste próprio contra o JSON Schema da spec") — não existe ETS (executable test
suite) oficial de OGC API — Tiles publicado para rodar offline nesta bancada; a alternativa que o
portão prevê é esta.
