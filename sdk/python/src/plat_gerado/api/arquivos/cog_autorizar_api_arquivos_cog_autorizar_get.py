from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/arquivos/_cog/autorizar",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 204:
        return None

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Cog Autorizar

     Subrequisição `auth_request` do bloco `/svc/<token>/cog/<slug>/...` do nginx (deploy/nginx.conf).
    Recebe o
    caminho original em `X-Original-URI` e responde 204 (o nginx serve a fatia do Garage) ou 403 (não
    serve).
    Autoriza quando: o caminho está na forma esperada, o token existe, não está revogado nem expirado, e
    o
    inquilino do token é o dono do `<slug>` do caminho. Nunca diz QUAL das condições falhou — a resposta
    é a
    mesma 403 para token inexistente e para token de outro inquilino, senão a rota vira oráculo de
    token.
    É rota pública de propósito: a subrequisição do nginx não carrega cookie nem `Authorization`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Cog Autorizar

     Subrequisição `auth_request` do bloco `/svc/<token>/cog/<slug>/...` do nginx (deploy/nginx.conf).
    Recebe o
    caminho original em `X-Original-URI` e responde 204 (o nginx serve a fatia do Garage) ou 403 (não
    serve).
    Autoriza quando: o caminho está na forma esperada, o token existe, não está revogado nem expirado, e
    o
    inquilino do token é o dono do `<slug>` do caminho. Nunca diz QUAL das condições falhou — a resposta
    é a
    mesma 403 para token inexistente e para token de outro inquilino, senão a rota vira oráculo de
    token.
    É rota pública de propósito: a subrequisição do nginx não carrega cookie nem `Authorization`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
