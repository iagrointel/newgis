"""Autorização por token de serviço para o servidor de tiles vetoriais (item
L2-04-e-vector-tile-server-tilejson).

Reusa o MESMO desenho já provado do ladrilho raster por token (item L1-02-tiles-token,
`wt/tilestok`, ADR 20260907T0300): o token vem no CAMINHO da URL (nunca em cookie, nunca em
parâmetro que expira), e a autorização é feita com o MESMO código que o FeatureServer usa
(`app.auth.sessao._auth_de_token` + `app.auth.escopos.exigir_escopo`, escopo `camada:ler`,
opcionalmente escopado ao item — `camada:ler:<uuid>`).

Cache em processo de 2 s por (token, item, referer, origin, ip): o nginx da frente (ver
`deploy/nginx.conf`, bloco `/_plat_tile_vetor_autorizar`) faz o mesmo `auth_request` ANTES do
`proxy_cache` do ladrilho, com outro cache de 2 s — os dois em série dão um pior caso de 4 s entre
revogar um token e ele parar de autenticar, dentro do teto de 5 s que a casa já aceitou para o
ladrilho raster. Diferente do raster, aqui a recusa é 401/403 (não sempre 403): o cliente MapLibre/
QGIS pode legitimamente pedir sem qualquer credencial (token ausente = 401, forma clássica), mas
uma vez que HÁ um token, todo motivo (revogado, expirado, escopo insuficiente, IP/Referer fora da
restrição) é o mesmo `ErroAPI` que `_auth_de_token`/`exigir_escopo` já levantam — nada reinventado
aqui além do cache."""

from __future__ import annotations

import time

from fastapi import Request

from app.auth import escopos as esc
from app.auth import sessao as auth_sessao
from app.auth.sessao import Auth
from app.erros import ErroAPI

ESCOPO = "camada:ler"
TTL_S = 2.0
CACHE_MAX = 5000

_CACHE: dict[str, tuple[float, Auth | ErroAPI]] = {}


def _agora() -> float:
    return time.monotonic()


def _chave(request: Request, token: str, item_id: str) -> str:
    ip = request.client.host if request.client else ""
    return f"{token}|{item_id}|{request.headers.get('referer', '')}|{request.headers.get('origin', '')}|{ip}"


def _guardar(chave: str, valor: Auth | ErroAPI) -> None:
    if len(_CACHE) >= CACHE_MAX:
        _CACHE.clear()
    _CACHE[chave] = (_agora(), valor)


def autorizar(request: Request, token: str, item_id: str) -> Auth:
    """Devolve o `Auth` do token, ou levanta `ErroAPI` (401 sem token/token inválido/revogado/
    expirado/restrição, 403 escopo insuficiente). Item vem SEMPRE da URL do servidor, nunca de um
    parâmetro que o cliente possa trocar por outro item de outro inquilino (mesmo cuidado do
    achado do adversário em L2-01-b/`app/tiles/rotas.py::_tabela_da_url`)."""
    if not token:
        raise ErroAPI(401, "token_ausente", "informe o token de serviço no caminho da URL")
    chave = _chave(request, token, item_id)
    guardado = _CACHE.get(chave)
    if guardado and (_agora() - guardado[0]) < TTL_S:
        valor = guardado[1]
        if isinstance(valor, ErroAPI):
            raise valor
        return valor
    try:
        auth = auth_sessao._auth_de_token(request, token)  # noqa: SLF001 — mesmo reuso do FeatureServer/GeocodeServer
        esc.exigir_escopo(auth, ESCOPO, item_id)
    except ErroAPI as e:
        _guardar(chave, e)
        raise
    _guardar(chave, auth)
    return auth


def esquecer() -> None:
    """Usada pelo teste de revogação (mede o pior caso do cache) e pelo desligamento."""
    _CACHE.clear()
