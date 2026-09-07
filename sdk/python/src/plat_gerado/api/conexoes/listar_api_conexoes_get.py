from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.conexao_pagina import ConexaoPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    tipo: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tipo: None | str | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ConexaoPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ConexaoPagina.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ConexaoPagina | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
) -> Response[ConexaoPagina | HTTPValidationError]:
    """Listar

    Args:
        tipo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConexaoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
) -> ConexaoPagina | HTTPValidationError | None:
    """Listar

    Args:
        tipo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConexaoPagina | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        tipo=tipo,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
) -> Response[ConexaoPagina | HTTPValidationError]:
    """Listar

    Args:
        tipo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ConexaoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
) -> ConexaoPagina | HTTPValidationError | None:
    """Listar

    Args:
        tipo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ConexaoPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            tipo=tipo,
        )
    ).parsed
