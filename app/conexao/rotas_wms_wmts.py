"""Rotas do conector WMS/WMTS externo (item L6-02-b-wms-wmts; ADR 0019). Todas penduradas em
`/api/conexoes/{id}/...`, sobre uma conexão já registrada (`tipo` = `wms` ou `wmts`, item L6-02-a) — a URL da
conexão já passou pela validação de SSRF na criação (`app.conexao.rotas._url_ok`); toda chamada ao serviço
externo daqui em diante usa `app.conexao.wms_wmts`, que por sua vez usa só `app.conexao.seguranca.buscar_seguro`.

Cobertura (linha viva no handoff do item):
  GET  /api/conexoes/{id}/wms/capacidades        — GetCapabilities analisado (camadas/CRS/estilos/bbox)
  GET  /api/conexoes/{id}/wms/mapa               — proxy de GetMap; reprojeta com GDAL quando o CRS pedido
                                                    (padrão 3857) não está entre os que o serviço declara, mas
                                                    um CRS conhecido está (hoje: 4674 -> 3857)
  GET  /api/conexoes/{id}/wms/feicao             — proxy de GetFeatureInfo (clique no mapa)
  GET  /api/conexoes/{id}/wmts/capacidades       — GetCapabilities WMTS analisado (camadas/TileMatrixSets)
  GET  /api/conexoes/{id}/wmts/tile-info         — diz se o TileMatrixSet pedido é nativo 3857 (o MapLibre
                                                    consome direto, sem proxy) ou exige o proxy de reprojeção
  GET  /api/conexoes/{id}/wmts/tile/{tms}/{z}/{x}/{y} — proxy de tile: passthrough (credencial escondida,
                                                    cache em processo) quando o TileMatrixSet já é 3857;
                                                    mosaico + reprojeção via GDAL quando não é

Credencial: a MESMA lógica de `rotas.testar` (decifra em memória, só aqui, nunca sai na resposta nem em log) —
serviço WMS/WMTS autenticado (ex.: `Authorization: Bearer ...`) tem a credencial injetada nesta camada; o
navegador nunca vê a URL original nem o cabeçalho.

Cache: em processo, por (conexao_id, operação, parâmetros), TTL curto (`_CACHE_TTL_S`) e tamanho travado
(`_CACHE_MAX_ITENS`) — fronteira honesta: não é Redis nem cache compartilhado entre processos (não existe essa
peça na plataforma hoje); serve para não rebater a mesma tile/GetMap a cada movimento de mouse na MESMA sessão
de worker."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import APIRouter, Query, Response

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.conexao import credencial as credencial_mod
from app.conexao import seguranca, wms_wmts
from app.conexao.rotas import _carregar
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(prefix="/api/conexoes/{id}", tags=["wms_wmts"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
_CACHE_TTL_S = 60.0
_CACHE_MAX_ITENS = 256


@dataclass
class _EntradaCache:
    corpo: bytes
    content_type: str
    cabecalhos_extra: dict[str, str]
    expira_em: float


_cache: dict[str, _EntradaCache] = {}


def _cache_pegar(chave: str) -> _EntradaCache | None:
    item = _cache.get(chave)
    if item is None:
        return None
    if item.expira_em < time.monotonic():
        _cache.pop(chave, None)
        return None
    return item


def _cache_guardar(chave: str, item: _EntradaCache) -> None:
    if len(_cache) >= _CACHE_MAX_ITENS:
        # remove a entrada mais antiga (política simples: não é LRU real, é FIFO por ordem de inserção do
        # dict; suficiente para um cache de tamanho pequeno e TTL curto)
        _cache.pop(next(iter(_cache)), None)
    _cache[chave] = item


def _conexao(id: str, tipo_esperado: str, auth: Auth) -> dict:
    from app.catalogo.comum import uuid_ok

    cid = uuid_ok(id, "conexao_inexistente", "conexão inexistente")
    with db.db(auth.contexto()) as cur:
        r = _carregar(cur, cid)
    if r["tipo"] != tipo_esperado:
        raise ErroAPI(
            422, "tipo_de_conexao_errado", f"conexão é do tipo {r['tipo']!r}, esperado {tipo_esperado!r}",
            {"esperado": tipo_esperado, "recebido": r["tipo"]},
        )
    return r


def _cabecalhos_credencial(r: dict, auth: Auth) -> dict[str, str] | None:
    if not r["tem_credencial"]:
        return None
    with db.db(auth.contexto()) as cur:
        cur.execute("SELECT credencial_cifrada FROM plat.conexao WHERE id = %s::uuid", (r["id"],))
        bruta = cur.fetchone()["credencial_cifrada"]
    try:
        token = credencial_mod.decifrar(bruta, settings.PLAT_SECRET)
    except ValueError:
        return None
    return {"Authorization": f"Bearer {token}"}


def _bbox_de_query(bbox: str) -> tuple[float, float, float, float]:
    partes = bbox.split(",")
    if len(partes) != 4:
        raise ErroAPI(422, "bbox_invalido", "bbox precisa de 4 números separados por vírgula (minx,miny,maxx,maxy)")
    try:
        minx, miny, maxx, maxy = (float(p) for p in partes)
    except ValueError as e:
        raise ErroAPI(422, "bbox_invalido", "bbox com valor não numérico") from e
    if minx >= maxx or miny >= maxy:
        raise ErroAPI(422, "bbox_invalido", "bbox degenerado (min >= max)")
    return (minx, miny, maxx, maxy)


# ------------------------------------------------------------------ WMS


@router.get("/wms/capacidades", openapi_extra=LER)
def wms_capacidades(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    r = _conexao(id, "wms", auth)
    try:
        cap = wms_wmts.capacidades_wms(r["url"])
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wms_capabilities_falhou", f"não foi possível ler o GetCapabilities: {e}") from e

    def _camada_json(c: wms_wmts.Camada) -> dict:
        return {
            "nome": c.nome, "titulo": c.titulo, "resumo": c.resumo,
            "crs_suportados": list(c.crs_suportados),
            "estilos": [{"nome": es.nome, "titulo": es.titulo} for es in c.estilos],
            "bbox_lonlat": list(c.bbox_lonlat) if c.bbox_lonlat else None,
            "consultavel": c.consultavel,
            "filhas": [_camada_json(f) for f in c.filhas],
        }

    return {
        "versao": cap.versao, "titulo": cap.titulo,
        "formatos_getmap": list(cap.formatos_getmap),
        "formatos_getfeatureinfo": list(cap.formatos_getfeatureinfo),
        "getfeatureinfo_disponivel": cap.url_getfeatureinfo is not None,
        "camadas": [_camada_json(c) for c in cap.camadas],
    }


@router.get("/wms/mapa", openapi_extra=LER)
def wms_mapa(
    id: str, camada: str, largura: int = Query(256, ge=1), altura: int = Query(256, ge=1),
    crs: str = "EPSG:3857", bbox: str = Query(...), formato: str = "image/png", estilo: str = "",
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    r = _conexao(id, "wms", auth)
    bbox_t = _bbox_de_query(bbox)
    chave = f"mapa:{r['id']}:{camada}:{crs}:{bbox}:{largura}x{altura}:{formato}:{estilo}"
    encontrado = _cache_pegar(chave)
    if encontrado:
        return Response(
            content=encontrado.corpo, media_type=encontrado.content_type,
            headers={**encontrado.cabecalhos_extra, "X-Plat-Cache": "hit"},
        )
    try:
        cap = wms_wmts.capacidades_wms(r["url"])
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wms_capabilities_falhou", str(e)) from e

    crs_norm = crs.upper()
    reprojetado = False
    cabecalhos = _cabecalhos_credencial(r, auth)
    try:
        folha = cap.por_nome(camada)
    except wms_wmts.ErroConector as e:
        raise ErroAPI(404, "camada_inexistente", f"camada {camada!r} não existe neste serviço") from e

    if crs_norm in folha.crs_suportados or not folha.crs_suportados:
        url = wms_wmts.url_getmap(
            cap, camada=camada, crs=crs, bbox=bbox_t, largura=largura, altura=altura, formato=formato,
            estilo=estilo,
        )
        resultado = seguranca.buscar_seguro(
            url, metodo="GET", cabecalhos=cabecalhos, guardar_corpo=True,
            timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_MAPA_TIMEOUT_S,
            max_bytes=limites.CONEXAO_WMS_MAPA_MAX_BYTES,
        )
    else:
        # serviço não declara o CRS pedido: procura um CRS geográfico conhecido que ele declare (o caso do
        # portão de pronto — "serviço só em EPSG:4674") e reprojeta com GDAL depois de baixar.
        crs_origem = next((c for c in folha.crs_suportados if c.startswith("EPSG:")), None)
        if crs_origem is None:
            raise ErroAPI(
                422, "sem_crs_compativel",
                f"a camada só declara {list(folha.crs_suportados)}, nenhum reprojetável por esta trilha",
            )
        from pyproj import Transformer

        epsg_origem = int(crs_origem.split(":")[1])
        epsg_destino = int(crs_norm.split(":")[1]) if crs_norm.startswith("EPSG:") else 3857
        transformador = Transformer.from_crs(epsg_destino, epsg_origem, always_xy=True)
        x0, y0 = transformador.transform(bbox_t[0], bbox_t[1])
        x1, y1 = transformador.transform(bbox_t[2], bbox_t[3])
        bbox_origem = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        url = wms_wmts.url_getmap(
            cap, camada=camada, crs=crs_origem, bbox=bbox_origem, largura=largura, altura=altura, formato=formato,
            estilo=estilo,
        )
        resultado = seguranca.buscar_seguro(
            url, metodo="GET", cabecalhos=cabecalhos, guardar_corpo=True,
            timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_MAPA_TIMEOUT_S,
            max_bytes=limites.CONEXAO_WMS_MAPA_MAX_BYTES,
        )
        if resultado.ok and formato == "image/png":
            resultado_corpo = wms_wmts.reprojetar_imagem(
                resultado.corpo, bbox_origem=bbox_origem, epsg_origem=epsg_origem, largura=largura,
                altura=altura, epsg_destino=epsg_destino,
            )
            reprojetado = True
            resultado = resultado.__class__(
                ok=True, status=resultado.status, mensagem=resultado.mensagem, url_final=resultado.url_final,
                latencia_ms=resultado.latencia_ms, saltos=resultado.saltos, corpo=resultado_corpo,
            )

    if not resultado.ok:
        raise ErroAPI(502, "wms_mapa_falhou", resultado.mensagem)
    cabecalhos_extra = {"X-Plat-Reprojetado": "1" if reprojetado else "0"}
    _cache_guardar(chave, _EntradaCache(
        corpo=resultado.corpo, content_type=formato, cabecalhos_extra=cabecalhos_extra,
        expira_em=time.monotonic() + _CACHE_TTL_S,
    ))
    return Response(content=resultado.corpo, media_type=formato, headers={**cabecalhos_extra, "X-Plat-Cache": "miss"})


@router.get("/wms/feicao", openapi_extra=LER)
def wms_feicao(
    id: str, camada: str, coluna: int, linha: int, largura: int = Query(256, ge=1), altura: int = Query(256, ge=1),
    crs: str = "EPSG:3857", bbox: str = Query(...), formato_info: str = "application/json",
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    r = _conexao(id, "wms", auth)
    bbox_t = _bbox_de_query(bbox)
    try:
        cap = wms_wmts.capacidades_wms(r["url"])
        url = wms_wmts.url_getfeatureinfo(
            cap, camada=camada, crs=crs, bbox=bbox_t, largura=largura, altura=altura, coluna=coluna, linha=linha,
            formato_info=formato_info,
        )
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wms_getfeatureinfo_indisponivel", str(e)) from e
    cabecalhos = _cabecalhos_credencial(r, auth)
    resultado = seguranca.buscar_seguro(
        url, metodo="GET", cabecalhos=cabecalhos, guardar_corpo=True,
        timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_MAPA_TIMEOUT_S,
        max_bytes=limites.CONEXAO_WMS_FEICAO_MAX_BYTES,
    )
    if not resultado.ok:
        raise ErroAPI(502, "wms_feicao_falhou", resultado.mensagem)
    return Response(content=resultado.corpo, media_type=formato_info)


# ------------------------------------------------------------------ WMTS


@router.get("/wmts/capacidades", openapi_extra=LER)
def wmts_capacidades(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    r = _conexao(id, "wmts", auth)
    try:
        cap = wms_wmts.capacidades_wmts(r["url"])
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wmts_capabilities_falhou", f"não foi possível ler o GetCapabilities: {e}") from e
    return {
        "titulo": cap.titulo,
        "camadas": [
            {
                "nome": c.nome, "titulo": c.titulo, "formatos": list(c.formatos),
                "tile_matrix_sets": list(c.tile_matrix_sets), "modelo": "restful" if c.template_restful else "kvp",
            }
            for c in cap.camadas
        ],
        "tile_matrix_sets": {
            nome: {"crs": tms.crs, "nativo_3857": tms.nativo_3857(), "niveis": len(tms.niveis)}
            for nome, tms in cap.tile_matrix_sets.items()
        },
    }


@router.get("/wmts/tile-info", openapi_extra=LER)
def wmts_tile_info(
    id: str, camada: str, tile_matrix_set: str, formato: str = "image/png",
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    r = _conexao(id, "wmts", auth)
    try:
        cap = wms_wmts.capacidades_wmts(r["url"])
        tms = cap.tile_matrix_sets.get(tile_matrix_set)
        if tms is None:
            raise ErroAPI(404, "tile_matrix_set_inexistente", tile_matrix_set)
        if tms.nativo_3857():
            template = wms_wmts.url_wmts_tile_direta(
                cap, camada=camada, tile_matrix_set=tile_matrix_set, formato=formato,
            )
            return {"direto": True, "template": template}
        proxy_base = f"/api/conexoes/{id}/wmts/tile/{tile_matrix_set}"
        return {
            "direto": False,
            "proxy_template": f"{proxy_base}/{{z}}/{{x}}/{{y}}?camada={camada}&formato={formato}",
        }
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wmts_capabilities_falhou", str(e)) from e


@router.get("/wmts/tile/{tile_matrix_set}/{z}/{x}/{y}", openapi_extra=LER)
def wmts_tile(
    id: str, tile_matrix_set: str, z: int, x: int, y: int, camada: str, formato: str = "image/png",
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    r = _conexao(id, "wmts", auth)
    chave = f"tile:{r['id']}:{tile_matrix_set}:{z}:{x}:{y}:{camada}:{formato}"
    encontrado = _cache_pegar(chave)
    if encontrado:
        return Response(
            content=encontrado.corpo, media_type=encontrado.content_type,
            headers={**encontrado.cabecalhos_extra, "X-Plat-Cache": "hit"},
        )
    try:
        cap = wms_wmts.capacidades_wmts(r["url"])
    except wms_wmts.ErroConector as e:
        raise ErroAPI(502, "wmts_capabilities_falhou", str(e)) from e
    tms = cap.tile_matrix_sets.get(tile_matrix_set)
    if tms is None:
        raise ErroAPI(404, "tile_matrix_set_inexistente", tile_matrix_set)

    cabecalhos = _cabecalhos_credencial(r, auth)
    if tms.nativo_3857():
        url = wms_wmts.url_wmts_tile_direta(cap, camada=camada, tile_matrix_set=tile_matrix_set, formato=formato)
        url = url.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        resultado = seguranca.buscar_seguro(
            url, metodo="GET", cabecalhos=cabecalhos, guardar_corpo=True,
            timeout_conectar=limites.CONEXAO_CONECTAR_TIMEOUT_S, timeout_ler=limites.CONEXAO_WMS_MAPA_TIMEOUT_S,
            max_bytes=limites.CONEXAO_WMTS_TILE_MAX_BYTES,
        )
        if not resultado.ok:
            raise ErroAPI(502, "wmts_tile_falhou", resultado.mensagem)
        corpo, reprojetado = resultado.corpo, False
    else:
        try:
            resultado_tile = wms_wmts.mosaico_tile_reprojetado(
                cap, camada=camada, tile_matrix_set=tile_matrix_set, z=z, x=x, y=y, formato=formato,
            )
        except wms_wmts.ErroConector as e:
            raise ErroAPI(502, "wmts_mosaico_falhou", str(e)) from e
        corpo, reprojetado = resultado_tile.png, resultado_tile.reprojetado

    cabecalhos_extra = {"X-Plat-Reprojetado": "1" if reprojetado else "0"}
    _cache_guardar(chave, _EntradaCache(corpo=corpo, content_type=formato, cabecalhos_extra=cabecalhos_extra,
                                        expira_em=time.monotonic() + _CACHE_TTL_S))
    return Response(content=corpo, media_type=formato, headers={**cabecalhos_extra, "X-Plat-Cache": "miss"})
