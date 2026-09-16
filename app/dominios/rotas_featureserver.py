"""Exposição dos domínios e subtipos no FeatureServer (item L2-10-a).

`GET /rest/services/{item_id}/FeatureServer` e `.../FeatureServer/0` devolvem o recurso no formato que o
ArcGIS Pro e o Map Viewer leem, com `fields[].domain` e `types[]` montados do banco pelo `app/dominios/esri.py`.

Fronteira declarada: este módulo publica só o METADADO da camada — é o pedaço do FeatureServer de que o item
L2-10-a depende para provar "domains e types iguais ao banco". `/query`, `/applyEdits` e os demais recursos
pertencem à linha L2-08 e NÃO estão aqui; quando ela chegar, o que se reaproveita é `esri.campos_para_esri` e
`esri.tipos_para_esri`, e esta rota passa a ser um pedaço do serviço dela, não um serviço à parte.

Por ser registrado antes de `app.consulta.rotas_servico` em `app/main.py`, ESTE router é quem de fato
responde `GET .../FeatureServer` e `.../FeatureServer/0` (mesmo path, mesmo método — o de `rotas_servico`
fica sombreado). Por isso os campos de sincronização do item L2-04-k (`syncEnabled`/`syncCapabilities`/
`syncModel`/`syncCanReturnChanges`, mecanismo de `app/replica/servico.py`, item L2-13-b) têm de anunciar
AQUI, não lá — achado do conserto L7-03 (`laco/handoffs/T9/L7-03-autenticar-CONSERTO.md`)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import db
from app.auth.sessao import Auth, autenticado
from app.dominios import esri, servico

router = APIRouter(tags=["featureserver"])
LER = {"x-auth": "S/T", "x-privilegio": "proprio"}
# Mesmo dicionário citado pela fachada de sincronização Esri (item L2-04-k / L2-13-b): createReplica,
# synchronizeReplica, extractChanges e unRegisterReplica existem de verdade em rotas_sync_esri.py.
SYNC_CAPABILITIES = {
    "createReplica": True,
    "synchronizeReplica": True,
    "extractChanges": True,
    "unRegisterReplica": True,
}
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
        # Sync ENTRA (L2-04-k): createReplica/synchronizeReplica/extractChanges/unRegisterReplica
        # existem em app/consulta/rotas_sync_esri.py e usam o mecanismo do L2-13-b (app/replica/servico.py).
        "capabilities": "Query,Sync",
        "extent": {"spatialReference": {"wkid": dados.get("srid") or 4326}},
        "supportsAttributeDomains": True,
        "syncCanReturnChanges": True,
        "syncCapabilities": SYNC_CAPABILITIES,
        "syncModel": "perLayer",
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
        # item L2-04-k: réplica desconectada existe de verdade (app/replica/servico.py, item L2-13-b) —
        # ver docstring do módulo sobre por que é este descritor, e não o de app.consulta.rotas_servico,
        # que anuncia sync ao cliente Esri.
        "hasVersionedData": True,
        "supportsDisconnectedEditing": True,
        "syncEnabled": True,
        "capabilities": "Query,Sync",
        "syncCapabilities": SYNC_CAPABILITIES,
        "syncModel": "perLayer",
        "layers": [{"id": 0, "name": camada["name"], "geometryType": camada["geometryType"]}],
        "tables": [],
    }


@router.get("/rest/services/{item_id}/FeatureServer/{camada:int}", openapi_extra=LER)
def camada_de_feicao(item_id: str, camada: int, f: str = Query(default="json", pattern="^json$"),
                     auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número.

    O `:int` no molde do caminho (Starlette) é o conserto do achado de rotas: sem ele, `camada: int` só
    filtrava DEPOIS do roteamento escolher esta função (por ordem de registro em `app/main.py`, este
    router vem antes de `rotas_sync_esri`) — qualquer palavra de um segmento só (`/replicas`,
    `/createReplica`) caía aqui e morria com 422 de conversão, nunca chegando à rota certa do item
    L2-04-k. Com o conversor no molde, um segmento não-numérico deixa de casar aqui e o Starlette
    tenta a próxima rota registrada — sem precisar reordenar `app/main.py`."""
    from app.erros import ErroAPI

    if camada != 0:
        raise ErroAPI(404, "camada_inexistente", "esta camada não existe neste serviço")
    with db.db(auth.contexto()) as cur:
        item = servico.camada_ou_404(cur, item_id)
        return _montar(cur, item)
