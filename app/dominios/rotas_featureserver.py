"""Exposição dos domínios e subtipos no FeatureServer (item L2-10-a).

`GET /rest/services/{item_id}/FeatureServer` e `.../FeatureServer/0` devolvem o recurso no formato que o
ArcGIS Pro e o Map Viewer leem, com `fields[].domain` e `types[]` montados do banco pelo `app/dominios/esri.py`.

Fronteira declarada: este módulo publica só o METADADO da camada — é o pedaço do FeatureServer de que o item
L2-10-a depende para provar "domains e types iguais ao banco". `/query`, `/applyEdits` e os demais recursos
pertencem à linha L2-08 e NÃO estão aqui; quando ela chegar, o que se reaproveita é `esri.campos_para_esri` e
`esri.tipos_para_esri`, e esta rota passa a ser um pedaço do serviço dela, não um serviço à parte."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import db
from app.auth.sessao import Auth, autenticado
from app.dominios import esri, servico

router = APIRouter(tags=["featureserver"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
GEOMETRIA_ESRI = {
    "Point": "esriGeometryPoint",
    "MultiPoint": "esriGeometryMultipoint",
    "LineString": "esriGeometryPolyline",
    "MultiLineString": "esriGeometryPolyline",
    "Polygon": "esriGeometryPolygon",
    "MultiPolygon": "esriGeometryPolygon",
    "Geometry": "esriGeometryAny",
    "nenhuma": "esriGeometryNull",
}


def _montar(cur, item: dict) -> dict:
    dados = item["dados"] or {}
    item_id = str(item["id"])
    cur.execute(
        "SELECT dc.campo, dc.subtipo_codigo, d.nome, d.tipo, d.tipo_campo, d.descricao, d.valores "
        "FROM plat.dominio_campo dc JOIN plat.dominio d ON d.id = dc.dominio_id "
        "WHERE dc.item_id = %s::uuid",
        (item_id,),
    )
    por_campo: dict[str, dict] = {}
    por_subtipo: dict[int, dict[str, dict]] = {}
    for r in cur.fetchall():
        linha = {"nome": r["nome"], "tipo": r["tipo"], "tipo_campo": r["tipo_campo"],
                 "descricao": r["descricao"], "valores": r["valores"]}
        if r["subtipo_codigo"] is None:
            por_campo[r["campo"]] = linha
        else:
            por_subtipo.setdefault(int(r["subtipo_codigo"]), {})[r["campo"]] = linha
    cur.execute("SELECT campo, valores FROM plat.camada_subtipo WHERE item_id = %s::uuid", (item_id,))
    s = cur.fetchone()
    subtipo = {"campo": s["campo"], "valores": s["valores"]} if s else None
    campos = esri.campos_para_esri(dados.get("campos") or [], por_campo)
    return {
        "currentVersion": 11.4,
        "id": 0,
        "name": item["titulo"],
        "type": "Feature Layer",
        "description": item.get("descricao") or "",
        "geometryType": GEOMETRIA_ESRI.get(dados.get("geometria") or "Geometry", "esriGeometryAny"),
        "objectIdField": "fid",
        "globalIdField": "globalid",
        "typeIdField": (subtipo["campo"] if subtipo else ""),
        "fields": campos,
        "types": esri.tipos_para_esri(subtipo, por_subtipo),
        "templates": [],
        "capabilities": "Query",
        "extent": {"spatialReference": {"wkid": dados.get("srid") or 4326}},
        "supportsAttributeDomains": True,
    }


@router.get("/rest/services/{item_id}/FeatureServer", openapi_extra=LER)
def servico_de_feicao(item_id: str, f: str = Query(default="json", pattern="^json$"),
                      auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        camada = _montar(cur, item)
    return {
        "currentVersion": 11.4,
        "serviceDescription": item["resumo"] or "",
        "hasVersionedData": False,
        "supportsDisconnectedEditing": False,
        "layers": [{"id": 0, "name": camada["name"], "geometryType": camada["geometryType"]}],
        "tables": [],
    }


@router.get("/rest/services/{item_id}/FeatureServer/{camada}", openapi_extra=LER)
def camada_de_feicao(item_id: str, camada: int, f: str = Query(default="json", pattern="^json$"),
                     auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número."""
    from app.erros import ErroAPI

    if camada != 0:
        raise ErroAPI(404, "camada_inexistente", "esta camada não existe neste serviço")
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        return _montar(cur, item)
