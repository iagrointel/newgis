"""Proxy WMS público para a casca do SIG (`/sig`, item L2-01-a-casca-sig, 10/09/2026): `GET /api/publico/
wms/{fonte}` repassa GetMap/GetCapabilities para uma allowlist FIXA de serviços WMS oficiais (GeoSampa,
IBGE, INDE — `app.settings.WMS_PUBLICO_ALLOWLIST`), sem exigir sessão. Por quê: o navegador não pode falar
direto com esses domínios (CORS fechado nos três, e eles não conhecem o cookie do plat); o proxy também
evita vazar a URL de origem para quem inspeciona a rede — só o nome curto da fonte aparece.

Rota deliberadamente ESTREITA: só `REQUEST=GetMap` ou `GetCapabilities` passa (os dois únicos que um mapa
de leitura precisa); qualquer outro valor — inclusive algo que pareça escrita — é 422 antes de qualquer
requisição sair daqui. Fonte fora da allowlist é 404 (nunca 403: não há segredo nenhum em "essa fonte não
existe"). Timeout curto (20 s): uma base pública lenta não pode travar o mapa de quem a esperar.

Este arquivo é NOVO e não toca `app/mapa/rotas.py` (outra frente está editando aquele arquivo agora — ver
app/main.py para o registro do router)."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.erros import ErroAPI
from app.settings import WMS_PUBLICO_ALLOWLIST

log = logging.getLogger("plat.mapa.wms_publico")
router = APIRouter(tags=["mapa"])
X_PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}

REQUESTS_PERMITIDOS = {"GETMAP", "GETCAPABILITIES"}
TIMEOUT_S = 20.0


@router.get("/api/publico/wms/{fonte}", include_in_schema=True, openapi_extra=X_PUBLICO)
async def wms_publico(fonte: str, request: Request):
    base = WMS_PUBLICO_ALLOWLIST.get(fonte)
    if base is None:
        raise ErroAPI(404, "fonte_inexistente", "fonte WMS pública desconhecida")
    parametros = dict(request.query_params)
    pedido = next((v for k, v in parametros.items() if k.upper() == "REQUEST"), None)
    if not pedido or pedido.upper() not in REQUESTS_PERMITIDOS:
        raise ErroAPI(422, "request_nao_permitido", "só REQUEST=GetMap ou GetCapabilities é repassado")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            r = await cliente.get(base, params=parametros)
    except httpx.HTTPError as e:
        log.warning("wms_publico: %s (%s) inacessível: %s", fonte, base, e)
        raise ErroAPI(502, "wms_indisponivel", "o serviço WMS externo não respondeu") from e
    tipo = r.headers.get("content-type", "application/octet-stream")
    # cache curto no próprio processo (o nginx da instalação real cacheia 10 min por cima, ADR do item);
    # sem isto um GetMap de erro (ex.: 400 do GeoServer de origem) ficaria com Cache-Control ausente.
    return Response(content=r.content, status_code=r.status_code, media_type=tipo,
                     headers={"Cache-Control": "public, max-age=600"})
