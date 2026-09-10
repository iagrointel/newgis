"""Rotas de OGC API — Tiles (20-057) e OGC API — Maps por token (item L1-02-i-ogc-api-tiles-e-maps;
ADR 20260910T2056).

    GET /svc/<token>/ogc/tiles                                                         landing
    GET /svc/<token>/ogc/tiles/conformance
    GET /svc/<token>/ogc/tiles/tileMatrixSets
    GET /svc/<token>/ogc/tiles/tileMatrixSets/WebMercatorQuad
    GET /svc/<token>/ogc/tiles/collections                                             itens raster visíveis
    GET /svc/<token>/ogc/tiles/collections/<item>                                      item OU mosaico registrado
    GET /svc/<token>/ogc/tiles/collections/<item>/map                                  OGC API Maps (só item raster)
    GET /svc/<token>/ogc/tiles/collections/<item>/map/tiles/WebMercatorQuad             tileset metadata
    GET /svc/<token>/ogc/tiles/collections/<item>/map/tiles/WebMercatorQuad/{z}/{y}/{x}[.ext]  ladrilho

Nenhuma leitura de pixel própria: o ladrilho de item chama `rotas_tiles._servir` — a MESMA função que
atende `/svc/<token>/raster/<item>/{z}/{x}/{y}` —, o ladrilho de mosaico chama
`rotas_tiles._tile_mosaico_impl` — a MESMA função de `/svc/<token>/mosaico/<alvo>/{z}/{x}/{y}` —, e o
`/map` chama `tiles.recorte()` — a mesma função que o `GetMap` do WMS usa. `{item}` no caminho vale
para item raster OU mosaico (uuid registrado ou nome de coleção completo, o modo ad-hoc que já existe
desde antes do L1-07) — ver `_resolver_colecao`. Mesma porta de entrada do resto do L1-02
(`_autorizar`, token no caminho, 403 sempre — nunca 404 — para "não existe" e "não é seu")."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app import db, limites
from app.erros import ErroAPI
from app.imagens import mosaico as mo
from app.imagens import ogc_tiles as doc
from app.imagens import pgstac as ps
from app.imagens import tiles
from app.imagens.rotas_tiles import (
    CACHE_TILE,
    X,
    _asset_padrao,
    _autorizar,
    _extent_do_mosaico,
    _fonte_do_item,
    _servir,
    _tile_mosaico_impl,
)
from app.imagens.rotas_wms import _camadas_visiveis
from app.settings import settings

router = APIRouter(tags=["ogc-tiles"])

CRS84_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


def _base(token: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/svc/{token}/ogc/tiles"


def _grade_valida(tile_matrix_set_id: str) -> None:
    if tile_matrix_set_id != doc.TMS_ID:
        raise ErroAPI(404, "tileMatrixSet_invalido", f"a única grade servida é {doc.TMS_ID}",
                      {"tileMatrixSetId": tile_matrix_set_id})


# ---------------------------------------------------------------------------- landing / conformance / grade
@router.get("/svc/{token}/ogc/tiles", openapi_extra=X, summary="OGC API Tiles/Maps — landing",
            operation_id="ogc_tiles_landing")
@router.get("/svc/{token}/ogc/tiles/", include_in_schema=False, openapi_extra=X,
            operation_id="ogc_tiles_landing_barra")
def landing(request: Request, token: str):
    _autorizar(request, token)
    return JSONResponse(doc.landing(_base(token)), headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/ogc/tiles/conformance", openapi_extra=X,
            summary="classes de conformidade declaradas (só as realmente cumpridas)")
def conformance(request: Request, token: str):
    _autorizar(request, token)
    return JSONResponse(doc.conformance(), headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/ogc/tiles/tileMatrixSets", openapi_extra=X, summary="grades de ladrilho servidas")
def tile_matrix_sets(request: Request, token: str):
    _autorizar(request, token)
    return JSONResponse(doc.tile_matrix_sets_lista(_base(token)),
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/svc/{token}/ogc/tiles/tileMatrixSets/{tile_matrix_set_id}", openapi_extra=X,
            summary="definição da grade — esquema OGC 17-083r4 (a definição real, não só o nome)")
def tile_matrix_set_um(request: Request, token: str, tile_matrix_set_id: str):
    _autorizar(request, token)
    _grade_valida(tile_matrix_set_id)
    return JSONResponse(doc.tile_matrix_set_definicao(), headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------- collections
@router.get("/svc/{token}/ogc/tiles/collections", openapi_extra=X,
            summary="coleções (itens raster) visíveis a este token — mosaico nunca é enumerado, só endereçado")
def collections(request: Request, token: str):
    auth = _autorizar(request, token)
    with db.db(auth.contexto_leitura()) as cur:
        camadas = _camadas_visiveis(cur, auth)
    itens = [{"item_id": c["item_id"], "titulo": c["titulo"], "bounds": c["bounds"]} for c in camadas.values()]
    return JSONResponse(doc.colecoes_json(_base(token), itens),
                        headers={"Cache-Control": "no-store, must-revalidate"})


def _eh_item_raster(auth, item: str) -> bool:
    with db.db(auth.contexto_leitura()) as cur:
        cur.execute(
            "SELECT 1 FROM plat.raster_item WHERE tenant_id = %s AND item_id = %s AND estado = 'ativo' LIMIT 1",
            (auth.tenant_id, item),
        )
        return cur.fetchone() is not None


def _resolver_colecao(auth, item: str) -> dict:
    """-> {tipo, titulo, bounds=[oeste,sul,leste,norte] 4326, minzoom, maxzoom}. `tipo` é "item",
    "mosaico_registrado" (uuid de `POST /svc/<token>/stac/mosaicos`) ou "mosaico_colecao" (nome
    completo de coleção, modo ad-hoc). 403 honesto — nunca 404 — quando `item` não é nada disso do
    inquilino do token (mesma regra do resto do L1-02: não confirma existência alheia)."""
    if _eh_item_raster(auth, item):
        fonte, stac = _fonte_do_item(auth, item, _asset_padrao(None, None))
        info = tiles.informacao(fonte)
        titulo = (stac.get("properties") or {}).get("title") or item
        return {"tipo": "item", "titulo": titulo, "bounds": info["bounds"],
                "minzoom": info["minzoom"], "maxzoom": max(info["maxzoom"], 18)}
    if mo.eh_uuid(item):
        with db.db(auth.contexto_leitura()) as cur:
            linha = mo.obter(cur, auth.tenant_id, item)
            if linha is None:
                raise ErroAPI(403, "item_indisponivel", "coleção inexistente ou de outro inquilino",
                              {"item": item})
            bounds = _extent_do_mosaico(cur, linha)
        return {"tipo": "mosaico_registrado", "titulo": linha["nome"], "bounds": bounds,
                "minzoom": 0, "maxzoom": 22}
    if ps.colecao_pertence(item, auth.tenant_id):
        return {"tipo": "mosaico_colecao", "titulo": item, "bounds": [-180.0, -90.0, 180.0, 90.0],
                "minzoom": 0, "maxzoom": 22}
    raise ErroAPI(403, "item_indisponivel", "coleção inexistente ou de outro inquilino", {"item": item})


@router.get("/svc/{token}/ogc/tiles/collections/{item}", openapi_extra=X,
            summary="metadados da coleção (item raster ou mosaico registrado)")
def colecao(request: Request, token: str, item: str):
    auth = _autorizar(request, token, item)
    info = _resolver_colecao(auth, item)
    return JSONResponse(doc.colecao_json(_base(token), item, info["titulo"], info["bounds"]),
                        headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- tileset metadata
def _limites_por_zoom(bounds: list[float], minzoom: int, maxzoom: int) -> list[dict]:
    """`tileMatrixSetLimits` por zoom — canto (oeste,norte) e canto (leste,sul) em O(1) por zoom
    (`TMS.tile`, não enumeração dos ladrilhos intersectados: um item cobrindo poucos graus teria
    milhões de ladrilhos em zoom alto — só os DOIS cantos bastam para o retângulo de linhas/colunas)."""
    oeste, sul, leste, norte = bounds
    saida = []
    if minzoom > maxzoom:
        return saida
    for z in range(minzoom, maxzoom + 1):
        sup_esq = tiles.TMS.tile(oeste, norte, z, truncate=True)
        inf_dir = tiles.TMS.tile(leste, sul, z, truncate=True)
        saida.append({
            "tileMatrix": str(z),
            "minTileRow": min(sup_esq.y, inf_dir.y), "maxTileRow": max(sup_esq.y, inf_dir.y),
            "minTileCol": min(sup_esq.x, inf_dir.x), "maxTileCol": max(sup_esq.x, inf_dir.x),
        })
    return saida


@router.get("/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}", openapi_extra=X,
            summary="metadados do conjunto de ladrilhos (tileset) da coleção")
def tileset(request: Request, token: str, item: str, tile_matrix_set_id: str):
    auth = _autorizar(request, token, item)
    _grade_valida(tile_matrix_set_id)
    info = _resolver_colecao(auth, item)
    if info["tipo"] == "mosaico_colecao":
        raise ErroAPI(422, "sem_metadados",
                      "coleção ad-hoc (nome completo, sem registro) não tem metadados de tileset — "
                      "registre a busca em POST /svc/<token>/stac/mosaicos para obter extensão e "
                      "limites (o ladrilho em si já funciona sem isso, ver /map/tiles/.../{z}/{y}/{x})",
                      {"item": item})
    limites_tile = _limites_por_zoom(info["bounds"], info["minzoom"], info["maxzoom"])
    corpo = doc.tileset_json(_base(token), item, info["titulo"], info["bounds"], info["minzoom"],
                             info["maxzoom"], limites_tile, ["image/png", "image/jpeg", "image/webp"])
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- ladrilho (map tile)
def _tile_impl(request: Request, token: str, item: str, tile_matrix_set_id: str, tile_matrix: int,
              tile_row: int, tile_col: int, formato: str) -> Response:
    # auth ANTES da validação de grade (mesma ordem do resto do módulo: nunca vazar detalhe do pedido
    # para quem não passou por `_autorizar`).
    auth = _autorizar(request, token, item)
    _grade_valida(tile_matrix_set_id)
    if _eh_item_raster(auth, item):
        return _servir(request, auth, item, tile_matrix, tile_col, tile_row, formato,
                       None, None, None, None, None, predef=None)
    return _tile_mosaico_impl(request, token, item, tile_matrix, tile_col, tile_row, formato,
                              None, None, None, None, None, None)


# a rota COM extensão é registrada ANTES da rota sem extensão de propósito — mesma armadilha
# documentada em `rotas_tiles.py` (FastAPI casa pela FORMA do caminho, na ordem de registro; se a
# rota sem `.{ext}` viesse primeiro, `tile_col` receberia o texto "12.png" e falharia a conversão
# para int antes de a rota certa ser tentada).
@router.get(
    "/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}.{ext}",
    openapi_extra=X, summary="ladrilho (map tile) com extensão no caminho")
def tile_map_ext(request: Request, token: str, item: str, tile_matrix_set_id: str, tile_matrix: int,
                 tile_row: int, tile_col: int, ext: str):
    if ext not in tiles.FORMATOS:
        raise ErroAPI(404, "formato_desconhecido", f"formato de ladrilho desconhecido: {ext}",
                      {"aceitos": sorted(tiles.FORMATOS)})
    return _tile_impl(request, token, item, tile_matrix_set_id, tile_matrix, tile_row, tile_col, ext)


@router.get(
    "/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}",
    openapi_extra=X, summary="ladrilho (map tile)")
def tile_map(request: Request, token: str, item: str, tile_matrix_set_id: str, tile_matrix: int,
            tile_row: int, tile_col: int, f: str = Query("png", pattern="^(png|jpg|jpeg|webp)$")):
    return _tile_impl(request, token, item, tile_matrix_set_id, tile_matrix, tile_row, tile_col, f)


# ---------------------------------------------------------------------------- OGC API Maps (/map)
def _crs_normalizar(valor: str | None) -> str:
    """CRS84, a URI OGC completa ou o atalho `EPSG:<n>` -> string que `rasterio.crs.CRS.from_user_input`
    aceita. Mesma tolerância de forma que `app/consulta/rotas_ogc_features.py::_crs_para_srid` já
    declara para feição — reescrita aqui (poucas linhas) por ser outro domínio (imagem, não feição),
    não importada por acoplamento cruzado entre `app/imagens` e `app/consulta`."""
    if not valor:
        return "EPSG:4326"
    v = valor.strip()
    if v.upper() in ("CRS84", "OGC:CRS84") or v == CRS84_URI:
        return "EPSG:4326"
    if v.upper().startswith("EPSG:"):
        return v.upper()
    m = re.search(r"/EPSG/\d+/(\d+)$", v)
    if m:
        return f"EPSG:{m.group(1)}"
    if v.lstrip("-").isdigit():
        return f"EPSG:{v}"
    raise ErroAPI(400, "crs_invalido", f"CRS não reconhecido: {valor!r}", {"crs": valor})


def _crs_uri_saida(crs_normalizado: str) -> str:
    n = crs_normalizado.split(":")[-1]
    return CRS84_URI if n == "4326" else f"http://www.opengis.net/def/crs/EPSG/0/{n}"


def _bbox_map(valor: str | None) -> tuple[float, float, float, float]:
    if not valor:
        raise ErroAPI(400, "bbox_ausente", "bbox é obrigatório: minx,miny,maxx,maxy")
    partes = valor.split(",")
    if len(partes) != 4:
        raise ErroAPI(400, "bbox_invalido", "bbox precisa de 4 números: minx,miny,maxx,maxy", {"bbox": valor})
    try:
        a, b, c, d = (float(p) for p in partes)
    except ValueError as e:
        raise ErroAPI(400, "bbox_invalido", "bbox precisa ser 4 números", {"bbox": valor}) from e
    if a >= c or b >= d:
        raise ErroAPI(400, "bbox_invalido", "bbox invertido: minx/miny precisam ser < maxx/maxy",
                      {"bbox": valor})
    return a, b, c, d


@router.get("/svc/{token}/ogc/tiles/collections/{item}/map", openapi_extra=X,
            summary="OGC API Maps — recorte por bbox/crs/width/height (a irmã do GetMap do WMS)")
def mapa(
    request: Request, token: str, item: str,
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy no CRS do parâmetro crs"),
    crs: str | None = Query(None, description="CRS do bbox e da imagem de saída (mesmo uso do CRS do WMS GetMap)"),
    # sem `le=` aqui de propósito: um valor acima do teto tem de CAIR no `dimensao_excessiva` abaixo
    # (erro do contrato desta casa, com o número no corpo) — um `le=` do pydantic devolveria o 422
    # genérico de validação ANTES da rota rodar, E (achado desta bancada) tornaria a checagem de
    # `width*height` abaixo MORTA: com os dois lados já presos no teto individual, o produto NUNCA
    # passaria de `WMS_PIXELS_MAX` (4096×4096 é exatamente o teto, não acima dele) — a checagem nunca
    # dispararia e um pedido exatamente no canto (4096×4096) cairia direto no render, medido em
    # 142 s numa única chamada. Mesmas três condições (OR) que `rotas_wms._get_map` já usa.
    width: int = Query(800, ge=1),
    height: int = Query(600, ge=1),
    f: str = Query("png", pattern="^(png|jpe?g)$"),
):
    auth = _autorizar(request, token, item)
    # `_resolver_colecao` primeiro — nunca `_eh_item_raster` sozinho: um item de OUTRO inquilino (ou
    # inexistente) tem de dar 403 (invisível), não 422 "mosaico não suportado" (achado do adversário
    # interno desta trilha: sem isto, `/map` de item alheio vazava "existe, só que é mosaico").
    info = _resolver_colecao(auth, item)
    if info["tipo"] != "item":
        raise ErroAPI(422, "mapa_nao_suportado",
                      "OGC API Maps (/map) nesta passagem só serve item raster; mosaico não tem motor "
                      "de recorte por bbox arbitrário composto de várias cenas (ver ADR 20260910T2056 §5)",
                      {"item": item})
    if (width > limites.WMS_LARGURA_MAX or height > limites.WMS_ALTURA_MAX
            or width * height > limites.WMS_PIXELS_MAX):
        raise ErroAPI(400, "dimensao_excessiva",
                      f"width×height acima do teto ({width}×{height} px; teto "
                      f"{limites.WMS_LARGURA_MAX}×{limites.WMS_ALTURA_MAX} = {limites.WMS_PIXELS_MAX} px)")
    oeste, sul, leste, norte = _bbox_map(bbox)
    crs_saida = _crs_normalizar(crs)
    formato = "jpg" if f in ("jpg", "jpeg") else "png"
    fonte, _ = _fonte_do_item(auth, item, _asset_padrao(None, None))
    try:
        corpo = tiles.recorte(fonte, (oeste, sul, leste, norte), crs_saida, width, height,
                              formato=formato, transparente=True)
    except tiles.ErroTile as e:
        raise ErroAPI(422, "recorte_invalido", str(e)) from e
    except ErroAPI:
        raise
    except Exception as e:  # leitura do armazenamento falhou: nunca 500 mudo
        raise ErroAPI(502, "leitura_falhou", f"não foi possível renderizar o mapa: {e}") from e
    media = "image/jpeg" if formato == "jpg" else "image/png"
    return Response(corpo, media_type=media,
                    headers={"Cache-Control": CACHE_TILE, "Content-Crs": f"<{_crs_uri_saida(crs_saida)}>"})


__all__ = ["router"]
