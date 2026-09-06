"""Catálogo externo por protocolo padrão (item L0-09-metadado-catalogo; D17 do L0_CONCEITO: "catálogo externo
OGC API Records + CSW próprio"). Esta passagem entrega só **OGC API Records** (Parte 1: Core, OGC 20-004r1);
CSW fica registrado como pendência em docs/PARIDADE.md — ver a justificativa abaixo.

Por que OGC API Records e não CSW nesta passagem:
1. Toda a API deste repositório já é JSON sobre HTTP com o mesmo contrato de autenticação (sessão ou
   `Authorization: Bearer` com escopo, ADR 0002 seção 8). OGC API Records é o MESMO estilo (JSON, OpenAPI);
   CSW é SOAP/XML-RPC-like (GetCapabilities/DescribeRecord/GetRecords em XML, com uma linguagem de filtro
   própria, OGC Filter Encoding ou CQL). Entregar CSW exigiria um parser de requisição e uma gramática de
   filtro que não existem nesta base — risco alto para o tempo do turno.
2. RAM desta máquina está no limite (23 GB, ~2 GB livres medido 05-06/09): um serviço CSW correto (ex.
   pycsw) não está instalado e instalá-lo como processo à parte não cabe no orçamento do item.
3. OGC API Records é a linha ativa do OGC (Records 1.0, 2024) enquanto CSW 2.0.2 é legado; clientes novos
   (STAC/pygeoapi/QGIS recente) falam a API REST primeiro.
Custo de mudar: médio — um roteador novo (`rotas_csw.py`) com GetCapabilities (XML estático + template) e
GetRecords (tradução do corpo XML/KVP para os mesmos `listar_ids`/`carregar_varios` que este módulo já usa);
a busca e a autenticação por token já servem os dois protocolos sem mudança.

Autenticação: sempre `catalogo:ler` (sessão OU token de serviço do L0-02, `app/auth/escopos.py`) — nunca
anônimo, mesmo na página de pouso/conformance (regra do item: "nunca aberto"). Isolamento por inquilino vem
de graça da RLS de `plat.item` (o mesmo mecanismo de `GET /api/itens`), não de um filtro escrito aqui: os
`ids` de `listar_ids`/`carregar_varios` já saem só do `tenant_id` do contexto (`auth.contexto()`).

Escopo "básico" (o que o portão pede): paisagem (landing), `/conformance`, uma coleção (`catalogo` — o
catálogo inteiro do inquilino; dividir por tipo/família fica para quando um cliente pedir), `/items` com os
mesmos filtros simples que `GET /api/itens` (q, bbox, tipo, tags, limit/offset — sem CQL2, sem `sortby`,
sem `queryables`; por isso a lista de conformance abaixo cita só Core+JSON, não Filter/Sorting/Queryables)."""

import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.catalogo.rotas_itens import _params_lista, carregar_varios, listar_ids
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/ogc/records", tags=["ogc-records"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
CONFORMANCE = (
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
    "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/json",
)
COLECAO_ID = "catalogo"


def _base(request: Request) -> str:
    return (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/") + "/ogc/records"


def _colecao_json(base: str) -> dict:
    return {
        "id": COLECAO_ID,
        "title": "Catálogo da plataforma",
        "description": "Itens do catálogo de conteúdo (mapas, camadas, estilos, aplicações, conexões e demais "
        "tipos registrados) visíveis para o inquilino do token/sessão que autenticou o pedido.",
        "itemType": "record",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/collections/{COLECAO_ID}"},
            {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{COLECAO_ID}/items"},
        ],
    }


def _extent_geojson(extent: list[float] | None) -> dict | None:
    if not extent:
        return None
    xmin, ymin, xmax, ymax = extent
    return {
        "type": "Polygon",
        "coordinates": [[[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]],
    }


def _registro(item: dict, base: str) -> dict:
    """Item já serializado por `item_json` (completo ou não) -> registro OGC API Records (perfil GeoJSON)."""
    iid = item["id"]
    base_api = settings.PLAT_URL_PUBLICA.rstrip("/")
    props = {
        "type": item["tipo"],
        "title": item["titulo"],
        "description": item.get("resumo") or item.get("descricao"),
        "keywords": item.get("tags") or [],
        "language": {"code": "por"},
        "created": item.get("criado_em"),
        "updated": item.get("modificado_em"),
        "externalIds": [{"scheme": "plat", "value": iid}],
    }
    if item.get("creditos"):
        props["rights"] = item["creditos"]
    return {
        "type": "Feature",
        "id": iid,
        "geometry": _extent_geojson(item.get("extent")),
        "time": None,
        "properties": {k: v for k, v in props.items() if v is not None},
        "links": [
            {"rel": "self", "type": "application/geo+json", "href": f"{base}/collections/{COLECAO_ID}/items/{iid}"},
            {"rel": "alternate", "type": "application/json", "href": f"{base_api}/api/itens/{iid}"},
            {
                "rel": "alternate",
                "type": "application/xml",
                "title": "ISO 19139",
                "href": f"{base_api}/api/itens/{iid}/metadado.xml",
            },
        ],
    }


@router.get("", openapi_extra=LER)
@router.get("/", openapi_extra=LER, include_in_schema=False)
def pouso(request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    base = _base(request)
    return {
        "title": "Catálogo OGC API Records — plataforma",
        "description": "Descoberta de itens do catálogo por protocolo padrão OGC, autenticada (nunca aberta).",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
        ],
    }


@router.get("/conformance", openapi_extra=LER)
def conformidade(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    return {"conformsTo": list(CONFORMANCE)}


@router.get("/collections", openapi_extra=LER)
def colecoes(request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    base = _base(request)
    return {
        "collections": [_colecao_json(base)],
        "links": [{"rel": "self", "type": "application/json", "href": f"{base}/collections"}],
    }


@router.get("/collections/{colecao_id}", openapi_extra=LER)
def colecao(colecao_id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
    return _colecao_json(_base(request))


@router.get("/collections/{colecao_id}/items", openapi_extra=LER)
def itens_da_colecao(
    colecao_id: str,
    request: Request,
    q: str | None = None,
    bbox: str | None = None,
    tipo: list[str] | None = Query(None),
    tags: list[str] | None = Query(None),
    limit: int | None = None,
    offset: int | None = None,
    cursor: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """GetRecords equivalente: mesmos filtros simples de `GET /api/itens` (q, bbox, tipo, tags); paginação
    `limit`/`offset` no vocabulário OGC (mapeados aos `limite`/`deslocamento` internos), `cursor` para a
    página seguinte (link `rel=next`). RLS de `plat.item` garante que só itens do inquilino do token/sessão
    aparecem — nunca de outro (refutação do item)."""
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
    base = _base(request)
    p = _params_lista(request, limit, offset)
    with db.db(auth.contexto()) as cur:
        total, ids, proximo, _aprox = listar_ids(cur, auth, p)
        itens = carregar_varios(cur, ids, auth)
    links = [
        {"rel": "self", "type": "application/geo+json", "href": f"{base}/collections/{COLECAO_ID}/items"},
    ]
    if proximo:
        links.append(
            {
                "rel": "next",
                "type": "application/geo+json",
                "href": f"{base}/collections/{COLECAO_ID}/items?cursor={proximo}",
            }
        )
    corpo = {
        "type": "FeatureCollection",
        "timeStamp": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "numberMatched": total,
        "numberReturned": len(itens),
        "links": links,
        "features": [_registro(i, base) for i in itens],
    }
    return JSONResponse(corpo, media_type="application/geo+json")


@router.get("/collections/{colecao_id}/items/{item_id}", openapi_extra=LER)
def item_da_colecao(
    colecao_id: str, item_id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")
):
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
    from app.catalogo.comum import item_json

    with db.db(auth.contexto()) as cur:
        r = comum.item_ou_404(cur, item_id)
        j = item_json(r, auth, completo=True)
    return JSONResponse(_registro(j, _base(request)), media_type="application/geo+json")
