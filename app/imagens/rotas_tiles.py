"""Serviço de ladrilho raster por inquilino (item L1-02-tiles-token; ADR 20260907T0300).

Contrato de URL (decisão C6 do conceito L1 — token LONGO NO CAMINHO, nunca em parâmetro de consulta,
nunca URL que expira: o endereço é colado num mapa web de terceiro e fica lá por anos):

    /svc/<token>/raster/<item>/{z}/{x}/{y}[.png|.jpg|.webp]   ladrilho XYZ
    /svc/<token>/raster/<item>/tilejson.json                  TileJSON 3.0.0
    /svc/<token>/raster/<item>/wmts                           WMTS 1.0.0 KVP (GetCapabilities/GetTile)
    /svc/<token>/raster/<item>/wmts/1.0.0/WMTSCapabilities.xml  WMTS RESTful (o que o QGIS guarda)
    /svc/<token>/raster/<item>/info.json                      extensão, bandas, tipo do dado
    /svc/<token>/mosaico/<colecao>/{z}/{x}/{y}[.ext]          mosaico da coleção (mais recente por cima)

Três coisas que este módulo NÃO faz, de propósito:
1. não aceita endereço de arquivo do cliente (não existe `?url=`): o caminho do COG NASCE da consulta ao
   catálogo do inquilino do token, então não há entrada que vire leitura arbitrária (SSRF);
2. não aceita cookie de sessão: a porta é para cliente de mapa (QGIS, ArcGIS, navegador de terceiro), e
   sessão nesta porta seria CSRF de graça;
3. não guarda o token no registro de uso: guarda o `token_id` (mesma regra de `plat.log_acesso`).

Código de recusa: 403 (não 401). O token está no CAMINHO da URL — não existe credencial a renegociar, e
um 401 faria o navegador do usuário abrir caixa de senha por um recurso que nunca a aceitaria. Revogação,
expiração, escopo insuficiente, Referer/IP fora da restrição e item de outro inquilino respondem todos 403
(item inexistente também: 404 confirmaria a existência do item para quem não pode vê-lo)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app import db, objetos
from app.acervo import arquivos as arquivos_acervo
from app.auth import escopos as esc
from app.auth import sessao as sessao_auth
from app.auth.sessao import _auth_de_token
from app.erros import ErroAPI
from app.imagens import leitura, tiles
from app.imagens import pgstac as ps
from app.imagens import wmts as wmts_doc
from app.settings import settings

router = APIRouter(tags=["tiles"])

X = {"x-auth": "T", "x-privilegio": "proprio"}
CACHE_TILE = "public, max-age=300"
FORMATO_PADRAO = "png"
# resolução de item -> objeto: cara (2 consultas) e estável. Cache curto em processo; a autorização NÃO
# passa por aqui (essa é conferida a cada requisição, com o cache de 5 s do `_autorizar`).
_FONTES: dict[tuple[int, str, str], tuple[float, Any]] = {}
FONTE_TTL_S = 60.0
# cache de autorização: o portão promete 403 em <= 5 s depois de revogar. São DOIS caches em série — este,
# em processo, e o do `auth_request` no nginx — e o pior caso é a soma. Por isso 2 s aqui e 2 s lá: 4 s < 5 s.
_AUTH: dict[str, tuple[float, Any]] = {}
AUTH_TTL_S = 2.0
# teto dos dois caches em processo: eles vivem em dicionário, e um serviço público é exatamente o
# lugar onde alguém manda um milhão de tokens diferentes para inchar a memória do processo. Ao passar
# do teto o dicionário é esvaziado inteiro (é cache de segundos; reconstruir custa uma consulta).
CACHE_MAX = 5000


def _agora() -> float:
    return time.monotonic()


def _guardar(cache: dict, chave, valor) -> None:
    if len(cache) >= CACHE_MAX:
        cache.clear()
    cache[chave] = (_agora(), valor)


def _autorizar(request: Request, token: str, item: str | None = None):
    """Token do caminho -> Auth, com cache de 5 s. Toda recusa vira 403 (ver docstring do módulo)."""
    chave = f"{token}|{request.headers.get('referer', '')}|{request.headers.get('origin', '')}|{request.client.host if request.client else ''}"  # noqa: E501
    guardado = _AUTH.get(chave)
    if guardado and (_agora() - guardado[0]) < AUTH_TTL_S:
        auth = guardado[1]
        if isinstance(auth, ErroAPI):
            raise auth
    else:
        try:
            auth = _auth_de_token(request, token)
        except ErroAPI as e:
            # `ErroAPI` guarda o código curto em `.erro` (não `.codigo`): trocar isso aqui devolvia 500 e o
            # nginx traduzia "auth request unexpected status: 500" — token inválido virava erro do servidor.
            recusa = ErroAPI(403, e.erro, e.mensagem, e.detalhe)
            _guardar(_AUTH, chave, recusa)
            raise recusa from e
        _guardar(_AUTH, chave, auth)
    if not esc.cobre(auth.escopos, "tiles:ler", item) and not esc.cobre(auth.escopos, "imagens:ler"):
        raise ErroAPI(403, "escopo_insuficiente", "o token não tem o escopo tiles:ler",
                      {"exigido": f"tiles:ler:{item}" if item else "tiles:ler", "token_tem": list(auth.escopos)})
    request.state.auth = auth
    request.state.tenant_id = auth.tenant_id
    request.state.usuario_id = auth.usuario_id
    request.state.token_id = auth.token_id
    return auth


def esquecer_autorizacao() -> None:
    """Usada pelo teste de revogação para medir o pior caso do cache (e pelo desligamento)."""
    _AUTH.clear()
    _FONTES.clear()


PREFIXO_ACERVO = "acervo://"


def _href_do_asset(item_stac: dict, asset: str) -> str:
    ativos = item_stac.get("assets") or {}
    if asset not in ativos:
        raise ErroAPI(404, "asset_inexistente", f"o item não tem o asset '{asset}'",
                      {"disponiveis": sorted(ativos)})
    href = ativos[asset].get("href") or ""
    # `/api/objetos/<chave>`: COG no balde do inquilino (L1-01). `acervo://<caminho>`: raster do acervo da CASA,
    # lido do disco onde ele já está (item L6-01-i) — nunca copiado para o balde, guardrail de disco D21.
    if href.startswith("/api/objetos/") or href.startswith(PREFIXO_ACERVO):
        return href
    raise ErroAPI(422, "asset_externo",
                  "este asset não é um objeto do armazenamento da plataforma nem um arquivo do acervo da casa",
                  {"asset": asset})


def _chave_do_asset(item_stac: dict, asset: str) -> str:
    href = _href_do_asset(item_stac, asset)
    if href.startswith(PREFIXO_ACERVO):
        raise ErroAPI(422, "asset_externo", "asset do acervo da casa não é objeto do armazenamento",
                      {"asset": asset})
    return href[len("/api/objetos/"):]


def _fonte_do_item(auth, item: str, asset: str) -> tuple[tiles.Fonte, dict]:
    """(fonte de leitura, item STAC). 403 quando o item não é do inquilino do token (nunca 404: a
    diferença entre 'não existe' e 'é de outro' é informação que não se dá)."""
    chave_cache = (auth.tenant_id, item, asset)
    guardado = _FONTES.get(chave_cache)
    if guardado and (_agora() - guardado[0]) < FONTE_TTL_S:
        return guardado[1]
    with db.db(auth.contexto_leitura()) as cur:
        cur.execute(
            "SELECT colecao, estado FROM plat.raster_item WHERE tenant_id = %s AND item_id = %s LIMIT 1",
            (auth.tenant_id, item),
        )
        linha = cur.fetchone()
        if linha is None or linha["estado"] != "ativo":
            raise ErroAPI(403, "item_indisponivel",
                          "item de imagem inexistente, excluído ou de outro inquilino", {"item": item})
        stac = ps.item_obter(cur, auth.tenant_id, linha["colecao"], item)
    if stac is None:
        raise ErroAPI(403, "item_indisponivel", "item de imagem sem registro STAC", {"item": item})
    href = _href_do_asset(stac, asset)
    if href.startswith(PREFIXO_ACERVO):
        # arquivo do acervo da casa: caminho local dentro da raiz configurada, sem sessão S3 e sem cópia
        alvo = arquivos_acervo.resolver(href[len(PREFIXO_ACERVO):])
        if not alvo.is_file():
            raise ErroAPI(422, "arquivo_ausente", "o arquivo do acervo saiu do disco desta instalação",
                          {"item": item})
        fonte = tiles.Fonte(str(alvo), tiles.env_gdal(), None)
    else:
        chave = href[len("/api/objetos/"):]
        caminho, opcoes = objetos.fonte_gdal(chave)
        tiles.preparar_ambiente_s3(settings.PLAT_GARAGE_URL or "")
        fonte = tiles.Fonte(caminho, tiles.env_gdal(), tiles.sessao_s3(opcoes))
    _guardar(_FONTES, chave_cache, (fonte, stac))
    return fonte, stac


def _faixa(rescale: str | None) -> list[tuple[float, float]] | None:
    if not rescale:
        return None
    partes = rescale.split(",")
    if len(partes) % 2 != 0 or len(partes) > 8:
        raise ErroAPI(422, "faixa_invalida", "faixa (rescale) tem de vir em pares min,max", {"faixa": rescale})
    try:
        numeros = [float(p) for p in partes]
    except ValueError as e:
        raise ErroAPI(422, "faixa_invalida", "faixa (rescale) só aceita números", {"faixa": rescale}) from e
    return [(numeros[i], numeros[i + 1]) for i in range(0, len(numeros), 2)]


def _bandas(bandas: str | None) -> list[int] | None:
    if not bandas:
        return None
    try:
        lista = [int(b) for b in bandas.split(",")]
    except ValueError as e:
        raise ErroAPI(422, "bandas_invalidas", "bandas tem de ser lista de inteiros (ex.: 3,2,1)",
                      {"bandas": bandas}) from e
    if not lista or len(lista) > 4 or any(b < 1 or b > 64 for b in lista):
        raise ErroAPI(422, "bandas_invalidas", "de 1 a 4 bandas, cada uma entre 1 e 64", {"bandas": bandas})
    return lista


def _asset_padrao(expressao: str | None, pedido: str | None) -> str:
    if pedido:
        if pedido not in ("visual", "cientifico"):
            raise ErroAPI(422, "asset_invalido", "asset tem de ser 'visual' ou 'cientifico'", {"asset": pedido})
        return pedido
    # expressão precisa das bandas originais; sem expressão, o visual (8 bits, já esticado) é mais barato
    return "cientifico" if expressao else "visual"


def _consulta_render(expressao, bandas, rescale, colormap, asset) -> str:
    import urllib.parse

    itens = [(k, v) for k, v in (("expressao", expressao), ("bandas", bandas), ("faixa", rescale),
                                 ("colormap", colormap), ("asset", asset)) if v]
    return urllib.parse.urlencode(itens)


def _servir(request: Request, auth, item: str, z: int, x: int, y: int, formato: str,
            expressao, bandas, faixa, colormap, asset) -> Response:
    asset_final = _asset_padrao(expressao, asset)
    fonte, _ = _fonte_do_item(auth, item, asset_final)
    inicio = time.perf_counter()
    try:
        corpo = tiles.ladrilho(fonte, z, x, y, formato=formato, expressao=expressao,
                              bandas=_bandas(bandas), rescale=_faixa(faixa), colormap=colormap)
    except tiles.ForaDaCobertura:
        leitura.contar(auth.tenant_id, auth.token_id, item, 0)
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    except tiles.ErroTile as e:
        leitura.contar(auth.tenant_id, auth.token_id, item, 0, erro=True)
        raise ErroAPI(422, "ladrilho_invalido", str(e)) from e
    except Exception as e:  # falha de leitura do armazenamento: conta como erro do token e sobe 502
        leitura.contar(auth.tenant_id, auth.token_id, item, 0, erro=True)
        raise ErroAPI(502, "leitura_falhou", f"não foi possível ler a imagem: {e}") from e
    ms = (time.perf_counter() - inicio) * 1000
    leitura.contar(auth.tenant_id, auth.token_id, item, len(corpo))
    return Response(
        content=corpo,
        media_type=tiles.FORMATOS[formato],
        headers={"Cache-Control": CACHE_TILE, "Server-Timing": f"ladrilho;dur={ms:.1f}"},
    )


# ---------------------------------------------------------------------------- TileJSON / info
def _base(token: str, item: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/svc/{token}/raster/{item}"


@router.get("/svc/{token}/raster/{item}/tilejson.json", openapi_extra=X, summary="TileJSON 3.0.0 do item")
def tilejson(
    request: Request, token: str, item: str,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    auth = _autorizar(request, token, item)
    asset_final = _asset_padrao(expressao, asset)
    fonte, stac = _fonte_do_item(auth, item, asset_final)
    info = tiles.informacao(fonte)
    consulta = _consulta_render(expressao, bandas, faixa, colormap, asset)
    url = f"{_base(token, item)}/{{z}}/{{x}}/{{y}}.{ 'jpg' if formato in ('jpg', 'jpeg') else formato}"
    if consulta:
        url += f"?{consulta}"
    corpo = {
        "tilejson": "3.0.0",
        "name": (stac.get("properties") or {}).get("title") or item,
        "tiles": [url],
        "minzoom": info["minzoom"],
        "maxzoom": info["maxzoom"],
        "bounds": info["bounds"],
        "center": [(info["bounds"][0] + info["bounds"][2]) / 2,
                   (info["bounds"][1] + info["bounds"][3]) / 2, info["minzoom"]],
        "scheme": "xyz",
        "attribution": (stac.get("properties") or {}).get("plat:atribuicao"),
    }
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/raster/{item}/info.json", openapi_extra=X, summary="extensão e bandas do item")
def info_json(request: Request, token: str, item: str,
              asset: str | None = Query(None, pattern="^(visual|cientifico)$")):
    auth = _autorizar(request, token, item)
    fonte, stac = _fonte_do_item(auth, item, _asset_padrao(None, asset))
    corpo = dict(tiles.informacao(fonte))
    corpo["item"] = item
    corpo["assets"] = sorted((stac.get("assets") or {}))
    corpo["colormaps"] = sorted(tiles.COLORMAPS)
    corpo["formatos"] = sorted(set(tiles.FORMATOS.values()))
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- WMTS
def _capabilities(token: str, item: str, auth, expressao, bandas, faixa, colormap, asset) -> str:
    asset_final = _asset_padrao(expressao, asset)
    fonte, stac = _fonte_do_item(auth, item, asset_final)
    info = tiles.informacao(fonte)
    titulo = (stac.get("properties") or {}).get("title") or item
    return wmts_doc.capabilities(
        base=_base(token, item),
        identificador=item,
        titulo=titulo,
        bounds=info["bounds"],
        zoom_min=0,
        zoom_max=max(info["maxzoom"], 18),
        formatos=["image/png", "image/jpeg", "image/webp"],
        consulta=_consulta_render(expressao, bandas, faixa, colormap, asset),
        resumo=f"{info['bandas']} banda(s), tipo {info['dtype']}; grade WebMercatorQuad.",
    )


@router.get("/svc/{token}/raster/{item}/wmts/1.0.0/WMTSCapabilities.xml", openapi_extra=X,
            summary="WMTS 1.0.0 GetCapabilities (forma REST)")
def wmts_rest(
    request: Request, token: str, item: str,
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    auth = _autorizar(request, token, item)
    xml = _capabilities(token, item, auth, expressao, bandas, faixa, colormap, asset)
    return Response(xml, media_type="application/xml",
                    headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/raster/{item}/wmts", openapi_extra=X,
            summary="WMTS 1.0.0 KVP (GetCapabilities e GetTile)")
def wmts_kvp(
    request: Request, token: str, item: str,
    service: str = Query("WMTS", alias="SERVICE"),
    request_: str = Query("GetCapabilities", alias="REQUEST"),
    version: str = Query("1.0.0", alias="VERSION"),
    layer: str | None = Query(None, alias="LAYER"),
    tilematrixset: str | None = Query(None, alias="TILEMATRIXSET"),
    tilematrix: str | None = Query(None, alias="TILEMATRIX"),
    tilerow: int | None = Query(None, alias="TILEROW"),
    tilecol: int | None = Query(None, alias="TILECOL"),
    format_: str | None = Query(None, alias="FORMAT"),
    style: str | None = Query(None, alias="STYLE"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    auth = _autorizar(request, token, item)
    if (service or "").upper() != "WMTS":
        raise ErroAPI(422, "servico_invalido", "SERVICE tem de ser WMTS", {"SERVICE": service})
    operacao = (request_ or "").lower()
    if operacao == "getcapabilities":
        xml = _capabilities(token, item, auth, expressao, bandas, faixa, colormap, asset)
        return Response(xml, media_type="application/xml",
                        headers={"Cache-Control": "no-store, must-revalidate"})
    if operacao != "gettile":
        raise ErroAPI(422, "operacao_invalida", "REQUEST tem de ser GetCapabilities ou GetTile",
                      {"REQUEST": request_})
    if tilematrix is None or tilerow is None or tilecol is None:
        raise ErroAPI(422, "parametro_ausente", "GetTile exige TILEMATRIX, TILEROW e TILECOL",
                      {"TILEMATRIX": tilematrix, "TILEROW": tilerow, "TILECOL": tilecol})
    if tilematrixset and tilematrixset != wmts_doc.TMS_ID:
        raise ErroAPI(422, "grade_invalida", f"a única grade servida é {wmts_doc.TMS_ID}",
                      {"TILEMATRIXSET": tilematrixset})
    if layer and layer != item:
        raise ErroAPI(422, "camada_invalida", "LAYER tem de ser o identificador do item",
                      {"LAYER": layer, "esperado": item})
    formato = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(
        (format_ or "image/png").lower())
    if formato is None:
        raise ErroAPI(422, "formato_desconhecido", "FORMAT aceito: image/png, image/jpeg, image/webp",
                      {"FORMAT": format_})
    try:
        z = int(str(tilematrix).split(":")[-1])
    except ValueError as e:
        raise ErroAPI(422, "tilematrix_invalido", "TILEMATRIX tem de ser o nível de zoom",
                      {"TILEMATRIX": tilematrix}) from e
    return _servir(request, auth, item, z, int(tilecol), int(tilerow), formato,
                   expressao, bandas, faixa, colormap, asset)


# ---------------------------------------------------------------------------- XYZ
@router.get("/svc/{token}/raster/{item}/{z}/{x}/{y}.{ext}", openapi_extra=X,
            summary="ladrilho XYZ do item com extensão no caminho")
def tile_xyz_ext(
    request: Request, token: str, item: str, z: int, x: int, y: int, ext: str,
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    if ext not in tiles.FORMATOS:
        raise ErroAPI(404, "formato_desconhecido", f"formato de ladrilho desconhecido: {ext}",
                      {"aceitos": sorted(tiles.FORMATOS)})
    auth = _autorizar(request, token, item)
    return _servir(request, auth, item, z, x, y, ext, expressao, bandas, faixa, colormap, asset)


@router.get("/svc/{token}/raster/{item}/{z}/{x}/{y}", openapi_extra=X, summary="ladrilho XYZ do item")
def tile_xyz(
    request: Request, token: str, item: str, z: int, x: int, y: int,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX,
                                  description="expressão sobre bandas, ex.: (b4-b3)/(b4+b3) para NDVI"),
    bandas: str | None = Query(None, max_length=32, description="bandas na ordem de saída, ex.: 3,2,1"),
    faixa: str | None = Query(None, max_length=64, description="faixa de valores min,max por banda"),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    auth = _autorizar(request, token, item)
    return _servir(request, auth, item, z, x, y, formato, expressao, bandas, faixa, colormap, asset)


# ---------------------------------------------------------------------------- mosaico por coleção
@router.get("/svc/{token}/mosaico/{colecao}/{z}/{x}/{y}", openapi_extra=X,
            summary="ladrilho do mosaico de uma coleção (mais recente por cima)")
def tile_mosaico(
    request: Request, token: str, colecao: str, z: int, x: int, y: int,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
    limite: int = Query(6, ge=1, le=12, description="máximo de cenas candidatas por ladrilho"),
):
    """Mosaico simples e declarado: as cenas da coleção que tocam o ladrilho, da mais recente para a mais
    antiga, e o PRIMEIRO pixel com dado vence (`first`). Não há linha de costura nem escolha por atributo
    (decisão C9 do conceito: Seamline e Closest to Viewpoint ficam FORA, com motivo)."""
    auth = _autorizar(request, token)
    if not ps.colecao_pertence(colecao, auth.tenant_id):
        raise ErroAPI(403, "colecao_indisponivel", "coleção inexistente ou de outro inquilino",
                      {"colecao": colecao})
    oeste, sul, leste, norte = tiles.TMS.bounds(tiles.TMS.tile(0, 0, 0).__class__(x=x, y=y, z=z))
    with db.db(auth.contexto_leitura()) as cur:
        busca = ps.buscar(cur, {"collections": [colecao], "bbox": [oeste, sul, leste, norte],
                                "limit": limite, "sortby": [{"field": "datetime", "direction": "desc"}]})
    feicoes = busca.get("features") or []
    if not feicoes:
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    ultima = None
    for f in feicoes:
        try:
            return _servir(request, auth, f["id"], z, x, y, formato, expressao, bandas, faixa,
                           colormap, asset)
        except ErroAPI as e:
            ultima = e
            continue
    raise ultima or ErroAPI(204, "sem_dado", "nenhuma cena da coleção cobre este ladrilho")


# ---------------------------------------------------------------------------- autorização para o nginx
@router.get("/api/tiles/autorizar", include_in_schema=False)
def autorizar_subrequisicao(request: Request):
    """Subrequisição do `auth_request` do nginx (ADR 20260907T0300): o nginx confere o token ANTES de
    responder do cache, porque a chave de cache do ladrilho NÃO tem o token (dois tokens do mesmo
    inquilino compartilham o ladrilho). Sem isto, revogar um token não tiraria do ar o que já está em
    cache. 204 = pode; 403 = não pode. Rota interna: o nginx a expõe só como `internal`.

    O token vem em cabeçalho (`X-Plat-Token`) e não no caminho porque quem monta a subrequisição é o
    nginx, não o cliente; a URL do cliente continua sendo a do contrato C6."""
    token = request.headers.get("x-plat-token") or ""
    item = request.headers.get("x-plat-item") or None
    tipo = (request.headers.get("x-plat-tipo") or "raster").lower()
    auth = _autorizar(request, token, item)
    # A chave de cache do ladrilho NÃO tem o token nem o inquilino. Logo é AQUI que se confere que o
    # recurso pedido é do inquilino do token — senão um token válido de OUTRO inquilino recebe do cache
    # o ladrilho alheio sem a aplicação ser consultada (achado real desta bancada em 07/09, antes do
    # conserto: token de `demo2` recebeu 200 num item de `demo`).
    if item:
        if tipo == "mosaico":
            if not ps.colecao_pertence(item, auth.tenant_id):
                raise ErroAPI(403, "colecao_indisponivel", "coleção inexistente ou de outro inquilino",
                              {"colecao": item})
        else:
            _fonte_do_item(auth, item, "visual")
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------- contagem por token
@router.get("/api/tiles/leituras", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"},
            summary="contagem de ladrilhos servidos por token")
def leituras(dias: int = Query(30, ge=1, le=365),
             auth=sessao_auth.autenticado(escopo_token="catalogo:ler")):
    leitura.descarregar()
    with db.db(auth.contexto()) as cur:
        linhas = leitura.contagem(cur, auth.tenant_id, dias)
    return JSONResponse({"dias": dias, "tokens": [
        {**li, "primeiro_em": li["primeiro_em"].isoformat() if li["primeiro_em"] else None,
         "ultimo_em": li["ultimo_em"].isoformat() if li["ultimo_em"] else None,
         "revogado_em": li["revogado_em"].isoformat() if li["revogado_em"] else None}
        for li in linhas]}, headers={"Cache-Control": "no-store, must-revalidate"})


__all__ = ["router", "esquecer_autorizacao"]
