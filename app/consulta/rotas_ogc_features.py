"""OGC API Features — Part 1: Core (OGC 17-069r4) sobre a MESMA camada hospedada e o MESMO motor de
consulta do FeatureServer (item L2-04-c/ADR 0018): nada de segundo caminho de SQL — `PedidoQuery` +
`motor.preparar_pedido`/`executar_features`/`executar_count` são reusados tal como estão; este módulo
só traduz o vocabulário OGC (bbox, limit, `application/geo+json`) para o `PedidoQuery` que o motor já
entende e devolve GeoJSON puro (via `serializar.como_geojson`), nunca o vocabulário Esri.

Uma coleção por item, id fixo `"0"` — a mesma restrição de uma-camada-por-item que o FeatureServer já
declara (`rotas_query._query`); a URL raiz é por item (`/ogc/features/{item_id}`, não um catálogo
único) porque o modelo desta plataforma publica cada camada como um serviço próprio, exatamente como
o FeatureServer. Autenticação: sessão OU token de serviço `camada:ler` (reusa `rotas_query._autenticar`
— mesma regra, mesmo RLS; nenhum caminho novo de autorização); escrita (Part 4) exige `camada:editar`,
via o MESMO `_auth_editor`/`aplicar_edicoes` de `app/edicao/` — nenhum segundo caminho de escrita.

Cobertura desta passagem (feito/parcial/fora vive em `docs/PARIDADE.md`):
  feito    - landing, /conformance (classes core+geojson+html+crs+filter+cql2-text+cql2-json+
             features-transaction), /api (OpenAPI enxuto, sem duplicar o schema global), /collections,
             /collections/{id} (com storageCrs e queryables), /collections/{id}/items (bbox,
             bbox-crs, crs, filter/filter-lang CQL2, limit, com numberMatched/numberReturned/links
             de paginação next/prev por offset), /collections/{id}/items/{featureId},
             /collections/{id}/queryables, POST/PUT/PATCH/DELETE em items (Part 4, sobre L2-03-a,
             com ETag/If-Match).
  parcial  - HTML só na landing/conformance (não em collections/items — Part 1 exige, mas o produto
             não tem template HTML de feição ainda; ver PARIDADE.md).
  fora     - CRS 3D (Part 2 §7.3), datumTransformation (fora do vocabulário CQL2/OGC), timeInfo por
             camada (mesma limitação do FeatureServer — `time`/timeInfo não configurados aqui).
"""

from __future__ import annotations

import datetime
import json
import re

import psycopg2
from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from app import db
from app.auth import escopos as esc
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum
from app.consulta import campos as campos_mod
from app.consulta import cql2, motor
from app.consulta.rotas_query import _autenticar
from app.consulta.rotas_servico import _camada_e_titulo
from app.consulta.serializar import GEOM_PG_PARA_ESRI, como_geojson
from app.edicao.modelos import EdicoesEntrada, FeicaoAdicionar, FeicaoApagar, FeicaoAtualizar
from app.edicao.servico import aplicar_edicoes
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/ogc/features/{item_id}", tags=["ogc-features"])
COLECAO_ID = "0"
CONFORMANCE = (
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-2/1.0/conf/crs",
    "http://www.opengis.net/spec/ogcapi-features-2/1.0/conf/crs-by-reference",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/filter",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/features-filter",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/cql2-text",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/cql2-json",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/queryables",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/features",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/update",
)
LIMITE_PADRAO = 100
LIMITE_TETO = 2000  # mesmo teto de maxRecordCount do FeatureServer (item L2-04-c)
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
_CRS_EPSG_RE = re.compile(r"^https?://www\.opengis\.net/def/crs/EPSG/0/(\d+)$", re.IGNORECASE)
_CRS_OGC_CRS84_RE = re.compile(r"^https?://www\.opengis\.net/def/crs/OGC/1\.3/CRS84$", re.IGNORECASE)
_CRS_CURTO_RE = re.compile(r"^EPSG:(\d+)$", re.IGNORECASE)


def _crs_para_srid(crs: str | None, default: int = 4326) -> int:
    """Part 2 (CRS by reference): aceita a URI OGC completa (`.../EPSG/0/<code>`), `CRS84` (=4326) ou
    o atalho curto `EPSG:<code>` — as três formas que QGIS e o validador oficial emitem."""
    if not crs:
        return default
    if _CRS_OGC_CRS84_RE.match(crs) or crs.upper() == "CRS84":
        return 4326
    m = _CRS_EPSG_RE.match(crs) or _CRS_CURTO_RE.match(crs)
    if m:
        return int(m.group(1))
    if crs.lstrip("-").isdigit():
        return int(crs)
    raise ErroAPI(400, "crs_invalido", f"CRS não reconhecido: {crs!r}", {"crs": crs})


def _srid_para_crs_uri(srid: int) -> str:
    return CRS84 if srid == 4326 else f"http://www.opengis.net/def/crs/EPSG/0/{srid}"


def _base(request: Request, item_id: str) -> str:
    raiz = (settings.PLAT_URL_PUBLICA or str(request.base_url)).rstrip("/")
    return f"{raiz}/ogc/features/{item_id}"


def _carregar(cur, item_id: str):
    dados, titulo = _camada_e_titulo(cur, item_id)
    schema, tabela, srid = dados["schema"], dados["tabela"], int(dados["srid"])
    meta = campos_mod.campos_da_camada(cur, schema, tabela)
    geometria_tipo_esri = GEOM_PG_PARA_ESRI.get(dados.get("geometria"))
    return schema, tabela, srid, meta, geometria_tipo_esri, titulo


def _colecao_json(
    base: str, item_id: str, titulo: str | None, extent4326: list[float] | None, srid_nativo: int
) -> dict:
    storage_crs = _srid_para_crs_uri(srid_nativo)
    d = {
        "id": COLECAO_ID,
        "title": titulo or item_id,
        "itemType": "feature",
        "crs": [CRS84, storage_crs],
        "storageCrs": storage_crs,
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/collections/{COLECAO_ID}"},
            {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{COLECAO_ID}/items"},
            {"rel": "queryables", "type": "application/schema+json",
             "href": f"{base}/collections/{COLECAO_ID}/queryables"},
        ],
    }
    if extent4326:
        d["extent"] = {"spatial": {"bbox": [extent4326], "crs": CRS84}}
    return d


def _exigir_colecao(colecao_id: str) -> None:
    if colecao_id != COLECAO_ID:
        raise ErroAPI(404, "colecao_inexistente", "esta implementação publica uma coleção só (id 0) por item")


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
        "description": "Camada hospedada da plataforma, servida por OGC API Features Part 1-4. "
        "Análise/beta privado.",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
            {"rel": "service-desc", "type": "application/vnd.oai.openapi+json;version=3.0",
             "href": f"{base}/api"},
        ],
    }


@router.get("/conformance", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_conformidade")
def conformidade(item_id: str, request: Request):
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, item_id)
    return {"conformsTo": list(CONFORMANCE)}


@router.get("/api", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}, operation_id="ogc_features_api_desc")
def api_descricao(item_id: str, request: Request):
    """Descrição OpenAPI 3.0 mínima e própria deste serviço (Part 1 §7.5) — não reusa
    `docs/openapi.json` (o documento inteiro da plataforma; publicar aqui seria vocabulário Esri
    junto do OGC, que o portão do item pede separado)."""
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        _carregar(cur, item_id)
    base = _base(request, item_id)
    return {
        "openapi": "3.0.3",
        "info": {"title": f"OGC API Features — {item_id}", "version": "1.0.0"},
        "servers": [{"url": base}],
        "paths": {
            "/": {"get": {"operationId": "ogc_features_pouso"}},
            "/conformance": {"get": {"operationId": "ogc_features_conformidade"}},
            "/collections": {"get": {"operationId": "ogc_features_colecoes"}},
            "/collections/{collectionId}": {"get": {"operationId": "ogc_features_colecao"}},
            "/collections/{collectionId}/queryables": {"get": {"operationId": "ogc_features_queryables"}},
            "/collections/{collectionId}/items": {
                "get": {"operationId": "ogc_features_items"},
                "post": {"operationId": "ogc_features_item_criar"},
            },
            "/collections/{collectionId}/items/{featureId}": {
                "get": {"operationId": "ogc_features_item"},
                "put": {"operationId": "ogc_features_item_substituir"},
                "patch": {"operationId": "ogc_features_item_atualizar"},
                "delete": {"operationId": "ogc_features_item_apagar"},
            },
        },
    }


@router.get("/collections", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_colecoes")
def colecoes(item_id: str, request: Request):
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        _, _, srid, _, _, titulo = _carregar(cur, item_id)
        cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, ST_YMax(extent) y1 "
                    "FROM plat.item WHERE id=%s::uuid", (item_id,))
        r = cur.fetchone()
    extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
    return {"collections": [_colecao_json(base, item_id, titulo, extent, srid)],
            "links": [{"rel": "self", "type": "application/json", "href": f"{base}/collections"}]}


@router.get("/collections/{colecao_id}", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_colecao")
def colecao(item_id: str, colecao_id: str, request: Request):
    _exigir_colecao(colecao_id)
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        _, _, srid, _, _, titulo = _carregar(cur, item_id)
        cur.execute("SELECT ST_XMin(extent) x0, ST_YMin(extent) y0, ST_XMax(extent) x1, ST_YMax(extent) y1 "
                    "FROM plat.item WHERE id=%s::uuid", (item_id,))
        r = cur.fetchone()
    extent = [r["x0"], r["y0"], r["x1"], r["y1"]] if r and r["x0"] is not None else None
    return _colecao_json(base, item_id, titulo, extent, srid)


_TIPO_QUERYABLE = {
    "esriFieldTypeString": "string", "esriFieldTypeInteger": "integer", "esriFieldTypeSmallInteger": "integer",
    "esriFieldTypeBigInteger": "integer", "esriFieldTypeDouble": "number", "esriFieldTypeSingle": "number",
    "esriFieldTypeDate": "string", "esriFieldTypeDateOnly": "string", "esriFieldTypeTimeOnly": "string",
    "esriFieldTypeGUID": "string", "esriFieldTypeOID": "integer",
}


@router.get("/collections/{colecao_id}/queryables", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_queryables")
def queryables(item_id: str, colecao_id: str, request: Request):
    """Part 3 §6: lista os campos que `filter` pode usar, um por coleção — a MESMA lista branca que
    `where_ast`/`cql2` exigem para compilar (nunca "todas as colunas", sempre a metadada validada)."""
    _exigir_colecao(colecao_id)
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        _, _, _, meta, _, titulo = _carregar(cur, item_id)
    propriedades = {}
    for c in meta:
        if c.get("papel") == "geometria":
            continue
        tipo = _TIPO_QUERYABLE.get(c.get("tipo_esri"), "string")
        propriedades[c["nome"]] = {"title": c["nome"], "type": tipo}
    propriedades["geometria"] = {"title": "geometria", "$ref": "https://geojson.org/schema/Geometry.json"}
    return {
        "$id": f"{base}/collections/{colecao_id}/queryables",
        "type": "object",
        "title": titulo or item_id,
        "properties": propriedades,
    }


def _bbox_para_pedido(bbox: str | None, bbox_crs: str | None) -> tuple[dict, int]:
    if not bbox:
        return {}, 4326
    partes = bbox.split(",")
    if len(partes) not in (4, 6):
        raise ErroAPI(400, "bbox_invalido", "bbox precisa de 4 (2D) ou 6 (3D) números, vírgula-separados")
    if len(partes) == 6:  # ignora minz/maxz — geometria de trabalho é 2D (declarado no C11 do L2_CONCEITO)
        partes = [partes[0], partes[1], partes[3], partes[4]]
    try:
        xmin, ymin, xmax, ymax = (float(x) for x in partes)
    except ValueError as e:
        raise ErroAPI(400, "bbox_invalido", "bbox precisa ser 4 números") from e
    if xmin > xmax or ymin > ymax:
        raise ErroAPI(400, "bbox_invalido", "bbox invertido: xmin/ymin precisam ser <= xmax/ymax",
                       {"bbox": bbox})
    srid_bbox = _crs_para_srid(bbox_crs, default=4326)
    return {"geometry": ",".join(partes), "geometryType": "esriGeometryEnvelope", "inSR": srid_bbox}, srid_bbox


def _campo_geometria_ativo(meta: list[dict]) -> str:
    for c in meta:
        if c.get("papel") == "geometria":
            return c["nome"]
    return "geometria"


def _aplicar_filtro_cql2(prep: dict, filtro: str | None, filtro_lang: str | None, meta: list[dict], srid_nativo: int):
    if not filtro:
        return
    colunas_sql = campos_mod.lista_branca(meta)
    # `cql2` fala do "campo geometria" (vocabulário GeoJSON), mas a coluna física é sempre `geom`
    colunas_sql_geom = dict(colunas_sql)
    colunas_sql_geom.setdefault("geometria", "geom")
    colunas_sql_geom.setdefault("geometry", "geom")
    try:
        sql, params = cql2.compilar_cql2(filtro, filtro_lang or "cql2-text", colunas_sql_geom, srid_nativo)
    except (cql2.ErroCql2, json.JSONDecodeError) as e:
        codigo = getattr(e, "codigo", "filtro_invalido")
        mensagem = getattr(e, "mensagem", str(e))
        detalhe = getattr(e, "detalhe", None)
        raise ErroAPI(400 if codigo != "filtro_operador_desconhecido" else 400, codigo, mensagem, detalhe) from e
    prep["where_sql"] = f"({prep['where_sql']}) AND ({sql})"
    prep["where_params"] = [*prep["where_params"], *params]


@router.get("/collections/{colecao_id}/items", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="ogc_features_items")
def items(
    item_id: str, colecao_id: str, request: Request, response: Response,
    bbox: str | None = None,
    bbox_crs: str | None = Query(None, alias="bbox-crs"),
    crs: str | None = None,
    filtro: str | None = Query(None, alias="filter"),
    filtro_lang: str | None = Query(None, alias="filter-lang"),
    datetime_: str | None = Query(None, alias="datetime"),
    limit: int | None = Query(None, ge=1),
    offset: int | None = Query(None, ge=0),
):
    _exigir_colecao(colecao_id)
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    limite = min(limit or LIMITE_PADRAO, LIMITE_TETO)
    deslocamento = offset or 0
    with db.db(auth.contexto()) as cur:
        schema, tabela, srid, meta, geom_esri, _ = _carregar(cur, item_id)
        kwargs, _srid_bbox = _bbox_para_pedido(bbox, bbox_crs)
        outSR = _crs_para_srid(crs, default=4326)
        p = motor.PedidoQuery(outFields="*", resultRecordCount=limite, resultOffset=deslocamento, outSR=outSR,
                               **kwargs)
        prep = motor.preparar_pedido(p, meta, srid)
        _aplicar_filtro_cql2(prep, filtro, filtro_lang, meta, srid)
        if datetime_:
            _validar_datetime_intervalo(datetime_)
        res = motor.executar_features(cur, schema, tabela, prep, p, meta, srid, geom_esri)
        total = motor.executar_count(cur, schema, tabela, prep).count
    corpo = como_geojson(res)
    corpo["numberMatched"] = total
    corpo["numberReturned"] = len(res.features)
    corpo["timeStamp"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    qs_base = ""
    if bbox:
        qs_base += f"&bbox={bbox}"
    if bbox_crs:
        qs_base += f"&bbox-crs={bbox_crs}"
    if crs:
        qs_base += f"&crs={crs}"
    if filtro:
        qs_base += f"&filter={filtro}"
    if filtro_lang:
        qs_base += f"&filter-lang={filtro_lang}"
    links = [{"rel": "self", "type": "application/geo+json",
              "href": f"{base}/collections/{colecao_id}/items"}]
    if deslocamento + len(res.features) < total:
        links.append({"rel": "next", "type": "application/geo+json",
                       "href": f"{base}/collections/{colecao_id}/items?limit={limite}"
                               f"&offset={deslocamento + limite}" + qs_base})
    if deslocamento > 0:
        links.append({"rel": "prev", "type": "application/geo+json",
                       "href": f"{base}/collections/{colecao_id}/items?limit={limite}"
                               f"&offset={max(0, deslocamento - limite)}" + qs_base})
    corpo["links"] = links
    resposta = JSONResponse(corpo, media_type="application/geo+json")
    resposta.headers["Content-Crs"] = f"<{_srid_para_crs_uri(outSR)}>"
    return resposta


_ISO_INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$")


def _validar_datetime_intervalo(bruto: str) -> None:
    """Só validação de forma (Part 1 §7.15): `datetime` aberto de um lado (`../2026-01-01` ou
    `2026-01-01/..`) tem de ser aceito — o portão do item pede isto explicitamente. A camada não
    tem `timeInfo` configurado (mesma limitação do FeatureServer), então o valor é aceito e
    IGNORADO no filtro — melhor que 422 quando o cliente só está testando conformidade."""
    partes = bruto.split("/")
    if len(partes) not in (1, 2):
        raise ErroAPI(400, "datetime_invalido", "datetime precisa ser um instante ou um intervalo a/b")
    for p in partes:
        if p in ("..", ""):
            continue
        if not _ISO_INSTANTE.match(p):
            raise ErroAPI(400, "datetime_invalido", f"instante datetime inválido: {p!r}")


@router.get("/collections/{colecao_id}/items/{feature_id}",
            openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"}, operation_id="ogc_features_item")
def item_um(item_id: str, colecao_id: str, feature_id: str, request: Request, crs: str | None = None):
    _exigir_colecao(colecao_id)
    if not feature_id.lstrip("-").isdigit():
        raise ErroAPI(400, "feature_id_invalido", "id da feição precisa ser o OID inteiro (fid)")
    auth = _autenticar(request, item_id)
    base = _base(request, item_id)
    with db.db(auth.contexto()) as cur:
        schema, tabela, srid, meta, geom_esri, _ = _carregar(cur, item_id)
        outSR = _crs_para_srid(crs, default=4326)
        p = motor.PedidoQuery(outFields="*", objectIds=feature_id, outSR=outSR)
        prep = motor.preparar_pedido(p, meta, srid)
        res = motor.executar_features(cur, schema, tabela, prep, p, meta, srid, geom_esri)
    if not res.features:
        raise ErroAPI(404, "feicao_nao_encontrada", f"nenhuma feição com id {feature_id!r}")
    corpo = como_geojson(res)
    feicao = corpo["features"][0]
    feicao["links"] = [{"rel": "self", "type": "application/geo+json",
                         "href": f"{base}/collections/{colecao_id}/items/{feature_id}"}]
    versao = feicao.get("properties", {}).get("versao")
    resposta = JSONResponse(feicao, media_type="application/geo+json")
    resposta.headers["Content-Crs"] = f"<{_srid_para_crs_uri(outSR)}>"
    if versao is not None:
        resposta.headers["ETag"] = f'"{versao}"'
    return resposta


# ============================================================================ Part 4 — Create/Replace/Update/Delete
# Único caminho de escrita: `app.edicao.servico.aplicar_edicoes`, o MESMO da rota
# `POST /api/camadas/{id}/edicoes` (L2-03-a) — nenhuma trilha nova de SQL, nenhuma regra de
# validação/domínio/concorrência duplicada.

def _auth_editor_ogc(auth: Auth = autenticado(escopo_token="camada:editar")) -> Auth:  # noqa: B008
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(
            403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total",
            {"exigido": "feicoes.editar|feicoes.editar_total"},
        )
    return auth


def _etag_para_versao(etag: str | None) -> int | None:
    if not etag:
        return None
    v = etag.strip().strip('"')
    if v == "*":
        return None
    try:
        return int(v)
    except ValueError as e:
        raise ErroAPI(400, "if_match_invalido", f"If-Match não é um ETag reconhecido: {etag!r}") from e


def _globalid_e_versao_por_fid(cur, schema: str, tabela: str, fid: str) -> tuple[str, int]:
    if not fid.lstrip("-").isdigit():
        raise ErroAPI(400, "feature_id_invalido", "id da feição precisa ser o OID inteiro (fid)")
    cur.execute(f'SELECT globalid, versao FROM "{schema}"."{tabela}" WHERE fid = %s', (int(fid),))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "feicao_nao_encontrada", f"nenhuma feição com id {fid!r}")
    return str(r["globalid"]), int(r["versao"])


async def _corpo_geojson(request: Request) -> dict:
    try:
        corpo = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErroAPI(400, "corpo_invalido", "corpo do pedido não é JSON válido") from e
    if not isinstance(corpo, dict) or corpo.get("type") != "Feature":
        raise ErroAPI(422, "feature_invalida", "corpo precisa ser um GeoJSON Feature ({'type':'Feature', ...})")
    return corpo


@router.post("/collections/{colecao_id}/items", status_code=201,
             openapi_extra={"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"},
             operation_id="ogc_features_item_criar")
async def item_criar(item_id: str, colecao_id: str, request: Request, response: Response,
                      auth: Auth = autenticado(escopo_token="camada:editar")):  # noqa: B008
    _exigir_colecao(colecao_id)
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total")
    corpo = await _corpo_geojson(request)
    iid = comum.uuid_ok(item_id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    entrada = EdicoesEntrada(adicionar=[FeicaoAdicionar(atributos=corpo.get("properties") or {},
                                                          geometria=corpo.get("geometry"))])
    try:
        with db.db(auth.contexto()) as cur:
            saida = aplicar_edicoes(cur, request, auth, iid, entrada)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    r = saida.adicionar[0]
    if not r.sucesso:
        raise ErroAPI(422, r.erro or "falha_ao_criar", r.mensagem or "falha ao criar a feição", r.detalhe)
    base = _base(request, item_id)
    resposta = JSONResponse({"id": r.fid}, status_code=201)
    resposta.headers["Location"] = f"{base}/collections/{colecao_id}/items/{r.fid}"
    if r.versao is not None:
        resposta.headers["ETag"] = f'"{r.versao}"'
    return resposta


@router.put("/collections/{colecao_id}/items/{feature_id}", status_code=204,
            openapi_extra={"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"},
            operation_id="ogc_features_item_substituir")
async def item_substituir(item_id: str, colecao_id: str, feature_id: str, request: Request,
                           if_match: str | None = Header(None),
                           auth: Auth = autenticado(escopo_token="camada:editar")):  # noqa: B008
    _exigir_colecao(colecao_id)
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total")
    corpo = await _corpo_geojson(request)
    iid = comum.uuid_ok(item_id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            dados, _ = _camada_e_titulo(cur, iid)
            schema, tabela = dados["schema"], dados["tabela"]
            globalid, versao_atual = _globalid_e_versao_por_fid(cur, schema, tabela, feature_id)
            versao_pedida = _etag_para_versao(if_match) if if_match else versao_atual
            entrada = EdicoesEntrada(atualizar=[FeicaoAtualizar(
                id=globalid, versao=versao_pedida, atributos=corpo.get("properties") or {},
                geometria=corpo.get("geometry"),
            )])
            saida = aplicar_edicoes(cur, request, auth, iid, entrada)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    except ErroAPI as e:
        if e.erro == "conflito_versao":
            raise ErroAPI(412, "precondicao_falhou", "If-Match não bate com a versão atual da feição",
                           e.detalhe) from e
        raise
    r = saida.atualizar[0]
    if not r.sucesso:
        raise ErroAPI(422, r.erro or "falha_ao_substituir", r.mensagem or "falha ao substituir a feição", r.detalhe)
    resposta = Response(status_code=204)
    if r.versao is not None:
        resposta.headers["ETag"] = f'"{r.versao}"'
    return resposta


@router.patch("/collections/{colecao_id}/items/{feature_id}", status_code=204,
              openapi_extra={"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"},
              operation_id="ogc_features_item_atualizar")
async def item_atualizar(item_id: str, colecao_id: str, feature_id: str, request: Request,
                          if_match: str | None = Header(None),
                          auth: Auth = autenticado(escopo_token="camada:editar")):  # noqa: B008
    _exigir_colecao(colecao_id)
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total")
    corpo = await _corpo_geojson(request)
    iid = comum.uuid_ok(item_id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            dados, _ = _camada_e_titulo(cur, iid)
            schema, tabela = dados["schema"], dados["tabela"]
            globalid, versao_atual = _globalid_e_versao_por_fid(cur, schema, tabela, feature_id)
            versao_pedida = _etag_para_versao(if_match) if if_match else versao_atual
            entrada = EdicoesEntrada(atualizar=[FeicaoAtualizar(
                id=globalid, versao=versao_pedida, atributos=corpo.get("properties"),
                geometria=corpo.get("geometry"),
            )])
            saida = aplicar_edicoes(cur, request, auth, iid, entrada)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    except ErroAPI as e:
        if e.erro == "conflito_versao":
            raise ErroAPI(412, "precondicao_falhou", "If-Match não bate com a versão atual da feição",
                           e.detalhe) from e
        raise
    r = saida.atualizar[0]
    if not r.sucesso:
        raise ErroAPI(422, r.erro or "falha_ao_atualizar", r.mensagem or "falha ao atualizar a feição", r.detalhe)
    resposta = Response(status_code=204)
    if r.versao is not None:
        resposta.headers["ETag"] = f'"{r.versao}"'
    return resposta


@router.delete("/collections/{colecao_id}/items/{feature_id}", status_code=204,
               openapi_extra={"x-auth": "S/T", "x-privilegio": "feicoes.editar|feicoes.editar_total"},
               operation_id="ogc_features_item_apagar")
def item_apagar(item_id: str, colecao_id: str, feature_id: str, request: Request,
                 if_match: str | None = Header(None),
                 auth: Auth = autenticado(escopo_token="camada:editar")):  # noqa: B008
    _exigir_colecao(colecao_id)
    if not (auth.tem("feicoes.editar") or auth.tem("feicoes.editar_total")):
        raise ErroAPI(403, "sem_privilegio", "a operação exige o privilégio feicoes.editar ou feicoes.editar_total")
    iid = comum.uuid_ok(item_id)
    esc.exigir_escopo(auth, "camada:editar", iid)
    try:
        with db.db(auth.contexto()) as cur:
            dados, _ = _camada_e_titulo(cur, iid)
            schema, tabela = dados["schema"], dados["tabela"]
            globalid, versao_atual = _globalid_e_versao_por_fid(cur, schema, tabela, feature_id)
            versao_pedida = _etag_para_versao(if_match) if if_match else None
            entrada = EdicoesEntrada(apagar=[FeicaoApagar(id=globalid, versao=versao_pedida)])
            saida = aplicar_edicoes(cur, request, auth, iid, entrada)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e
    except ErroAPI as e:
        if e.erro == "conflito_versao":
            raise ErroAPI(412, "precondicao_falhou", "If-Match não bate com a versão atual da feição",
                           e.detalhe) from e
        raise
    r = saida.apagar[0]
    if not r.sucesso:
        raise ErroAPI(422, r.erro or "falha_ao_apagar", r.mensagem or "falha ao apagar a feição", r.detalhe)
    return Response(status_code=204)
