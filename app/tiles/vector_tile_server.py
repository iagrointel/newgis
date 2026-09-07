"""Servidor de tiles vetoriais em três contratos (item L2-04-e-vector-tile-server-tilejson):

1. TileJSON 3.0.0 + XYZ puro (MapLibre, QGIS): `GET /tiles/{token}/{item}/tilejson.json` e
   `GET /tiles/{token}/{item}/{z}/{x}/{y}.pbf`.
2. VectorTileServer compatível Esri (AGOL/Portal/Pro adicionam "vector tile layer" por URL, sem
   crédito de hospedagem): `GET /svc/{token}/rest/services/{item}/VectorTileServer`, o estilo em
   `.../resources/styles/root.json`, sprites/glyphs em `.../resources/sprites|fonts/...`, e o tile
   em ORDEM Esri `.../tile/{z}/{y}/{x}.pbf` — byte a byte o MESMO tile do contrato 1 (`_tile_bytes`
   é a única função que chama o Martin; as duas rotas só trocam a ordem dos parâmetros de entrada).
3. Exportação por URL de arquivo (`app/tiles/exportacao.py`, módulo irmão).

Token no CAMINHO (nunca cookie, nunca URL assinada que expira — decisão já tomada pelo ladrilho
raster, item L1-02, e reusada aqui: `docs/adr/20260907T1400-vector-tile-server-contratos.md`), uma
camada por item do catálogo (mesma restrição já aceita pelo FeatureServer, item L2-04-c: publicar
mais de uma camada por serviço fica para quando o item tiver esse conceito)."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from app import db
from app.consulta import campos as campos_mod
from app.consulta.serializar import GEOM_PG_PARA_ESRI
from app.erros import ErroAPI
from app.estilos import compilador as estilo_compilador
from app.estilos import padrao as estilo_padrao
from app.tiles import autorizacao, martin_cliente, tilejson
from app.tiles.camada import _camada_do_item, _item_id_valido, extent_4326, funcao_tile

router = APIRouter(tags=["tiles-vetoriais"])

CONTENT_TYPE_MVT = "application/x-protobuf"
CACHE_TILE = "public, max-age=60, stale-while-revalidate=30"
CACHE_DOCUMENTO = "no-store, must-revalidate"
CURRENT_VERSION = 11.3  # mesma versão declarada em rotas_servico.py/rotas_esri.py

GEOM_ESRI_PARA_PLAT_CONSTRUTOR = {
    "Point": "ponto", "MultiPoint": "ponto",
    "LineString": "linha", "MultiLineString": "linha",
    "Polygon": "poligono", "MultiPolygon": "poligono",
}

# tileInfo Web Mercator / 512 px (decisão C do item: Esri aceita LOD custom, mas 512 px é o que os
# clientes ArcGIS esperam de um serviço de vetor — o mesmo tamanho de tile que o Martin/MVT usa por
# convenção de 4096 unidades de extensão, ST_AsMVT em plat.camada_tile_garantir).
_ORIGEM_MERCATOR = 20037508.342789244
_RESOLUCAO_Z0 = (2 * _ORIGEM_MERCATOR) / 512
_ESCALA_POR_METRO = 1 / 0.0002645833333  # fator de conversão padrão da Esri (dpi 96)


def _lods(zoom_max: int = 22) -> list[dict]:
    saida = []
    for z in range(zoom_max + 1):
        resolucao = _RESOLUCAO_Z0 / (2**z)
        saida.append({"level": z, "resolution": resolucao, "scale": resolucao * _ESCALA_POR_METRO})
    return saida


def _campo_da_query(item_id: str) -> None:
    _item_id_valido(item_id)


def _titulo_e_dados(cur, item_id: str) -> tuple[str, dict]:
    dados = _camada_do_item(cur, item_id)
    cur.execute("SELECT titulo FROM plat.item WHERE id = %s::uuid", (item_id,))
    r = cur.fetchone()
    return (r["titulo"] if r else None) or item_id, dados


def _tile_bytes(request: Request, token: str, item_id: str, z: int, x: int, y: int) -> tuple[bytes, int]:
    """Único ponto que chama o Martin para um tile desta camada — as duas rotas HTTP (ordem
    MapLibre x/y e ordem Esri y/x) convergem aqui, o que faz a cláusula "byte a byte igual" ser
    verdade por CONSTRUÇÃO, não por coincidência de implementação paralela."""
    auth = autorizacao.autorizar(request, token, item_id)
    with db.db(auth.contexto()) as cur:
        dados = _camada_do_item(cur, item_id)
    funcao = funcao_tile(dados)
    return martin_cliente.tile_mvt(funcao, z, x, y, token=token, item=item_id)


def _resposta_tile(corpo: bytes, status: int) -> Response:
    if status == 204 or not corpo:
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    etag = '"' + hashlib.sha256(corpo).hexdigest()[:32] + '"'
    return Response(
        content=corpo, media_type=CONTENT_TYPE_MVT,
        headers={"Cache-Control": CACHE_TILE, "ETag": etag},
    )


# ============================================================================== contrato 1: TileJSON
@router.get(
    "/tiles/{token}/{item_id}/tilejson.json",
    openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
    summary="TileJSON 3.0.0 da camada (MapLibre/QGIS)",
)
def tilejson_da_camada(request: Request, token: str, item_id: str):
    auth = autorizacao.autorizar(request, token, item_id)
    with db.db(auth.contexto()) as cur:
        titulo, dados = _titulo_e_dados(cur, item_id)
        schema, tabela = dados["schema"], dados["tabela"]
        funcao = funcao_tile(dados)
        bounds = extent_4326(cur, schema, tabela)
        campos = campos_mod.campos_da_camada(cur, schema, tabela)
    base = f"{request.url.scheme}://{request.url.netloc}"
    tiles_url = f"{base}/tiles/{token}/{item_id}/{{z}}/{{x}}/{{y}}.pbf"
    doc = tilejson.documento(nome=titulo, funcao=funcao, tiles_url=tiles_url, bounds=bounds, campos=campos)
    corpo = json.dumps(doc, sort_keys=True).encode("utf-8")
    etag = '"' + hashlib.sha256(corpo).hexdigest()[:32] + '"'
    return JSONResponse(doc, headers={"Cache-Control": CACHE_DOCUMENTO, "ETag": etag})


@router.get(
    "/tiles/{token}/{item_id}/{z}/{x}/{y}.pbf",
    openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
    summary="tile XYZ (ordem MapLibre: z/x/y)",
)
def tile_xyz(request: Request, token: str, item_id: str, z: int, x: int, y: int):
    corpo, status = _tile_bytes(request, token, item_id, z, x, y)
    return _resposta_tile(corpo, status)


# ==================================================================== internal: auth_request do nginx
@router.get("/api/tiles/vetor/autorizar", include_in_schema=False)
def autorizar_para_nginx(
    request: Request,
    x_plat_token: str | None = Header(default=None, alias="X-Plat-Token"),
    x_plat_item: str | None = Header(default=None, alias="X-Plat-Item"),
):
    """Espelho do `_plat_tile_autorizar` do ladrilho raster (item L1-02): nginx faz `auth_request`
    para cá ANTES de servir do `proxy_cache` — o cache do TILE não tem o token na chave (dois
    tokens válidos do mesmo item compartilham o tile em disco), então é este endpoint, chamado em
    cada pedido de verdade, que garante que token revogado nunca passa, mesmo com o tile já em cache."""
    try:
        autorizacao.autorizar(request, x_plat_token or "", x_plat_item or "")
    except ErroAPI as e:
        return Response(status_code=e.status, headers={"X-Motivo-Recusa": e.erro})
    return Response(status_code=204)


# ============================================================================ contrato 2: Esri VectorTileServer
PREFIXO_ESRI = "/svc/{token}/rest/services/{item_id}/VectorTileServer"


def _fontes_maplibre(base: str) -> dict:
    return {"camada": {"type": "vector", "tiles": [f"{base}/tile/{{z}}/{{y}}/{{x}}.pbf"], "minzoom": 0, "maxzoom": 22}}


def _root_style(cur, base: str, item_id: str, dados: dict) -> dict:
    funcao = funcao_tile(dados)
    geom_esri = GEOM_PG_PARA_ESRI.get(dados.get("geometria"))
    geom_pc = GEOM_ESRI_PARA_PLAT_CONSTRUTOR.get(dados.get("geometria"), "poligono")
    pc = json.loads(json.dumps(estilo_padrao.estilo_padrao(item_id, geom_pc)["corpo"]["plat_construtor"]))
    layers = estilo_compilador.compilar(pc, id_base=funcao)["layers"]
    for layer in layers:
        layer["source"] = "camada"
        layer["source-layer"] = funcao
    return {
        "version": 8,
        "name": f"estilo padrão de {item_id}",
        "sources": _fontes_maplibre(base),
        "sprite": f"{base}/resources/sprites/sprite",
        "glyphs": f"{base}/resources/fonts/{{fontstack}}/{{range}}.pbf",
        "layers": layers,
        "metadata": {"plat:geometryType": geom_esri},
    }


def _descritor_servico(cur, token: str, item_id: str, base: str) -> dict:
    titulo, dados = _titulo_e_dados(cur, item_id)
    bounds = extent_4326(cur, dados["schema"], dados["tabela"])
    extent = None
    if bounds:
        extent = {"xmin": bounds[0], "ymin": bounds[1], "xmax": bounds[2], "ymax": bounds[3],
                  "spatialReference": {"wkid": 4326, "latestWkid": 4326}}
    tiles_url = f"{base}/tile/{{z}}/{{y}}/{{x}}.pbf"
    return {
        "currentVersion": CURRENT_VERSION,
        "name": titulo,
        "serviceItemId": item_id,
        "capabilities": "TilesOnly",
        "type": "indexedVector",
        "copyrightText": "",
        "spatialReference": {"wkid": 4326, "latestWkid": 4326},
        "tiles": [tiles_url],
        "tileInfo": {
            "rows": 512, "cols": 512, "dpi": 96, "format": "pbf",
            "origin": {"x": -_ORIGEM_MERCATOR, "y": _ORIGEM_MERCATOR},
            "spatialReference": {"wkid": 102100, "latestWkid": 3857},
            "lods": _lods(),
        },
        "fullExtent": extent,
        "initialExtent": extent,
        "minScale": 0,
        "maxScale": 0,
        "resourceInfo": {"styleVersion": 8, "tileCompression": "gzip"},
        "defaultStyles": "resources/styles",
    }


@router.get(PREFIXO_ESRI, openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="descritor VectorTileServer (?f=json)")
def descritor_vector_tile_server(request: Request, token: str, item_id: str):
    auth = autorizacao.autorizar(request, token, item_id)
    base = f"{request.url.scheme}://{request.url.netloc}{PREFIXO_ESRI.format(token=token, item_id=item_id)}"
    with db.db(auth.contexto()) as cur:
        doc = _descritor_servico(cur, token, item_id, base)
    corpo = json.dumps(doc, sort_keys=True).encode("utf-8")
    etag = '"' + hashlib.sha256(corpo).hexdigest()[:32] + '"'
    return JSONResponse(doc, headers={"Cache-Control": CACHE_DOCUMENTO, "ETag": etag})


@router.get(f"{PREFIXO_ESRI}/resources/styles/root.json",
            openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="estilo MapLibre do serviço (fontes apontando para o próprio VectorTileServer)")
def root_style(request: Request, token: str, item_id: str):
    auth = autorizacao.autorizar(request, token, item_id)
    base = f"{request.url.scheme}://{request.url.netloc}{PREFIXO_ESRI.format(token=token, item_id=item_id)}"
    with db.db(auth.contexto()) as cur:
        dados = _camada_do_item(cur, item_id)
        doc = _root_style(cur, base, item_id, dados)
    corpo = json.dumps(doc, sort_keys=True).encode("utf-8")
    etag = '"' + hashlib.sha256(corpo).hexdigest()[:32] + '"'
    return JSONResponse(doc, headers={"Cache-Control": CACHE_DOCUMENTO, "ETag": etag})


# sprite/glyphs: sem pipeline próprio de ícone/fonte nesta plataforma ainda (L2-02-e não construído —
# dependência NÃO listada neste item). Placeholder REAL e válido (nunca um 404/500 que quebre o
# cliente Esri): sprite vazio (nenhum ícone) e um PNG 1x1 transparente de verdade (bytes PNG reais,
# não um arquivo fake); glyphs devolve um PBF de pilha de fontes VÁLIDO, mas SEM glifos (protobuf
# `glyphs.proto` da Style Spec, stack com `range` declarado e zero `glyphs`) — 200 correto, conteúdo
# honestamente vazio. Registrado como fronteira no handoff, não escondido.
_PNG_1X1_TRANSPARENTE = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a4944415478da6360000002000155027d10000000"
    "0049454e44ae426082"
)


def _glyphs_pbf_vazio(fontstack: str, faixa: str) -> bytes:
    """Protobuf `glyphs.proto` (MapLibre Style Spec) montado à mão: `message glyphs { repeated
    fontstack stacks = 1; }`, `message fontstack { required string name = 1; repeated glyph glyphs
    = 2; optional string range = 3; }`. Sem dependência nova (nenhum protobuf runtime instalado
    no venv compartilhado — ADR do item), escrito por wire format: tag 1 (stacks, LEN), dentro dela
    tag 1 (name, LEN) e tag 3 (range, LEN); sem glyphs (campo 2 ausente = lista vazia, válido)."""

    def _campo_string(numero: int, valor: bytes) -> bytes:
        tag = (numero << 3) | 2  # wire type 2 = length-delimited
        return bytes([tag]) + _varint(len(valor)) + valor

    def _varint(n: int) -> bytes:
        saida = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                saida.append(b | 0x80)
            else:
                saida.append(b)
                return bytes(saida)

    fontstack_msg = _campo_string(1, fontstack.encode("utf-8")) + _campo_string(3, faixa.encode("utf-8"))
    return _campo_string(1, fontstack_msg)


@router.get(f"{PREFIXO_ESRI}/resources/sprites/sprite.json",
            openapi_extra={"x-auth": "T", "x-privilegio": "proprio"}, summary="sprite (sem ícones ainda)")
def sprite_json(request: Request, token: str, item_id: str):
    autorizacao.autorizar(request, token, item_id)
    return JSONResponse({}, headers={"Cache-Control": CACHE_DOCUMENTO})


@router.get(f"{PREFIXO_ESRI}/resources/sprites/sprite.png",
            openapi_extra={"x-auth": "T", "x-privilegio": "proprio"}, summary="sprite (PNG 1x1 transparente)")
def sprite_png(request: Request, token: str, item_id: str):
    autorizacao.autorizar(request, token, item_id)
    return Response(_PNG_1X1_TRANSPARENTE, media_type="image/png", headers={"Cache-Control": CACHE_DOCUMENTO})


@router.get(f"{PREFIXO_ESRI}/resources/fonts/{{fontstack}}/{{faixa}}.pbf",
            openapi_extra={"x-auth": "T", "x-privilegio": "proprio"}, summary="glifos (pilha vazia válida)")
def fontes_pbf(request: Request, token: str, item_id: str, fontstack: str, faixa: str):
    autorizacao.autorizar(request, token, item_id)
    corpo = _glyphs_pbf_vazio(fontstack, faixa)
    return Response(corpo, media_type="application/x-protobuf", headers={"Cache-Control": CACHE_DOCUMENTO})


@router.get(f"{PREFIXO_ESRI}/tile/{{z}}/{{y}}/{{x}}.pbf",
            openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
            summary="tile no formato Esri (ordem z/y/x)")
def tile_esri(request: Request, token: str, item_id: str, z: int, y: int, x: int):
    corpo, status = _tile_bytes(request, token, item_id, z, x, y)
    return _resposta_tile(corpo, status)
