"""OGC API Features — Part 1: Core (OGC 17-069r4) sobre a MESMA camada hospedada e o MESMO motor de
consulta do FeatureServer (item L2-04-c/ADR 0018): nada de segundo caminho de SQL — `PedidoQuery` +
`motor.preparar_pedido`/`executar_features`/`executar_count` são reusados tal como estão; este módulo
só traduz o vocabulário OGC (bbox, limit, `application/geo+json`) para o `PedidoQuery` que o motor já
entende e devolve GeoJSON puro (via `serializar.como_geojson`), nunca o vocabulário Esri.

Uma coleção por item, id fixo `"0"` — a mesma restrição de uma-camada-por-item que o FeatureServer já
declara (`rotas_query._query`); a URL raiz é por item (`/ogc/features/{item_id}`, não um catálogo
único) porque o modelo desta plataforma publica cada camada como um serviço próprio, exatamente como
o FeatureServer. Autenticação: sessão OU token de serviço `camada:ler` (reusa `rotas_query._autenticar`
— mesma regra, mesmo RLS; nenhum caminho novo de autorização).

Cobertura desta passagem (feito/parcial/fora vive em `docs/PARIDADE.md`):
  feito    - landing, /conformance (classe `core`+`geojson`), /collections, /collections/{id},
             /collections/{id}/items (bbox, limit, com `numberMatched`/`numberReturned`/links de
             paginação `next`/`prev` por offset), /collections/{id}/items/{featureId}.
  fora     - filtro CQL2 (Part 3, item L2-04-g próprio), CRS diferente de CRS84/4326 (Part 2), HTML
             (conf/html), Part 4 Create/Replace/Update/Delete (depende de L2-03-a, não construído).
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import db
from app.consulta import campos as campos_mod
from app.consulta import motor
from app.consulta.rotas_query import _autenticar
from app.consulta.rotas_servico import _camada_e_titulo
from app.consulta.serializar import GEOM_PG_PARA_ESRI, como_geojson
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/ogc/features/{item_id}", tags=["ogc-features"])
COLECAO_ID = "0"
CONFORMANCE = (
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
)
LIMITE_PADRAO = 100
LIMITE_TETO = 2000  # mesmo teto de maxRecordCount do FeatureServer (item L2-04-c)


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/ogc/features/{item_id}"


def _carregar(cur, item_id: str):
    dados, titulo = _camada_e_titulo(cur, item_id)
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    meta = campos_mod.campos_da_camada(cur, schema, tabela)
    geometria_tipo_esri = GEOM_PG_PARA_ESRI.get(dados.get("geometria"))
    return schema, tabela, srid, meta, geometria_tipo_esri, titulo


def _colecao_json(base: str, item_id: str, titulo: str | None, extent4326: list[float] | None) -> dict:
    d = {
        "id": COLECAO_ID,
        "title": titulo or item_id,
        "itemType": "feature",
        "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/collections/{COLECAO_ID}"},
            {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{COLECAO_ID}/items"},
        ],
    }
    if extent4326:
        d["extent"] = {"spatial": {"bbox": [extent4326], "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}}
    return d


@router.get("", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}, operation_id="ogc_features_pouso")
@router.get("/", include_in_schema=False, openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_pouso_barra")
def pouso(item_id: str, request: Request):
    auth = _autenticar(request, item_id)
    # achado do adversário (bateria de ataque desta trilha): _autenticar só confere ESCOPO, não se o
    # item existe e pertence ao inquilino do contexto -- sem esta consulta, um item_id de outro
    # inquilino (ou lixo qualquer) devolvia 200 com a landing page (nunca dado do outro inquilino,
    # mas ainda assim o comportamento certo é 404, igual ao FeatureServer/WFS, que já tocam o banco
    # aqui embaixo). RLS de `plat.item` faz o filtro de verdade.
    with db.db(auth.contexto()) as cur:
        _carregar(cur, item_id)
    base = _base(request, item_id)
    return {
        "title": f"OGC API Features — {item_id}",
        "description": "Camada hospedada da plataforma, servida por OGC API Features Part 1 (Core). "
        "Análise/beta privado.",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
        ],
    }


@router.get("/conformance", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_conformidade")
def conformidade(item_id: str, request: Request):
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, item_id)
    return {"conformsTo": list(CONFORMANCE)}


@router.get("/collections", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_colecoes")
def colecoes(item_id: str, request: Request):
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        _, _, _, _, _, titulo = _carregar(cur, item_id)
        cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, ST_YMax(extent) y1 "
                    "FROM plat.item WHERE id=%s::uuid", (item_id,))
        r = cur.fetchone()
    extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
    return {"collections": [_colecao_json(base, item_id, titulo, extent)],
            "links": [{"rel": "self", "type": "application/json", "href": f"{base}/collections"}]}


@router.get("/collections/{colecao_id}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_colecao")
def colecao(item_id: str, colecao_id: str, request: Request):
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "esta implementação publica uma coleção só (id 0) por item")
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        _, _, _, _, _, titulo = _carregar(cur, item_id)
        cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, ST_YMax(extent) y1 "
                    "FROM plat.item WHERE id=%s::uuid", (item_id,))
        r = cur.fetchone()
    extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
    return _colecao_json(base, item_id, titulo, extent)


def _bbox_para_pedido(bbox: str | None) -> dict:
    if not bbox:
        return {}
    partes = bbox.split(",")
    if len(partes) not in (4, 6):
        raise ErroAPI(400, "bbox_invalido", "bbox precisa de 4 (2D) ou 6 (3D) números, vírgula-separados")
    if len(partes) == 6:  # ignora minz/maxz — geometria de trabalho é 2D (declarado no C11 do L2_CONCEITO)
        partes = [partes[0], partes[1], partes[3], partes[4]]
    return {"geometry": ",".join(partes), "geometryType": "esriGeometryEnvelope", "inSR": 4326}


@router.get("/collections/{colecao_id}/items", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_items")
def items(
    item_id: str, colecao_id: str, request: Request,
    bbox: str | None = None,
    limit: int | None = Query(None, ge=1),
    offset: int | None = Query(None, ge=0),
):
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "esta implementação publica uma coleção só (id 0) por item")
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    limite = min(limit or LIMITE_PADRAO, LIMITE_TETO)
    deslocamento = offset or 0
    with db.db(auth.contexto()) as cur:
        schema, tabela, srid, meta, geom_esri, _ = _carregar(cur, item_id)
        kwargs = _bbox_para_pedido(bbox)
        p = motor.PedidoQuery(outFields="*", resultRecordCount=limite, resultOffset=deslocamento, **kwargs)
        prep = motor.preparar_pedido(p, meta, srid)
        res = motor.executar_features(cur, schema, tabela, prep, p, meta, srid, geom_esri)
        total = motor.executar_count(cur, schema, tabela, prep).count
    corpo = como_geojson(res)
    corpo["numberMatched"] = total
    corpo["numberReturned"] = len(res.features)
    corpo["timeStamp"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    links = [{"rel": "self", "type": "application/geo+json",
              "href": f"{base}/collections/{colecao_id}/items"}]
    if deslocamento + len(res.features) < total:
        links.append({"rel": "next", "type": "application/geo+json",
                       "href": f"{base}/collections/{colecao_id}/items?limit={limite}&offset={deslocamento + limite}"
                               + (f"&bbox={bbox}" if bbox else "")})
    if deslocamento > 0:
        links.append({"rel": "prev", "type": "application/geo+json",
                       "href": f"{base}/collections/{colecao_id}/items?limit={limite}"
                               f"&offset={max(0, deslocamento - limite)}" + (f"&bbox={bbox}" if bbox else "")})
    corpo["links"] = links
    return JSONResponse(corpo, media_type="application/geo+json")


@router.get("/collections/{colecao_id}/items/{feature_id}",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}, operation_id="ogc_features_item")
def item_um(item_id: str, colecao_id: str, feature_id: str, request: Request):
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "esta implementação publica uma coleção só (id 0) por item")
    if not feature_id.lstrip("-").isdigit():
        raise ErroAPI(400, "feature_id_invalido", "id da feição precisa ser o OID inteiro (fid)")
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        schema, tabela, srid, meta, geom_esri, _ = _carregar(cur, item_id)
        p = motor.PedidoQuery(outFields="*", objectIds=feature_id)
        prep = motor.preparar_pedido(p, meta, srid)
        res = motor.executar_features(cur, schema, tabela, prep, p, meta, srid, geom_esri)
    if not res.features:
        raise ErroAPI(404, "feicao_nao_encontrada", f"nenhuma feição com id {feature_id!r}")
    corpo = como_geojson(res)
    feicao = corpo["features"][0]
    feicao["links"] = [{"rel": "self", "type": "application/geo+json",
                         "href": f"{base}/collections/{colecao_id}/items/{feature_id}"}]
    return JSONResponse(feicao, media_type="application/geo+json")
