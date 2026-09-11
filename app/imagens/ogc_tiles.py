"""OGC API — Tiles (OGC 20-057) e OGC API — Maps sobre o motor raster do L1-02 (item
L1-02-i-ogc-api-tiles-e-maps; ADR 20260910T2056).

Este módulo só serializa JSON — nenhuma leitura de pixel, nenhuma consulta ao banco. A mesma divisão
de `app/imagens/wms.py` (documento) x `app/imagens/rotas_wms.py` (rota+autorização+pixel): quem lê o
COG é sempre `app/imagens/tiles.py`, chamado de `app/imagens/rotas_ogc_tiles.py`.

A grade servida é só `WebMercatorQuad` (mesma decisão C4 do conceito L1 — todo o motor de ladrilho já
é essa grade só) e a definição devolvida por `/tileMatrixSets/WebMercatorQuad` é a do PRÓPRIO
morecantile (`TMS.model_dump`), a mesma biblioteca que gera a grade de verdade — não uma cópia escrita
à mão que pode divergir. `TMS.model_dump` já produz o esquema TileMatrixSet2D da OGC Two Dimensional
Tile Matrix Set and Tile Set Metadata 2.0 (17-083r4), que é o mesmo esquema que 20-057 referencia.

Cobertura desta passagem (linha viva em `docs/PARIDADE.md`):
  feito    - landing, /conformance, /tileMatrixSets, /tileMatrixSets/WebMercatorQuad (definição real,
             não só o nome), /collections (só itens raster do inquilino, mesma restrição de
             visibilidade do WMS), /collections/{item} (item OU mosaico registrado, endereçado direto
             mesmo fora da listagem — mesma assimetria que o resto do módulo já tem: mosaico nunca é
             enumerado, só acessado por endereço conhecido), tileset metadata (item + mosaico
             registrado), ladrilho (item + mosaico registrado + mosaico ad-hoc por nome de coleção).
  parcial  - tileset metadata do mosaico ad-hoc (nome de coleção completo, sem registro): 422 com a
             instrução de registrar a busca — mesma lacuna que `mosaico_tilejson`/`mosaico_wmts_rest`
             já têm hoje (ver ADR §4).
  fora     - OGC API Maps (`/map`) só para item raster: compor um retângulo arbitrário de várias cenas
             exigiria motor de composição por bbox livre, que não existe (`ladrilho_composto` só
             compõe por célula da grade) — ver ADR §5. `collections-selection` (tile de várias
             coleções combinadas), `dataset-tilesets` (não existe "dataset" nesta plataforma, só
             coleções por token), formatos mvt/tiff/netcdf/geojson, `/api` (OpenAPI próprio), HTML,
             dimensão `datetime` por coleção.
"""

from __future__ import annotations

from app.imagens.tiles import TMS

TMS_ID = "WebMercatorQuad"

CONFORMANCE: tuple[str, ...] = (
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/tileset",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/geodata-tilesets",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/png",
    "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/jpeg",
)


def landing(base: str) -> dict:
    return {
        "title": "OGC API — Tiles / Maps",
        "description": "Ladrilho e recorte de imagem raster hospedada da plataforma, servidos por "
        "OGC API — Tiles (20-057, classe GeoData TileSets) e OGC API — Maps. Análise/beta privado.",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
            {"rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-schemes", "type": "application/json",
             "href": f"{base}/tileMatrixSets"},
        ],
    }


def conformance() -> dict:
    return {"conformsTo": list(CONFORMANCE)}


def tile_matrix_set_definicao() -> dict:
    """A definição REAL da grade (não um resumo escrito à mão) — o mesmo objeto que `tiles.py` usa
    para calcular todo ladrilho servido por esta plataforma."""
    return TMS.model_dump(mode="json", by_alias=True, exclude_none=True)


def tile_matrix_sets_lista(base: str) -> dict:
    return {
        "tileMatrixSets": [
            {
                "id": TMS_ID,
                "title": TMS.title,
                "uri": TMS.uri,
                "links": [
                    {"rel": "self", "type": "application/json",
                     "href": f"{base}/tileMatrixSets/{TMS_ID}"},
                ],
            },
        ],
    }


def colecoes_json(base: str, itens: list[dict]) -> dict:
    """`itens`: [{item_id, titulo, bounds=[oeste,sul,leste,norte] em 4326}] — mesma forma que
    `rotas_wms._camadas_visiveis` já produz (reusado, não recalculado)."""
    return {
        "collections": [_colecao_um(base, it["item_id"], it["titulo"], it["bounds"]) for it in itens],
        "links": [{"rel": "self", "type": "application/json", "href": f"{base}/collections"}],
    }


def _colecao_um(base: str, item: str, titulo: str, bounds: list[float]) -> dict:
    raiz = f"{base}/collections/{item}"
    return {
        "id": item,
        "title": titulo,
        "extent": {"spatial": {"bbox": [bounds], "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
        "links": [
            {"rel": "self", "type": "application/json", "href": raiz},
            {"rel": "http://www.opengis.net/def/rel/ogc/1.0/map", "type": "image/png",
             "href": f"{raiz}/map"},
            {"rel": "http://www.opengis.net/def/rel/ogc/1.0/map-tileset", "type": "application/json",
             "href": f"{raiz}/map/tiles/{TMS_ID}"},
        ],
    }


def colecao_json(base: str, item: str, titulo: str, bounds: list[float]) -> dict:
    return _colecao_um(base, item, titulo, bounds)


def tileset_json(base: str, item: str, titulo: str, bounds: list[float], minzoom: int, maxzoom: int,
                 limites: list[dict], formatos: list[str]) -> dict:
    """Recurso "TileSet" (OGC API — Tiles §8 / 17-083r4 §9): metadados do CONJUNTO de ladrilhos de map
    tiles desta coleção — dataType "map" porque são imagens já renderizadas (PNG/JPEG), não feição
    vetorial (dataType "vector") nem cobertura crua (dataType "coverage")."""
    raiz = f"{base}/collections/{item}/map/tiles/{TMS_ID}"
    link_item = {
        "rel": "item", "type": formatos[0], "title": "ladrilho",
        "href": raiz + "/{tileMatrix}/{tileRow}/{tileCol}." + _ext(formatos[0]),
        "templated": True,
    }
    return {
        "title": titulo,
        "dataType": "map",
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "tileMatrixSetURI": TMS.uri,
        "tileMatrixSetLimits": limites,
        "boundingBox": {
            "lowerLeft": [bounds[0], bounds[1]], "upperRight": [bounds[2], bounds[3]],
            "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        },
        "links": [
            {"rel": "self", "type": "application/json", "href": raiz},
            {"rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-scheme", "type": "application/json",
             "href": f"{base}/tileMatrixSets/{TMS_ID}"},
            link_item,
        ],
    }


def _ext(media_type: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(media_type, "png")


__all__ = [
    "CONFORMANCE", "TMS_ID",
    "colecao_json", "colecoes_json", "conformance", "landing",
    "tile_matrix_set_definicao", "tile_matrix_sets_lista", "tileset_json",
]
