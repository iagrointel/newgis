from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/campo/sessao",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 201:
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
    """Campo Sessao

     Token de campo (L0-02-d): sempre escopo `campo:usar`, sempre `CAMPO_TOKEN_DIAS` dias, sem escolha —
    é a única forma de emitir esse escopo (a rota genérica `/api/tokens` também aceitaria, mas o PWA
    sempre
    chama esta para não expor o formulário completo de tokens a quem só quer entrar em campo). Revogável
    como
    qualquer token de serviço, por `DELETE /api/tokens/{id}` (mesma tabela, sem rota própria de
    revogar).

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
    """Campo Sessao

     Token de campo (L0-02-d): sempre escopo `campo:usar`, sempre `CAMPO_TOKEN_DIAS` dias, sem escolha —
    é a única forma de emitir esse escopo (a rota genérica `/api/tokens` também aceitaria, mas o PWA
    sempre
    chama esta para não expor o formulário completo de tokens a quem só quer entrar em campo). Revogável
    como
    qualquer token de serviço, por `DELETE /api/tokens/{id}` (mesma tabela, sem rota própria de
    revogar).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
