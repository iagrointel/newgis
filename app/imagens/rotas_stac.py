"""STAC API por inquilino (item L1-01-a): `GET /svc/<token>/stac/...`. Autenticação SEMPRE por token de
serviço (nunca sessão/cookie — é a porta para ArcGIS Pro/QGIS/GDAL, não para o navegador), o MESMO
`plat.token_servico` de `/api/tokens`, só que lido do PATH em vez do cabeçalho `Authorization` (mesma
função `app.auth.sessao._auth_de_token`, reaproveitada — restrição de IP/referer, expiração, revogação e
pendência do dono continuam valendo do jeito que já valem para o resto da API).

Isolamento por inquilino (cláusula inegociável do item): NENHUM endpoint aceita `collections`/`ids` do
cliente sem primeiro interseccionar com `pgstac.colecoes_do_tenant` — ver app/imagens/pgstac.py. Coleção e
item de outro inquilino sempre respondem 404 (nunca 403: 403 confirmaria que existe)."""

from typing import Any

import psycopg2
from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import db, limites
from app.auth import escopos as esc
from app.auth.comum import erro_do_banco
from app.auth.sessao import _auth_de_token  # reaproveita o MESMO caminho de auth de token do /api (ADR 0002 §8)
from app.erros import ErroAPI
from app.imagens import pgstac as ps
from app.imagens import raster_item as ri
from app.settings import settings

router = APIRouter(tags=["stac"])
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}
X = {"x-auth": "T", "x-privilegio": "proprio"}

CONFORMES = (
    "https://api.stacspec.org/v1.0.0/core",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/item-search",
    "https://api.stacspec.org/v1.0.0/item-search#sort",
    "https://api.stacspec.org/v1.0.0/item-search#filter",
    "https://api.stacspec.org/v1.0.0/item-search#filter:cql2-json",
    "https://api.stacspec.org/v1.0.0/item-search#filter:basic-cql2",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/cql2/1.0/conf/cql2-json",
    "http://www.opengis.net/spec/cql2/1.0/conf/basic-cql2",
)


def _auth(request: Request, token: str):
    """Resolve o token do PATH (nunca do cabeçalho) pelo mesmo caminho de `/api`."""
    auth = _auth_de_token(request, token)
    request.state.auth = auth
    request.state.tenant_id = auth.tenant_id
    request.state.usuario_id = auth.usuario_id
    request.state.token_id = auth.token_id
    return auth


def _exigir_leitura(auth) -> None:
    if not esc.cobre(auth.escopos, "imagens:ler") and not esc.cobre(auth.escopos, "imagens:escrever"):
        raise ErroAPI(403, "escopo_insuficiente", "o token não tem o escopo imagens:ler nem imagens:escrever",
                      {"exigido": "imagens:ler", "token_tem": list(auth.escopos)})


def _exigir_escrita(auth) -> None:
    if not esc.cobre(auth.escopos, "imagens:escrever"):
        raise ErroAPI(403, "escopo_insuficiente", "o token não tem o escopo imagens:escrever",
                      {"exigido": "imagens:escrever", "token_tem": list(auth.escopos)})


def _base(token: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/svc/{token}/stac"


# ---------------------------------------------------------------- landing / conformance / serviço
@router.get("/svc/{token}/stac", include_in_schema=False, openapi_extra=X)
@router.get("/svc/{token}/stac/", openapi_extra=X)
def pouso(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    base = _base(token)
    corpo = {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": f"plat-imagens-{auth.tenant_slug}",
        "title": f"Catálogo de imagens — {auth.tenant_nome}",
        "description": "Catálogo STAC de imagens do inquilino, isolado por inquilino (pgstac + convenção "
        "de nome de coleção `<tenant_id>-<slug>`; item L1-01-a).",
        "conformsTo": list(CONFORMES),
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "root", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
            {
                "rel": "service-desc", "type": "application/vnd.oai.openapi+json;version=3.0",
                "href": f"{base}/api",
            },
            {"rel": "service-doc", "type": "text/html", "href": f"{base}/api.html"},
            {"rel": "search", "type": "application/geo+json", "href": f"{base}/search", "method": "GET"},
            {"rel": "search", "type": "application/geo+json", "href": f"{base}/search", "method": "POST"},
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/queryables",
                "type": "application/schema+json", "href": f"{base}/queryables",
            },
        ],
    }
    return JSONResponse(corpo, headers=SEM_CACHE)


@router.get("/svc/{token}/stac/conformance", openapi_extra=X)
def conformidade(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    return JSONResponse({"conformsTo": list(CONFORMES)}, headers=SEM_CACHE)


_OPENAPI_MINIMO = {
    "openapi": "3.0.3",
    "info": {"title": "STAC API — catálogo de imagens (item L1-01-a)", "version": "1.0.0"},
    "paths": {},
}


@router.get("/svc/{token}/stac/api", openapi_extra=X)
def servico_descricao(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    return JSONResponse(
        _OPENAPI_MINIMO,
        media_type="application/vnd.oai.openapi+json;version=3.0",
        headers=SEM_CACHE,
    )


@router.get("/svc/{token}/stac/api.html", include_in_schema=False)
def servico_descricao_html(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    return HTMLResponse(
        "<!doctype html><title>STAC API</title><p>Ver /svc/&lt;token&gt;/stac/api (OpenAPI).</p>", headers=SEM_CACHE
    )


# ---------------------------------------------------------------- coleções
def _colecao_link(base: str, colecao_id: str) -> list[dict]:
    return [
        {"rel": "self", "type": "application/json", "href": f"{base}/collections/{colecao_id}"},
        {"rel": "root", "type": "application/json", "href": f"{base}/"},
        {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{colecao_id}/items"},
        {"rel": "parent", "type": "application/json", "href": f"{base}/"},
        {
            "rel": "queryables", "type": "application/schema+json",
            "href": f"{base}/collections/{colecao_id}/queryables",
        },
    ]


@router.get("/svc/{token}/stac/collections", openapi_extra=X)
def colecoes(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    base = _base(token)
    with db.db(auth.contexto()) as cur:
        conteudos = ps.colecoes_listar(cur, auth.tenant_id)
    saida = []
    for c in conteudos:
        c = {**c, "links": [*c.get("links", []), *_colecao_link(base, c["id"])]}
        saida.append(c)
    corpo = {
        "collections": saida,
        "links": [{"rel": "self", "type": "application/json", "href": f"{base}/collections"}],
    }
    return JSONResponse(corpo, headers=SEM_CACHE)


@router.post("/svc/{token}/stac/collections", status_code=201, openapi_extra=X)
def colecao_criar(token: str, request: Request, corpo: dict = Body(...), slug: str = Query(...)):
    auth = _auth(request, token)
    _exigir_escrita(auth)
    try:
        with db.db(auth.contexto()) as cur:
            cur.execute("SELECT count(*) AS n FROM pgstac.collections WHERE id LIKE %s", (f"{auth.tenant_id}-%",))
            if cur.fetchone()["n"] >= limites.STAC_COLECOES_POR_INQUILINO:
                raise ErroAPI(
                    422, "limite_colecoes",
                    f"no máximo {limites.STAC_COLECOES_POR_INQUILINO} coleções por inquilino",
                )
            conteudo = ps.colecao_criar(cur, auth.tenant_id, slug, corpo)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    base = _base(token)
    return JSONResponse(
        {**conteudo, "links": [*conteudo.get("links", []), *_colecao_link(base, conteudo["id"])]},
        status_code=201, headers=SEM_CACHE,
    )


@router.get("/svc/{token}/stac/collections/{colecao_id}", openapi_extra=X)
def colecao_ver(token: str, colecao_id: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    with db.db(auth.contexto()) as cur:
        conteudo = ps.colecao_obter(cur, auth.tenant_id, colecao_id)
    if conteudo is None:
        raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
    base = _base(token)
    return JSONResponse(
        {**conteudo, "links": [*conteudo.get("links", []), *_colecao_link(base, colecao_id)]}, headers=SEM_CACHE
    )


@router.get("/svc/{token}/stac/collections/{colecao_id}/queryables", openapi_extra=X)
def colecao_queryables(token: str, colecao_id: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    with db.db(auth.contexto()) as cur:
        if ps.colecao_obter(cur, auth.tenant_id, colecao_id) is None:
            raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
        q = ps.queryables(cur, colecao_id)
    return JSONResponse(q, media_type="application/schema+json", headers=SEM_CACHE)


@router.get("/svc/{token}/stac/queryables", openapi_extra=X)
def queryables_globais(token: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    with db.db(auth.contexto()) as cur:
        q = ps.queryables(cur, None)
    return JSONResponse(q, media_type="application/schema+json", headers=SEM_CACHE)


# ---------------------------------------------------------------- itens
@router.get("/svc/{token}/stac/collections/{colecao_id}/items", openapi_extra=X)
def itens_listar(
    token: str, colecao_id: str, request: Request,
    limit: int = Query(limites.STAC_PAGINA_PADRAO, ge=1),
    bbox: str | None = None, datetime: str | None = None, next: str | None = Query(None, alias="token"),
):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    try:
        bbox_lista = [float(x) for x in bbox.split(",")] if bbox else None
    except ValueError as e:
        raise ErroAPI(422, "bbox_invalido", f"bbox precisa ser números separados por vírgula: {e}") from e
    with db.db(auth.contexto()) as cur:
        if ps.colecao_obter(cur, auth.tenant_id, colecao_id) is None:
            raise ErroAPI(404, "colecao_inexistente", "coleção inexistente")
        payload = ps.parametros_busca(
            auth.tenant_id, cur, collections=[colecao_id],
            bbox=bbox_lista, datetime_=datetime, limit=limit, token=next,
        )
        resultado = ps.buscar(cur, payload)
    base = _base(token)
    return _resposta_busca(resultado, base, f"{base}/collections/{colecao_id}/items")


@router.get("/svc/{token}/stac/collections/{colecao_id}/items/{item_id}", openapi_extra=X)
def item_ver(token: str, colecao_id: str, item_id: str, request: Request):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    with db.db(auth.contexto()) as cur:
        conteudo = ps.item_obter(cur, auth.tenant_id, colecao_id, item_id)
    if conteudo is None:
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    base = _base(token)
    conteudo = {
        **conteudo,
        "links": [
            *conteudo.get("links", []),
            {"rel": "self", "type": "application/geo+json",
             "href": f"{base}/collections/{colecao_id}/items/{item_id}"},
            {"rel": "collection", "type": "application/json", "href": f"{base}/collections/{colecao_id}"},
            {"rel": "root", "type": "application/json", "href": f"{base}/"},
        ],
    }
    return JSONResponse(conteudo, media_type="application/geo+json", headers=SEM_CACHE)


@router.post("/svc/{token}/stac/collections/{colecao_id}/items", status_code=201, openapi_extra=X)
def item_criar(token: str, colecao_id: str, request: Request, corpo: dict = Body(...)):
    auth = _auth(request, token)
    _exigir_escrita(auth)
    raster = corpo.pop("raster", None)
    try:
        with db.db(auth.contexto()) as cur:
            conteudo = ps.item_criar(cur, auth.tenant_id, colecao_id, corpo)
            ri.espelhar(cur, auth.tenant_id, colecao_id, conteudo["id"], raster)
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e
    base = _base(token)
    return JSONResponse(
        {**conteudo, "links": [{"rel": "self", "type": "application/geo+json",
                                 "href": f"{base}/collections/{colecao_id}/items/{conteudo['id']}"}]},
        status_code=201, headers=SEM_CACHE,
    )


# ---------------------------------------------------------------- busca (item-search)
def _resposta_busca(resultado: dict, base: str, self_href: str) -> JSONResponse:
    links = [
        {"rel": "self", "type": "application/geo+json", "href": self_href},
        {"rel": "root", "type": "application/json", "href": f"{base}/"},
    ]
    for link in resultado.get("links", []):
        if link.get("rel") in ("next", "prev"):
            href = link["href"]
            marcador = href.split("token=", 1)[1] if "token=" in href else None
            if marcador:
                links.append({**link, "href": f"{self_href}?token={marcador}"})
    corpo = {**resultado, "links": links}
    return JSONResponse(corpo, media_type="application/geo+json", headers=SEM_CACHE)


def _corpo_busca_get(
    collections: str | None, ids: str | None, bbox: str | None, intersects: str | None, datetime: str | None,
    limit: int, token_pag: str | None, sortby: str | None, filtro: str | None, filtro_lang: str | None,
) -> dict[str, Any]:
    import json as _json

    saida: dict[str, Any] = {}
    if collections:
        saida["collections"] = collections.split(",")
    if ids:
        saida["ids"] = ids.split(",")
    if bbox:
        saida["bbox"] = [float(x) for x in bbox.split(",")]
    if intersects:
        saida["intersects"] = _json.loads(intersects)
    if datetime:
        saida["datetime_"] = datetime
    saida["limit"] = limit
    if token_pag:
        saida["token"] = token_pag
    if sortby:
        # GET usa texto simples "-campo,+campo" (STAC API Sort Extension, forma GET); "-" = desc.
        saida["sortby"] = [
            {"field": s[1:] if s[:1] in "+-" else s, "direction": "desc" if s.startswith("-") else "asc"}
            for s in sortby.split(",") if s
        ]
    if filtro:
        saida["filtro"] = _json.loads(filtro)
        saida["filtro_lang"] = filtro_lang or "cql2-json"
    return saida


@router.get("/svc/{token}/stac/search", openapi_extra=X)
def busca_get(
    token: str, request: Request,
    collections: str | None = None, ids: str | None = None, bbox: str | None = None,
    intersects: str | None = None,
    datetime: str | None = None, limit: int = Query(limites.STAC_PAGINA_PADRAO, ge=1),
    next: str | None = Query(None, alias="token"), sortby: str | None = None,
    filter: str | None = None, filter_lang: str | None = Query(None, alias="filter-lang"),
):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    try:
        args = _corpo_busca_get(
            collections, ids, bbox, intersects, datetime, limit, next, sortby, filter, filter_lang
        )
    except (ValueError, TypeError) as e:
        raise ErroAPI(422, "parametro_invalido", f"parâmetro de busca inválido: {e}") from e
    with db.db(auth.contexto()) as cur:
        payload = ps.parametros_busca(auth.tenant_id, cur, **args)
        resultado = ps.buscar(cur, payload)
    base = _base(token)
    return _resposta_busca(resultado, base, f"{base}/search")


@router.post("/svc/{token}/stac/search", openapi_extra=X)
def busca_post(token: str, request: Request, corpo: dict = Body(default={})):
    auth = _auth(request, token)
    _exigir_leitura(auth)
    with db.db(auth.contexto()) as cur:
        payload = ps.parametros_busca(
            auth.tenant_id, cur,
            collections=corpo.get("collections"), ids=corpo.get("ids"), bbox=corpo.get("bbox"),
            intersects=corpo.get("intersects"),
            datetime_=corpo.get("datetime"), limit=corpo.get("limit", limites.STAC_PAGINA_PADRAO),
            token=corpo.get("token"), sortby=corpo.get("sortby"),
            filtro=corpo.get("filter"), filtro_lang=corpo.get("filter-lang"),
            fields=corpo.get("fields"), query=corpo.get("query"),
        )
        resultado = ps.buscar(cur, payload)
    base = _base(token)
    return _resposta_busca(resultado, base, f"{base}/search")
