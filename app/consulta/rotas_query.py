"""Operação `query` do FeatureServer, item L2-04-c (ADR 0016) — compatibilidade Esri: o cliente troca
o ArcGIS Enterprise pela plataforma sem trocar a ferramenta. Rota montada sob `/rest/services/{item}/
FeatureServer/{camada}/query` (mesma raiz `/rest/services` do GeocodeServer compatível, ADR 0013 §5,
enquanto o diretório completo do serviço — pastas, `/FeatureServer` raiz, `/layers` — é o item L2-04-b,
ainda não construído; a URL aqui é a que o L2-04-b vai montar por cima quando existir).

Autenticação: sessão de usuário OU token de serviço com escopo `camada:ler` (opcionalmente escopado à
camada, `camada:ler:<uuid>` — igual ao GeocodeServer, aceita o token também por querystring `?token=`,
que é como AGOL/Pro se conectam a um FeatureServer publicado). RLS faz o resto: a consulta corre como
`plat_app` com o inquilino do token/sessão no contexto — outro inquilino nunca aparece, mesmo que o
UUID do item seja adivinhado (P6)."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Request, Response

from app import db
from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.consulta import campos as campos_mod
from app.consulta import motor, serializar
from app.consulta.geometria_esri import sr_wkid
from app.erros import ErroAPI

router = APIRouter(tags=["consulta-esri"])
PREFIXO = "/rest/services/{item_id}/FeatureServer/{camada_id}"
ESCOPO = "camada:ler"

_CONTENT_TYPE = {
    "json": "application/json", "pjson": "application/json",
    "geojson": "application/vnd.geo+json", "pbf": "application/x-protobuf",
}


def _autenticar(request: Request, item_id: str, escopo: str = ESCOPO):
    """Sessão normal OU token — igual ao GeocodeServer (`app/geocodificador/rotas_esri.py`):
    protocolo Esri manda o token na URL, então `?token=`/form `token=` também é aceito além do
    cabeçalho `Authorization`."""
    try:
        auth = auth_sessao.resolver(request)
    except ErroAPI:
        auth = None
    if auth is None:
        tok = request.query_params.get("token")
        if not tok:
            raise ErroAPI(401, "token_requerido", "informe token=<token de serviço> ou Authorization: Bearer")
        auth = auth_sessao._auth_de_token(request, tok)  # noqa: SLF001 — mesmo reuso do GeocodeServer
        request.state.auth = auth
    esc.exigir_escopo(auth, escopo, item_id)
    return auth


async def _parametros(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        ct = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            p.update({k: str(v) for k, v in form.items()})
        elif "application/json" in ct:
            corpo = await request.json()
            if isinstance(corpo, dict):
                p.update({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in corpo.items()})
    return p


def _pedido_de(p: dict) -> motor.PedidoQuery:
    campos_bool = (
        "returnGeometry", "returnDistinctValues", "returnIdsOnly", "returnCountOnly", "returnExtentOnly",
        "returnZ", "returnM", "returnCentroid", "returnTrueCurves", "returnExceededLimitFeatures",
        "timeReferenceUnknownClient", "returnEnvelope", "returnUniqueIdsOnly",
    )
    kwargs = {}
    defaults = motor.PedidoQuery()
    for nome in campos_bool:
        if nome in p:
            kwargs[nome] = motor._bool(p[nome], getattr(defaults, nome))
    for nome in ("distance",):
        if nome in p:
            kwargs[nome] = float(p[nome]) if p[nome] not in (None, "") else 0.0
    for nome in ("resultOffset", "resultRecordCount", "geometryPrecision"):
        if nome in p:
            kwargs[nome] = motor._int(p[nome])
    texto = (
        "where", "objectIds", "geometry", "geometryType", "inSR", "spatialRel", "relationParam", "units",
        "time", "outFields", "defaultSR", "outSR", "havingClause", "gdbVersion", "orderByFields",
        "groupByFieldsForStatistics", "outStatistics", "multipatchOption", "quantizationParameters",
        "resultType", "historicMoment", "sqlFormat", "datumTransformation", "fullText", "uniqueIds",
        "resultPaginationToken", "f",
    )
    for nome in texto:
        if p.get(nome) not in (None, ""):
            kwargs[nome] = p[nome]
    return motor.PedidoQuery(**kwargs)


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _item_id_valido(item_id: str) -> None:
    """Achado do adversário da trilha `esriogc` (item L2-04-servicos-esri-ogc): `item_id::uuid` sem
    validar antes deixava o Postgres levantar `InvalidTextRepresentation` para qualquer path
    (`x' OR '1'='1`, `;DROP TABLE ...`) — a exceção não tinha handler e virava HTTP 500 (o texto do
    cliente chegava ao banco antes de ser recusado, exatamente o que a refutação do item proíbe).
    Corrigido aqui, na função que cada um dos protocolos (FeatureServer, OGC API Features, WFS) chama
    antes de tocar o banco — item_id malformado é tratado como item inexistente (404), nunca 500."""
    if not _UUID_RE.match(item_id):
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")


def _camada_do_item(cur, item_id: str) -> dict:
    _item_id_valido(item_id)
    cur.execute(
        "SELECT dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'", (item_id,)
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "camada_nao_encontrada", "item inexistente, não é camada vetorial, ou sem permissão")
    return r["dados"]


async def _query(request: Request, item_id: str, camada_id: str) -> Response:
    if camada_id != "0":
        raise ErroAPI(404, "camada_nao_encontrada", "esta implementação publica uma camada só (id 0) por item")
    p_bruto = await _parametros(request)
    p = _pedido_de(p_bruto)
    auth = _autenticar(request, item_id)
    with db.db(auth.contexto()) as cur:
        dados = _camada_do_item(cur, item_id)
        schema, tabela, srid_nativo = dados["schema"], dados["tabela"], int(dados["srid"])
        meta = campos_mod.campos_da_camada(cur, schema, tabela)
        geom_pg = dados.get("geometria")
        geometria_tipo_esri = serializar.GEOM_PG_PARA_ESRI.get(geom_pg)

        prep = motor.preparar_pedido(p, meta, srid_nativo)
        if p.outStatistics:
            res = motor.executar_estatisticas(cur, schema, tabela, prep, p, sr_wkid(p.outSR) or srid_nativo)
        elif p.returnCountOnly and not p.returnExtentOnly:
            res = motor.executar_count(cur, schema, tabela, prep)
        elif p.returnExtentOnly:
            res = motor.executar_extent(cur, schema, tabela, prep, sr_wkid(p.outSR) or srid_nativo, p.returnCountOnly)
        elif p.returnIdsOnly or p.returnUniqueIdsOnly:
            res = motor.executar_ids(cur, schema, tabela, prep)
        else:
            res = motor.executar_features(cur, schema, tabela, prep, p, meta, srid_nativo, geometria_tipo_esri)
            if p.returnEnvelope and isinstance(res, motor.ResultadoFeatures):
                # extensão do CONJUNTO filtrado (não só da página) — mesma consulta de returnExtentOnly,
                # reaproveitada; sai como `res.extent`, incluído no corpo por `serializar.como_json`
                extent_res = motor.executar_extent(cur, schema, tabela, prep, sr_wkid(p.outSR) or srid_nativo, False)
                res.extent = extent_res.extent

    f = (p.f or "json").lower()
    if f not in _CONTENT_TYPE:
        raise ErroAPI(400, "formato_invalido", f"f não suportado: {f!r} (use json, pjson, geojson ou pbf)")
    if f == "geojson" and not isinstance(res, motor.ResultadoFeatures):
        raise ErroAPI(422, "geojson_fora", "f=geojson só se aplica a consulta de feições (não count/ids/extent)")
    if f == "pbf":
        return Response(content=serializar.como_pbf(res), media_type=_CONTENT_TYPE["pbf"])
    corpo = serializar.como_geojson(res) if f == "geojson" else serializar.como_json(res)
    return Response(content=json.dumps(corpo, default=str), media_type=_CONTENT_TYPE[f])


@router.get(f"{PREFIXO}/query", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            operation_id="consulta_esri_query_get")
async def query_get(request: Request, item_id: str, camada_id: str):
    return await _query(request, item_id, camada_id)


@router.post(f"{PREFIXO}/query", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
             operation_id="consulta_esri_query_post")
async def query_post(request: Request, item_id: str, camada_id: str):
    return await _query(request, item_id, camada_id)
