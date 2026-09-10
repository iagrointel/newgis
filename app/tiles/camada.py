"""Resolução de item de camada vetorial -> tabela/função de tile (item L2-04-e). Reusa
`_item_id_valido`/`_camada_do_item` de `app.consulta.rotas_query` (mesmo achado do adversário
daquele item: id malformado nunca chega ao banco como texto cru — vira 404 antes)."""

from __future__ import annotations

from app.consulta.rotas_query import _camada_do_item, _item_id_valido  # noqa: F401 — reexportado
from app.erros import ErroAPI


def funcao_tile(dados: dict) -> str:
    """`c_<16 hex>` -> `t_<16 hex>` (nome da função de tile que `plat.camada_tile_garantir`,
    item L2-04-a, criou no schema da camada — é também o `source_id` que o Martin publica,
    conferido no binário `martin-v1.15.0`: `source_id_format: "{function}"`)."""
    tabela = dados.get("tabela") or ""
    if not tabela.startswith("c_"):
        raise ErroAPI(409, "camada_sem_funcao_de_tile", "esta camada não tem tabela hospedada com função de tile")
    return "t_" + tabela[2:]


def extent_4326(cur, schema: str, tabela: str) -> list[float] | None:
    """Envelope da camada em WGS84 (TileJSON/VectorTileServer sempre anunciam bounds em graus,
    mesmo quando a fonte nativa é outro SRID — diferente do FeatureServer, que preserva o SRID
    nativo por C11 do L2_CONCEITO: aqui é o CONTRATO do TileJSON 3.0/Esri que exige graus)."""
    cur.execute(f'SELECT ST_Extent(ST_Transform("geom", 4326)) AS caixa FROM "{schema}"."{tabela}"')  # noqa: S608 — schema/tabela vêm de plat.item
    r = cur.fetchone()
    caixa = r["caixa"] if r else None
    if not caixa:
        return None
    miolo = caixa[4:-1] if caixa.startswith("BOX(") else caixa
    (xmin, ymin), (xmax, ymax) = (tuple(float(v) for v in par.split()) for par in miolo.split(","))
    return [xmin, ymin, xmax, ymax]
