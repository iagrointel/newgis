"""Entrega direta de COG por HTTPS, autenticada pelo token de serviço no caminho.

O objeto nunca é materializado inteiro: tanto a resposta completa quanto a parcial são
produzidas em blocos usando a leitura por intervalo já oferecida por ``app.objetos``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import db, limites, objetos
from app.auth import escopos as esc
from app.erros import ErroAPI
from app.imagens import pgstac as ps
from app.imagens.rotas_tiles import _autorizar, _chave_do_asset

router = APIRouter(tags=["imagens"])

_TIPO_COG = "image/tiff; application=geotiff; profile=cloud-optimized"
_BLOCO_STREAM_BYTES = 1024 * 1024
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _recusar_faixa(tamanho: int, mensagem: str) -> None:
    raise ErroAPI(
        416,
        "faixa_invalida",
        mensagem,
        headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{tamanho}"},
    )


def _interpretar_faixa(cabecalho: str, tamanho: int) -> tuple[int, int]:
    """Converte um único byte-range em limites inclusivos; múltiplas faixas não são aceitas."""
    encontrado = _RANGE.fullmatch(cabecalho.strip())
    if encontrado is None or tamanho <= 0:
        _recusar_faixa(tamanho, "o cabeçalho Range deve conter uma única faixa de bytes")
    primeiro, ultimo = encontrado.groups()
    if not primeiro and not ultimo:
        _recusar_faixa(tamanho, "a faixa de bytes está vazia")
    if not primeiro:
        sufixo = int(ultimo)
        if sufixo <= 0:
            _recusar_faixa(tamanho, "o sufixo da faixa deve ser maior que zero")
        inicio, fim = max(0, tamanho - sufixo), tamanho - 1
    else:
        inicio = int(primeiro)
        if inicio >= tamanho:
            _recusar_faixa(tamanho, "o início da faixa está além do fim do objeto")
        fim = min(int(ultimo), tamanho - 1) if ultimo else tamanho - 1
        if fim < inicio:
            _recusar_faixa(tamanho, "o fim da faixa é anterior ao início")
    if fim - inicio + 1 > limites.COG_FAIXA_MAX_BYTES:
        _recusar_faixa(tamanho, "a faixa solicitada excede o teto permitido")
    return inicio, fim


def _blocos(chave: str, inicio: int, fim: int, tenant_slug: str) -> Iterator[bytes]:
    posicao = inicio
    while posicao <= fim:
        ultimo = min(fim, posicao + _BLOCO_STREAM_BYTES - 1)
        dados = objetos.ler_intervalo(chave, posicao, ultimo, tenant_slug_esperado=tenant_slug)
        if not dados:
            raise RuntimeError("o armazenamento encerrou o objeto antes do tamanho informado")
        yield dados
        posicao += len(dados)


def _resolver_asset(auth, item: str, asset: str) -> str:
    if asset not in ("visual", "cientifico"):
        raise ErroAPI(404, "asset_inexistente", f"o item não tem o asset '{asset}'")
    with db.db(auth.contexto_leitura()) as cur:
        cur.execute(
            "SELECT colecao, estado FROM plat.raster_item "
            "WHERE tenant_id = %s AND item_id = %s LIMIT 1",
            (auth.tenant_id, item),
        )
        linha = cur.fetchone()
        if linha is None or linha["estado"] != "ativo":
            raise ErroAPI(
                403,
                "item_indisponivel",
                "item de imagem inexistente, excluído ou de outro inquilino",
                {"item": item},
            )
        item_stac = ps.item_obter(cur, auth.tenant_id, linha["colecao"], item)
    if item_stac is None:
        raise ErroAPI(403, "item_indisponivel", "item de imagem sem registro STAC", {"item": item})
    return _chave_do_asset(item_stac, asset)


@router.get(
    "/svc/{token}/cog/{item}/{asset}.tif",
    responses={200: {"content": {_TIPO_COG: {}}}, 206: {"content": {_TIPO_COG: {}}}},
    openapi_extra={"x-auth": "T", "x-privilegio": "proprio"},
)
def servir_cog(request: Request, token: str, item: str, asset: str):
    auth = _autorizar(request, token, item)
    if not esc.cobre(auth.escopos, "imagens:ler"):
        raise ErroAPI(
            403,
            "escopo_insuficiente",
            "o token não tem o escopo imagens:ler",
            {"exigido": "imagens:ler", "token_tem": list(auth.escopos)},
        )
    chave = _resolver_asset(auth, item, asset)
    try:
        tamanho = objetos.tamanho(chave, tenant_slug_esperado=auth.tenant_slug)
    except FileNotFoundError as exc:
        raise ErroAPI(404, "asset_inexistente", "o objeto do asset não existe no armazenamento") from exc
    except objetos.ChaveDeOutroInquilino as exc:
        # defesa em profundidade (achado ADVL1): o href do item aponta para o balde de OUTRO inquilino —
        # nunca 404 (confirmaria que o objeto existe em algum lugar), sempre 403, igual a `item_indisponivel`.
        raise ErroAPI(403, "item_indisponivel", "item de imagem inexistente, excluído ou de outro inquilino",
                      {"item": item}) from exc

    inicio, fim, status = 0, tamanho - 1, 200
    range_pedido = request.headers.get("range")
    if range_pedido is not None:
        inicio, fim = _interpretar_faixa(range_pedido, tamanho)
        status = 206

    etag_match = objetos.CHAVE.fullmatch(chave)
    etag = f'"{etag_match.group("sha256")}"' if etag_match else f'"{tamanho:x}"'
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(fim - inicio + 1),
        "ETag": etag,
        "X-Robots-Tag": "noindex, nofollow",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {inicio}-{fim}/{tamanho}"
    return StreamingResponse(
        _blocos(chave, inicio, fim, auth.tenant_slug), status_code=status, media_type=_TIPO_COG, headers=headers
    )
