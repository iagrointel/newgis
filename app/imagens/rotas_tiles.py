"""Serviço de ladrilho raster por inquilino (item L1-02-tiles-token; ADR 20260907T0300).

Contrato de URL (decisão C6 do conceito L1 — token LONGO NO CAMINHO, nunca em parâmetro de consulta,
nunca URL que expira: o endereço é colado num mapa web de terceiro e fica lá por anos):

    /svc/<token>/raster/<item>/{z}/{x}/{y}[.png|.jpg|.webp]   ladrilho XYZ
    /svc/<token>/raster/<item>/tilejson.json                  TileJSON 3.0.0
    /svc/<token>/raster/<item>/wmts                           WMTS 1.0.0 KVP (GetCapabilities/GetTile)
    /svc/<token>/raster/<item>/wmts/1.0.0/WMTSCapabilities.xml  WMTS RESTful (o que o QGIS guarda)
    /svc/<token>/raster/<item>/info.json                      extensão, bandas, tipo do dado
    /svc/<token>/raster/<item>/estatisticas.json               mín/máx/média/desvio/percentis 2-98
    /svc/<token>/mosaico/<X>/{z}/{x}/{y}[.ext]                mosaico (X = uuid de mosaico REGISTRADO,
                                                               item L1-07 — busca STAC nomeada com
                                                               várias coleções/filtro/ordenação; OU
                                                               X = nome de coleção completo, o
                                                               comportamento ad-hoc antigo, coleção
                                                               inteira, mais recente por cima)
    /svc/<token>/mosaico/<uuid>/tilejson.json                 TileJSON 3.0.0 do mosaico registrado
    /svc/<token>/mosaico/<uuid>/wmts[/1.0.0/WMTSCapabilities.xml]  WMTS 1.0.0 do mosaico registrado
    /svc/<token>/mosaico/<uuid>/pegadas                       GeoJSON das pegadas (item L1-07)

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
from app.imagens import mosaico as mo
from app.imagens import pgstac as ps
from app.imagens import predefinicoes as pred
from app.imagens import wmts as wmts_doc
from app.settings import settings

router = APIRouter(tags=["tiles"])

X = {"x-auth": "T", "x-privilegio": "proprio"}
CACHE_TILE = "public, max-age=300"
# a porta serve mapa web de terceiro (docstring do módulo); sem isto o editor de estilo (e qualquer
# cliente MapLibre fora do domínio da plataforma) não consegue usar a imagem como textura WebGL — o
# navegador marca <img crossorigin> sem cabeçalho de resposta como falha de carregamento, não como aviso.
CORS = "*"
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


def _consulta_render(expressao, bandas, rescale, colormap, asset, predef=None) -> str:
    import urllib.parse

    itens = [(k, v) for k, v in (("expressao", expressao), ("bandas", bandas), ("faixa", rescale),
                                 ("colormap", colormap), ("asset", asset), ("predef", predef)) if v]
    return urllib.parse.urlencode(itens)


def _resolver_predef(auth, item: str, predef: str, expressao, bandas, colormap, asset):
    """`predef` (item L1-02-f) -> (`Resolvido`, asset efetivo). Usa SEMPRE o asset científico quando o
    cliente não pediu o visual explicitamente: uma predefinição controla esticamento/bandas a partir da
    estatística do item, e o asset visual já vem pré-esticado em 8 bits — a mesma razão pela qual uma
    `expressao=` explícita hoje já força o científico (`_asset_padrao`)."""
    asset_efetivo = asset or "cientifico"
    _, stac = _fonte_do_item(auth, item, asset_efetivo)
    with db.db(auth.contexto_leitura()) as cur:
        resolvido = pred.resolver(cur, auth.tenant_id, item, predef, stac, asset_efetivo)
    return resolvido, asset_efetivo


def _servir(request: Request, auth, item: str, z: int, x: int, y: int, formato: str,
            expressao, bandas, faixa, colormap, asset, *, predef: str | None = None) -> Response:
    resolvido = None
    if predef:
        resolvido, asset = _resolver_predef(auth, item, predef, expressao, bandas, colormap, asset)
        if resolvido.hillshade:
            fonte, _ = _fonte_do_item(auth, item, asset)
            inicio = time.perf_counter()
            try:
                corpo = pred.renderizar_hillshade(
                    fonte, banda=(resolvido.bandas or [1])[0], formato=formato,
                    resampling=resolvido.resampling, nodata_transparente=resolvido.nodata_transparente,
                    tile=(z, x, y),
                )
            except tiles.ForaDaCobertura:
                leitura.contar(auth.tenant_id, auth.token_id, item, 0)
                return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
            except tiles.ErroTile as e:
                leitura.contar(auth.tenant_id, auth.token_id, item, 0, erro=True)
                raise ErroAPI(422, "ladrilho_invalido", str(e)) from e
            ms = (time.perf_counter() - inicio) * 1000
            leitura.contar(auth.tenant_id, auth.token_id, item, len(corpo))
            return Response(content=corpo, media_type=tiles.FORMATOS[formato],
                            headers={"Cache-Control": CACHE_TILE, "Server-Timing": f"ladrilho;dur={ms:.1f}"})
        expressao = expressao or resolvido.expressao
        bandas = bandas or (",".join(str(b) for b in resolvido.bandas) if resolvido.bandas else None)
        colormap = colormap or resolvido.colormap
    asset_final = _asset_padrao(expressao, asset)
    fonte, _ = _fonte_do_item(auth, item, asset_final)
    faixa_final = _faixa(faixa) if faixa else (resolvido.rescale if resolvido else None)
    resampling = resolvido.resampling if resolvido else "nearest"
    nodata_transparente = resolvido.nodata_transparente if resolvido else True
    inicio = time.perf_counter()
    try:
        corpo = tiles.ladrilho(fonte, z, x, y, formato=formato, expressao=expressao,
                              bandas=_bandas(bandas), rescale=faixa_final, colormap=colormap,
                              resampling=resampling, nodata_transparente=nodata_transparente)
    except tiles.ForaDaCobertura:
        leitura.contar(auth.tenant_id, auth.token_id, item, 0)
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    except tiles.ErroTile as e:
        leitura.contar(auth.tenant_id, auth.token_id, item, 0, erro=True)
        raise ErroAPI(422, "ladrilho_invalido", str(e)) from e
    except Exception as e:  # falha de leitura do armazenamento: conta como erro do token e sobe 502
        leitura.contar(auth.tenant_id, auth.token_id, item, 0, erro=True)
        raise ErroAPI(502, "leitura_falhou", f"não foi possível ler a imagem: {e}") from e
    if resolvido and resolvido.opacidade < 1.0:
        corpo = pred.aplicar_opacidade(corpo, formato, resolvido.opacidade)
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


def _predef_publicada(auth, item: str, predef: str | None) -> str | None:
    """`predef` explícito do cliente vence; sem ele, se o item tem predefinição CUSTOM marcada padrão
    (`pred.padrao_do_item`), essa é a que fica GRAVADA na URL publicada (TileJSON/WMTS). É o mecanismo
    do portão "trocar a predefinição padrão do item muda a URL WMTS publicada... sem quebrar a
    anterior": o nome fica escrito por extenso na URL, nunca "o padrão de agora" implícito — uma URL já
    publicada com `predef=x` sempre resolve `x` (que só some se for apagada), mesmo depois de outra
    predefinição virar a padrão do item."""
    if predef:
        return predef
    with db.db(auth.contexto_leitura()) as cur:
        achado = pred.padrao_do_item(cur, auth.tenant_id, item)
    return achado[0] if achado else None


@router.get("/svc/{token}/raster/{item}/tilejson.json", openapi_extra=X, summary="TileJSON 3.0.0 do item")
def tilejson(
    request: Request, token: str, item: str,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
    predef: str | None = Query(None, max_length=59, description="nome de predefinição de renderização (L1-02-f)"),
):
    auth = _autorizar(request, token, item)
    predef_pub = _predef_publicada(auth, item, predef)
    asset_final = _asset_padrao(expressao, asset if not predef_pub else (asset or "cientifico"))
    fonte, stac = _fonte_do_item(auth, item, asset_final)
    info = tiles.informacao(fonte)
    consulta = _consulta_render(expressao, bandas, faixa, colormap, asset, predef_pub)
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


@router.get("/svc/{token}/raster/{item}/estatisticas.json", openapi_extra=X,
            summary="mín/máx/média/desvio-padrão e percentis 2-98 por banda (ou por expressão)")
def estatisticas_json(
    request: Request, token: str, item: str,
    bandas: str | None = Query(None, max_length=32, description="bandas a medir, ex.: 3,2,1"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX,
                                  description="mede a expressão (ex.: NDVI) em vez das bandas cruas"),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    """Base do esticamento por percentil/desvio-padrão do editor de estilo (item L2-02-f) e da legenda
    contínua: o editor chama esta rota, escolhe min/máx pelo método pedido e GRAVA os números no
    `plat_construtor.parametros_raster.rescale` — a legenda nunca recalcula por conta própria, só cita
    o que aqui saiu (mesma disciplina de fonte única do resto do módulo de estilo)."""
    auth = _autorizar(request, token, item)
    asset_final = _asset_padrao(expressao, asset)
    fonte, _ = _fonte_do_item(auth, item, asset_final)
    try:
        corpo = tiles.estatisticas(fonte, bandas=_bandas(bandas), expressao=expressao)
    except tiles.ErroTile as e:
        raise ErroAPI(422, "estatistica_invalida", str(e)) from e
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate",
                                        "Access-Control-Allow-Origin": CORS})


# ---------------------------------------------------------------------------- WMTS
_PREDEF_Q = Query(None, max_length=59, pattern="^[a-z0-9][a-z0-9-]{0,58}$",
                  description="nome de predefinição de renderização (item L1-02-f)")


def _capabilities(token: str, item: str, auth, expressao, bandas, faixa, colormap, asset, predef=None) -> str:
    predef_pub = _predef_publicada(auth, item, predef)
    asset_final = _asset_padrao(expressao, asset if not predef_pub else (asset or "cientifico"))
    fonte, stac = _fonte_do_item(auth, item, asset_final)
    info = tiles.informacao(fonte)
    titulo = (stac.get("properties") or {}).get("title") or item
    return wmts_doc.capabilities(
        base=_base(token, item),
        identificador=item,
        titulo=titulo,
        bounds=info["bounds"],
        # o zoom mínimo é o da IMAGEM, não zero: declarar 0 faz o cliente pedir o ladrilho do mundo
        # inteiro ao criar a camada, e ler o COG para um ladrilho em que a imagem não chega a um pixel
        # custou 93 s MEDIDOS nesta máquina — acima do teto de 60 s do nginx, que devolve 504 e faz o
        # ArcGIS Pro recusar a camada com "Invalid Path". O TileJSON já anunciava o mínimo certo.
        zoom_min=info["minzoom"],
        zoom_max=max(info["maxzoom"], 18),
        formatos=["image/png", "image/jpeg", "image/webp"],
        consulta=_consulta_render(expressao, bandas, faixa, colormap, asset, predef_pub),
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
    predef: str | None = _PREDEF_Q,
):
    auth = _autorizar(request, token, item)
    xml = _capabilities(token, item, auth, expressao, bandas, faixa, colormap, asset, predef)
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
    predef: str | None = _PREDEF_Q,
):
    auth = _autorizar(request, token, item)
    if (service or "").upper() != "WMTS":
        raise ErroAPI(422, "servico_invalido", "SERVICE tem de ser WMTS", {"SERVICE": service})
    # STYLE (WMTS) é o mesmo mecanismo de predefinição — mesma convenção do STYLES do WMS
    # (app/imagens/rotas_wms.py): um cliente WMTS "de verdade" nomeia o estilo por `STYLE=`, não por um
    # parâmetro inventado; `predef=` continua aceito para quem já usa a URL do XYZ/TileJSON.
    predef_efetivo = predef or (style if style and style != "default" else None)
    operacao = (request_ or "").lower()
    if operacao == "getcapabilities":
        xml = _capabilities(token, item, auth, expressao, bandas, faixa, colormap, asset, predef_efetivo)
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
                   expressao, bandas, faixa, colormap, asset, predef=predef_efetivo)


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
    predef: str | None = _PREDEF_Q,
):
    if ext not in tiles.FORMATOS:
        raise ErroAPI(404, "formato_desconhecido", f"formato de ladrilho desconhecido: {ext}",
                      {"aceitos": sorted(tiles.FORMATOS)})
    auth = _autorizar(request, token, item)
    return _servir(request, auth, item, z, x, y, ext, expressao, bandas, faixa, colormap, asset, predef=predef)


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
    predef: str | None = _PREDEF_Q,
):
    auth = _autorizar(request, token, item)
    return _servir(request, auth, item, z, x, y, formato, expressao, bandas, faixa, colormap, asset, predef=predef)


# ---------------------------------------------------------------------------- predefinições de renderização (L1-02-f)
@router.get("/svc/{token}/raster/{item}/predefinicoes.json", openapi_extra=X,
            summary="predefinições de renderização disponíveis para o item (fábrica + custom do inquilino)")
def predefinicoes_do_item(request: Request, token: str, item: str):
    auth = _autorizar(request, token, item)
    custom: list[dict] = []
    if pred._e_uuid(item):  # noqa: SLF001 — item de fixture antiga (não-uuid) nunca tem predefinição custom
        with db.db(auth.contexto_leitura()) as cur:
            cur.execute(
                "SELECT nome, titulo, versao, padrao FROM plat.render_predefinicao "
                "WHERE tenant_id = %s AND item_id = %s::uuid AND apagado_em IS NULL ORDER BY nome",
                (auth.tenant_id, item),
            )
            custom = [dict(r) for r in cur.fetchall()]
    corpo = {"item": item, "fabrica": pred.listar_fabrica(), "custom": custom}
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/raster/{item}/legenda.json", openapi_extra=X,
            summary="legenda (estrutura) da predefinição pedida ou padrão do item")
def legenda_json_svc(request: Request, token: str, item: str, predef: str | None = _PREDEF_Q,
                     asset: str | None = Query(None, pattern="^(visual|cientifico)$")):
    auth = _autorizar(request, token, item)
    nome = _predef_publicada(auth, item, predef)
    if not nome:
        raise ErroAPI(422, "predefinicao_ausente",
                      "informe predef= ou marque uma predefinição padrão para o item", {"item": item})
    resolvido, _ = _resolver_predef(auth, item, nome, None, None, None, asset)
    return JSONResponse(pred.legenda_json(resolvido), headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/raster/{item}/legenda.png", openapi_extra=X,
            summary="legenda (imagem) da predefinição pedida ou padrão do item")
def legenda_png_svc(request: Request, token: str, item: str, predef: str | None = _PREDEF_Q,
                    asset: str | None = Query(None, pattern="^(visual|cientifico)$")):
    auth = _autorizar(request, token, item)
    nome = _predef_publicada(auth, item, predef)
    if not nome:
        raise ErroAPI(422, "predefinicao_ausente",
                      "informe predef= ou marque uma predefinição padrão para o item", {"item": item})
    resolvido, _ = _resolver_predef(auth, item, nome, None, None, None, asset)
    corpo = pred.legenda_png(resolvido)
    return Response(corpo, media_type="image/png", headers={"Cache-Control": "no-store, must-revalidate"})


# ---------------------------------------------------------------------------- mosaico (ad-hoc OU busca registrada)
def _validar_tile(z: int, x: int, y: int) -> None:
    """Achado do adversário independente do item L1-07 (10/09): `z` negativo ou muito grande (ex. -1,
    10000) fazia `morecantile` calcular `matrixWidth` com overflow e levantar `OverflowError` CRU (500)
    dentro de `_bbox_do_tile` — nunca chegava a `ErroAPI`. `z/x/y` são sempre da grade WebMercatorQuad
    (`tiles.TMS`, decisão C4 do L1-02): fora da faixa válida é pedido malformado, 422, nunca 500."""
    if not (tiles.TMS.minzoom <= z <= tiles.TMS.maxzoom):
        raise ErroAPI(422, "tile_invalido", f"z fora da faixa {tiles.TMS.minzoom}-{tiles.TMS.maxzoom}",
                      {"z": z})
    teto = 2**z
    if not (0 <= x < teto) or not (0 <= y < teto):
        raise ErroAPI(422, "tile_invalido", f"x/y fora da grade do zoom {z} (0 a {teto - 1})",
                      {"z": z, "x": x, "y": y, "teto": teto - 1})


def _bbox_do_tile(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    _validar_tile(z, x, y)
    return tiles.TMS.bounds(tiles.TMS.tile(0, 0, 0).__class__(x=x, y=y, z=z))


def _servir_composto(request: Request, auth, feicoes: list[dict], z: int, x: int, y: int, formato: str,
                     expressao, bandas, faixa, colormap, asset, metodo: str | None = None) -> Response:
    """COMPÕE o ladrilho de todas as cenas candidatas num só (`tiles.ladrilho_composto`, item L1-07):
    a ordem já vem do `sortby` registrado/pedido ("mais recente" por padrão); `metodo` escolhe a REGRA
    de seleção de pixel (padrão `primeira` — a primeira cena COM DADO vence, PIXEL A PIXEL, não cena a
    cena: é isto que faz a junta entre duas cenas mostrar as duas, em vez de uma cena inteira com o
    resto em branco). A seleção vem dos critérios persistidos quando não há override `metodo`.
    Candidata cujo item não resolve fonte (excluído/de outro estado) é ignorada, não derruba o tile."""
    if not feicoes:
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    asset_final = _asset_padrao(expressao, asset)
    fontes = []
    for f in feicoes:
        try:
            fonte, _ = _fonte_do_item(auth, f["id"], asset_final)
            fontes.append(fonte)
        except ErroAPI:
            continue
    if not fontes:
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    inicio = time.perf_counter()
    try:
        corpo = tiles.ladrilho_composto(fontes, z, x, y, formato=formato, expressao=expressao,
                                        bandas=_bandas(bandas), rescale=_faixa(faixa), colormap=colormap,
                                        metodo=metodo)
    except tiles.ForaDaCobertura:
        return Response(status_code=204, headers={"Cache-Control": CACHE_TILE})
    except tiles.ErroTile as e:
        raise ErroAPI(422, "ladrilho_invalido", str(e)) from e
    except Exception as e:  # falha de leitura do armazenamento: nunca 500 cru
        raise ErroAPI(502, "leitura_falhou", f"não foi possível ler a imagem: {e}") from e
    ms = (time.perf_counter() - inicio) * 1000
    return Response(
        content=corpo, media_type=tiles.FORMATOS[formato],
        headers={"Cache-Control": CACHE_TILE, "Server-Timing": f"ladrilho;dur={ms:.1f}",
                "X-Plat-Cenas-Candidatas": str(len(fontes))},
    )


def _tile_mosaico_impl(
    request: Request, token: str, alvo: str, z: int, x: int, y: int, formato: str,
    expressao, bandas, faixa, colormap, asset, limite: int | None, metodo: str | None = None,
) -> Response:
    """`alvo` é um uuid de mosaico REGISTRADO (item L1-07: `POST /svc/<token>/stac/mosaicos`, busca com
    várias coleções/bbox/datetime/filtro CQL2/ordenação) OU o nome completo de uma coleção
    (`<tenant_id>-<slug>`, comportamento ad-hoc anterior a este item: a coleção INTEIRA, sem registro,
    sempre ordenada por data desc) — ver ADR 20260910T2330 §4. As duas formas nunca colidem porque um
    nome de coleção nunca é um uuid sintaticamente válido. `metodo` = regra de seleção de pixel do
    item L1-08 (mínimo), ver `tiles.METODOS_COMPOSICAO`."""
    if mo.eh_uuid(alvo):
        auth = _autorizar(request, token, alvo)  # escopo FINO: tiles:ler:<uuid-do-mosaico>
        with db.db(auth.contexto_leitura()) as cur:
            linha = mo.obter(cur, auth.tenant_id, alvo)
            if linha is None:
                raise ErroAPI(403, "mosaico_indisponivel", "mosaico inexistente ou de outro inquilino",
                              {"mosaico": alvo})
            feicoes = mo.candidatas_para_tile(cur, linha, _bbox_do_tile(z, x, y),
                                              limite or linha["criterios"].get("limite") or mo.LIMITE_TILE_PADRAO)
        return _servir_composto(request, auth, feicoes, z, x, y, formato, expressao, bandas, faixa,
                                  colormap, asset, metodo or linha["criterios"].get("pixel_selection", "first"))

    colecao = alvo
    auth = _autorizar(request, token)
    if not ps.colecao_pertence(colecao, auth.tenant_id):
        raise ErroAPI(403, "colecao_indisponivel", "coleção inexistente ou de outro inquilino",
                      {"colecao": colecao})
    oeste, sul, leste, norte = _bbox_do_tile(z, x, y)
    with db.db(auth.contexto_leitura()) as cur:
        busca = ps.buscar(cur, {"collections": [colecao], "bbox": [oeste, sul, leste, norte],
                                "limit": limite or 6, "sortby": [{"field": "datetime", "direction": "desc"}]})
    return _servir_composto(request, auth, busca.get("features") or [], z, x, y, formato, expressao,
                              bandas, faixa, colormap, asset, metodo)


# As DUAS rotas de ladrilho (`.{ext}` e sem extensão) são registradas DEPOIS das rotas literais
# (tilejson.json/wmts/pegadas, abaixo) DE PROPÓSITO: `/mosaico/{alvo}/{z}/{x}/{y}.{ext}` e
# `/mosaico/{mosaico_id}/wmts/1.0.0/WMTSCapabilities.xml` têm a MESMA forma de caminho (4 segmentos
# depois de `/mosaico/`, o último com um ponto literal — "WMTSCapabilities.xml" bate no padrão
# `{y}.{ext}`) — o FastAPI casa pela FORMA do caminho, na ordem de registro, e só then tenta converter
# os tipos; se a rota de ladrilho viesse primeiro, `wmts/1.0.0/WMTSCapabilities.xml` cairia nela com
# z="wmts" (não converte para int) e devolvia 422 em vez de cair na rota certa (defeito real medido
# nesta bancada, corrigido por esta ordem — ver docstring do módulo em rotas_tiles.py topo)
# ---------------------------------------------------------------------------- TileJSON/WMTS/pegadas do mosaico
def _mosaico_autorizado(request: Request, token: str, mosaico_id: str):
    """(auth, linha) do mosaico — 403 tanto para uuid inválido/inexistente quanto para outro inquilino
    (mesma regra do resto do módulo: 404 nunca, confirmaria a existência alheia)."""
    auth = _autorizar(request, token, mosaico_id)
    with db.db(auth.contexto_leitura()) as cur:
        linha = mo.obter(cur, auth.tenant_id, mosaico_id)
        if linha is None:
            raise ErroAPI(403, "mosaico_indisponivel", "mosaico inexistente ou de outro inquilino",
                          {"mosaico": mosaico_id})
    return auth, linha


def _extent_do_mosaico(cur, linha: dict) -> list[float]:
    """bbox 4326 que envolve TODAS as pegadas do mosaico — usado pelo TileJSON/WMTS. Custa uma busca
    (a mesma de `pegadas()`, capada em LIMITE_PEGADAS); para os tamanhos deste item (dezenas de cenas)
    é barato. Sem nenhuma feição, cai no bbox registrado ou no mundo inteiro."""
    fc = mo.pegadas(cur, linha)
    boxes = [f["bbox"] for f in fc["features"] if f.get("bbox")]
    if not boxes:
        bbox_reg = linha["criterios"].get("bbox")
        return list(bbox_reg) if bbox_reg else [-180.0, -90.0, 180.0, 90.0]
    oeste = min(b[0] for b in boxes)
    sul = min(b[1] for b in boxes)
    leste = max(b[2] for b in boxes)
    norte = max(b[3] for b in boxes)
    return [oeste, sul, leste, norte]


def _base_mosaico(token: str, mosaico_id: str) -> str:
    return f"{settings.PLAT_URL_PUBLICA.rstrip('/')}/svc/{token}/mosaico/{mosaico_id}"


@router.get("/svc/{token}/mosaico/{mosaico_id}/tilejson.json", openapi_extra=X,
            summary="TileJSON 3.0.0 do mosaico registrado (item L1-07)")
def mosaico_tilejson(
    request: Request, token: str, mosaico_id: str,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
):
    auth, linha = _mosaico_autorizado(request, token, mosaico_id)
    with db.db(auth.contexto_leitura()) as cur:
        bounds = _extent_do_mosaico(cur, linha)
    consulta = _consulta_render(expressao, bandas, faixa, colormap, asset)
    ext = "jpg" if formato in ("jpg", "jpeg") else formato
    url = f"{_base_mosaico(token, mosaico_id)}/{{z}}/{{x}}/{{y}}.{ext}"
    if consulta:
        url += f"?{consulta}"
    corpo = {
        "tilejson": "3.0.0",
        "name": linha["nome"],
        "tiles": [url],
        "minzoom": 0,
        "maxzoom": 22,
        "bounds": bounds,
        "center": [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2, 10],
        "scheme": "xyz",
    }
    return JSONResponse(corpo, headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/mosaico/{mosaico_id}/wmts/1.0.0/WMTSCapabilities.xml", openapi_extra=X,
            summary="WMTS 1.0.0 GetCapabilities do mosaico registrado (forma REST)")
def mosaico_wmts_rest(request: Request, token: str, mosaico_id: str):
    auth, linha = _mosaico_autorizado(request, token, mosaico_id)
    with db.db(auth.contexto_leitura()) as cur:
        bounds = _extent_do_mosaico(cur, linha)
    xml = wmts_doc.capabilities(
        base=_base_mosaico(token, mosaico_id), identificador=mosaico_id, titulo=linha["nome"],
        bounds=bounds, zoom_min=0, zoom_max=20, formatos=["image/png", "image/jpeg", "image/webp"],
        consulta="", resumo=f"mosaico de {len(linha['colecoes'])} coleção(ões); grade WebMercatorQuad.",
    )
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/mosaico/{mosaico_id}/wmts", openapi_extra=X,
            summary="WMTS 1.0.0 KVP do mosaico registrado (GetCapabilities e GetTile)")
def mosaico_wmts_kvp(
    request: Request, token: str, mosaico_id: str,
    service: str = Query("WMTS", alias="SERVICE"), request_: str = Query("GetCapabilities", alias="REQUEST"),
    tilematrix: str | None = Query(None, alias="TILEMATRIX"), tilerow: int | None = Query(None, alias="TILEROW"),
    tilecol: int | None = Query(None, alias="TILECOL"), format_: str | None = Query(None, alias="FORMAT"),
):
    if (service or "").upper() != "WMTS":
        raise ErroAPI(422, "servico_invalido", "SERVICE tem de ser WMTS", {"SERVICE": service})
    operacao = (request_ or "").lower()
    if operacao == "getcapabilities":
        return mosaico_wmts_rest(request, token, mosaico_id)
    if operacao != "gettile":
        raise ErroAPI(422, "operacao_invalida", "REQUEST tem de ser GetCapabilities ou GetTile",
                      {"REQUEST": request_})
    if tilematrix is None or tilerow is None or tilecol is None:
        raise ErroAPI(422, "parametro_ausente", "GetTile exige TILEMATRIX, TILEROW e TILECOL")
    formato = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(
        (format_ or "image/png").lower())
    if formato is None:
        raise ErroAPI(422, "formato_desconhecido", "FORMAT aceito: image/png, image/jpeg, image/webp",
                      {"FORMAT": format_})
    try:
        z = int(str(tilematrix).split(":")[-1])
    except ValueError as e:
        raise ErroAPI(422, "tile_invalido", "TILEMATRIX deve indicar um zoom inteiro") from e
    return _tile_mosaico_impl(request, token, mosaico_id, z, tilecol, tilerow, formato,
                             None, None, None, None, None, None)


@router.get("/svc/{token}/mosaico/{mosaico_id}/pegadas", openapi_extra=X,
            summary="pegadas (footprints) do mosaico registrado, em GeoJSON — item L1-07")
def mosaico_pegadas(request: Request, token: str, mosaico_id: str):
    auth, linha = _mosaico_autorizado(request, token, mosaico_id)
    with db.db(auth.contexto_leitura()) as cur:
        fc = mo.pegadas(cur, linha)
    return JSONResponse(fc, media_type="application/geo+json",
                        headers={"Cache-Control": "no-store, must-revalidate"})


@router.get("/svc/{token}/mosaico/{alvo}/{z}/{x}/{y}.{ext}", openapi_extra=X,
            summary="ladrilho do mosaico com extensão no caminho (uuid de busca registrada ou coleção)")
def tile_mosaico_ext(
    request: Request, token: str, alvo: str, z: int, x: int, y: int, ext: str,
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
    limite: int | None = Query(None, ge=1, le=mo.LIMITE_TILE_MAX),
    metodo: str | None = Query(None, description="override da seleção persistida: "
                               "first|last|lowest|highest|mean|median|stdev (aceita aliases em português)"),
):
    if ext not in tiles.FORMATOS:
        raise ErroAPI(404, "formato_desconhecido", f"formato de ladrilho desconhecido: {ext}",
                      {"aceitos": sorted(tiles.FORMATOS)})
    return _tile_mosaico_impl(request, token, alvo, z, x, y, ext, expressao, bandas, faixa, colormap,
                              asset, limite, metodo)


@router.get("/svc/{token}/mosaico/{alvo}/{z}/{x}/{y}", openapi_extra=X,
            summary="ladrilho do mosaico (uuid de busca registrada — L1-07 — ou nome de coleção)")
def tile_mosaico(
    request: Request, token: str, alvo: str, z: int, x: int, y: int,
    formato: str = Query(FORMATO_PADRAO, pattern="^(png|jpg|jpeg|webp)$"),
    expressao: str | None = Query(None, max_length=tiles.EXPRESSAO_MAX),
    bandas: str | None = Query(None, max_length=32),
    faixa: str | None = Query(None, max_length=64),
    colormap: str | None = Query(None, max_length=40),
    asset: str | None = Query(None, pattern="^(visual|cientifico)$"),
    limite: int | None = Query(None, ge=1, le=mo.LIMITE_TILE_MAX,
                               description="máximo de cenas candidatas por ladrilho"),
    metodo: str | None = Query(None, description="override da seleção persistida: "
                               "first|last|lowest|highest|mean|median|stdev (aceita aliases em português)"),
):
    return _tile_mosaico_impl(request, token, alvo, z, x, y, formato, expressao, bandas, faixa,
                              colormap, asset, limite, metodo)


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
            if mo.eh_uuid(item):
                with db.db(auth.contexto_leitura()) as cur:
                    if mo.obter(cur, auth.tenant_id, item) is None:
                        raise ErroAPI(403, "mosaico_indisponivel", "mosaico inexistente ou de outro inquilino",
                                      {"mosaico": item})
            elif not ps.colecao_pertence(item, auth.tenant_id):
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
