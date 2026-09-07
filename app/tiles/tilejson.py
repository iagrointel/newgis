"""TileJSON 3.0.0 (item L2-04-e; spec https://github.com/mapbox/tilejson-spec/tree/master/3.0.0).
Um documento por camada — o `vector_layers` tem sempre UMA entrada (id = nome da função de tile,
`t_<16 hex>`, o mesmo `source-layer` que `ST_AsMVT` grava dentro do MVT em
`plat.camada_tile_garantir`, item L2-04-a) porque esta implementação publica uma camada por
função, nunca um mosaico de várias na mesma fonte."""

from __future__ import annotations

ZOOM_MIN_PADRAO = 0
ZOOM_MAX_PADRAO = 22


def documento(
    *,
    nome: str,
    funcao: str,
    tiles_url: str,
    bounds: list[float] | None,
    campos: list[dict],
    atribuicao: str | None = None,
    zoom_min: int = ZOOM_MIN_PADRAO,
    zoom_max: int = ZOOM_MAX_PADRAO,
) -> dict:
    fields = {c["nome"]: c["tipo_pg"] for c in campos}
    doc: dict = {
        "tilejson": "3.0.0",
        "name": nome,
        "scheme": "xyz",
        "tiles": [tiles_url],
        "minzoom": zoom_min,
        "maxzoom": zoom_max,
        "vector_layers": [
            {
                "id": funcao,
                "fields": fields,
                "minzoom": zoom_min,
                "maxzoom": zoom_max,
                "description": f"camada vetorial {nome}",
            }
        ],
    }
    if bounds:
        doc["bounds"] = bounds
        doc["center"] = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2, zoom_min]
    if atribuicao:
        doc["attribution"] = atribuicao
    return doc
