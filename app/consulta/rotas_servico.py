"""Diretório e metadados do FeatureServer (item L2-04-servicos-esri-ogc, que fecha ao redor da operação
`query` já construída no item L2-04-c/ADR 0018 — REUSADA aqui sem reescrita: `campos_da_camada`,
`GEOM_PG_PARA_ESRI`, `_autenticar` do mesmo módulo `app.consulta.rotas_query`).

Cobre a parte "o cliente descobre o serviço" que faltava para o FeatureServer ser navegável por
ArcGIS Pro/QGIS/AGOL sem a URL exata da camada de antemão: o descritor do serviço (`.../FeatureServer
?f=json`, com `layers`/`tables`/`fullExtent`/`spatialReference`/`capabilities`) e o descritor da
camada (`.../FeatureServer/0?f=json`, com `fields`/`geometryType`/`drawingInfo`/`capabilities`).

Esta implementação publica UMA camada por item (id fixo "0"), mesma restrição já declarada em
`rotas_query._query`; por isso `layers` tem sempre 0 ou 1 elemento e `tables` é sempre vazio (a
plataforma não tem, ainda, o conceito de tabela sem geometria publicada por este caminho — registrado
como fora em docs/PARIDADE.md).

`applyEdits`, `attachments`, `queryRelatedRecords` e `relationships` dependem do item L2-03-edicao
(escrita transacional) e do L2-10-b (relacionamentos), NENHUM dos dois construído ainda — por isso
`capabilities` nunca anuncia "Create,Update,Delete,Uploads,Editing" e a lista de `relationships` da
camada é sempre `[]`, nunca inventada. Ver `docs/PARIDADE.md` para a linha viva."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import db
from app.consulta import campos as campos_mod
from app.consulta.rotas_query import PREFIXO as PREFIXO_CAMADA
from app.consulta.rotas_query import _autenticar, _item_id_valido
from app.consulta.serializar import GEOM_PG_PARA_ESRI
from app.erros import ErroAPI

router = APIRouter(tags=["consulta-esri"])
PREFIXO_SERVICO = "/rest/services/{item_id}/FeatureServer"
CURRENT_VERSION = 11.3  # mesma versão declarada no GeocodeServer (app/geocodificador/rotas_esri.py)


def _camada_e_titulo(cur, item_id: str) -> tuple[dict, str]:
    """Igual a `rotas_query._camada_do_item`, mas também traz `titulo` — que vive na coluna
    `plat.item.titulo`, não dentro de `dados` (conferido em `app/ingestao/carregar.py`). Valida o
    formato de `item_id` ANTES do banco (mesmo achado/conserto do adversário em `rotas_query.py`)."""
    _item_id_valido(item_id)
    cur.execute(
        "SELECT dados, titulo FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,)
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")
    return r["dados"], r["titulo"]


def _extent_nativo(cur, schema: str, tabela: str, srid: int) -> dict | None:
    """`fullExtent` na referência espacial NATIVA da camada (C11 do L2_CONCEITO: SRID nunca convertido
    na ingestão). `ST_Extent` sozinho, sem filtro: custo aceitável para um descritor chamado raramente
    (não está no caminho de `query`/tile); tabela vazia devolve None, nunca um envelope inventado."""
    cur.execute(f'SELECT ST_Extent("geom") AS caixa FROM "{schema}"."{tabela}"')  # noqa: S608 — schema/tabela vêm de plat.item, nunca do cliente
    r = cur.fetchone()
    caixa = r["caixa"] if r else None
    if not caixa:
        return None
    # formato "BOX(xmin ymin,xmax ymax)"
    miolo = caixa[4:-1] if caixa.startswith("BOX(") else caixa
    (xmin, ymin), (xmax, ymax) = (
        tuple(float(v) for v in par.split()) for par in miolo.split(",")
    )
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "spatialReference": {"wkid": srid}}


def _campo_json(c: dict) -> dict:
    d = {
        "name": c["nome"],
        "type": c["tipo_esri"],
        "alias": c["nome"],
        "nullable": c["nullable"],
        "editable": c["papel"] not in ("oid", "globalid"),
    }
    if c["comprimento"]:
        d["length"] = c["comprimento"]
    if c["papel"] == "globalid":
        d["sqlType"] = "sqlTypeOther"
    return d


def _descritor_camada(cur, item_id: str, dados: dict, titulo: str | None) -> dict:
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    meta = campos_mod.campos_da_camada(cur, schema, tabela)
    geom_pg = dados.get("geometria")
    tipo_esri = GEOM_PG_PARA_ESRI.get(geom_pg)
    oid_campo = next((c["nome"] for c in meta if c["papel"] == "oid"), "fid")
    globalid_campo = next((c["nome"] for c in meta if c["papel"] == "globalid"), None)
    return {
        "currentVersion": CURRENT_VERSION,
        "id": 0,
        "name": titulo or item_id,
        "type": "Feature Layer",
        "description": "",
        "geometryType": tipo_esri,
        "sourceSpatialReference": {"wkid": srid},
        "extent": _extent_nativo(cur, schema, tabela, srid),
        "objectIdField": oid_campo,
        "globalIdField": globalid_campo or "",
        "displayField": next((c["nome"] for c in meta if c["papel"] == "atributo"), oid_campo),
        "fields": [_campo_json(c) for c in meta],
        # sem L2-03-a/L2-10-b: nunca anunciar Create/Update/Delete/Uploads (P2 — anúncio sem
        # mecanismo é o mesmo defeito que um botão que não faz nada)
        "capabilities": "Query",
        "supportedQueryFormats": "JSON,geoJSON,PBF",
        "hasAttachments": False,
        "relationships": [],
        "advancedQueryCapabilities": {
            "supportsPagination": True,
            "supportsStatistics": True,
            "supportsDistinct": True,
            "supportsOrderBy": True,
            "supportsQueryWithDistance": True,
        },
        "maxRecordCount": 2000,
        "supportsCoordinatesQuantization": True,
        "drawingInfo": {"renderer": {"type": "simple", "symbol": {}}},
    }


@router.get(PREFIXO_SERVICO, openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="consulta_esri_servico_descritor")
def descritor_servico(item_id: str, request: Request):
    """`.../FeatureServer?f=json` — raiz do diretório. `f` diferente de json/pjson não é servido aqui
    (html é a UI da Esri, que não construímos; ver docs/PARIDADE.md)."""
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        camada = _descritor_camada(cur, item_id, dados, titulo)
    return {
        "currentVersion": CURRENT_VERSION,
        "serviceDescription": titulo or "",
        "hasVersionedData": False,
        "supportsDisconnectedEditing": False,
        "syncEnabled": False,
        "hasStaticData": False,
        "maxRecordCount": 2000,
        "supportedQueryFormats": "JSON,geoJSON,PBF",
        "capabilities": "Query",
        "spatialReference": camada["sourceSpatialReference"],
        "fullExtent": camada["extent"],
        "layers": [{"id": 0, "name": camada["name"], "parentLayerId": -1, "defaultVisibility": True,
                    "subLayerIds": None, "minScale": 0, "maxScale": 0, "type": "Feature Layer",
                    "geometryType": camada["geometryType"]}],
        "tables": [],
    }


@router.get(f"{PREFIXO_CAMADA}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="consulta_esri_camada_descritor")
def descritor_camada(item_id: str, camada_id: str, request: Request):
    """`.../FeatureServer/0?f=json` — descritor da camada. `camada_id` diferente de "0" cai no mesmo
    404 já usado pela `query` (uma camada publicada por item, ver docstring do módulo)."""
    if camada_id != "0":
        raise ErroAPI(404, "camada_nao_encontrada", "esta implementação publica uma camada só (id 0) por item")
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        dados, titulo = _camada_e_titulo(cur, item_id)
        return _descritor_camada(cur, item_id, dados, titulo)
