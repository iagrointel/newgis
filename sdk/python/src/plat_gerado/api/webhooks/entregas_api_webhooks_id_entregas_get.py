from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.entrega_pagina import EntregaPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    estado: None | str | Unset = UNSET,
    limite: int | Unset = 20,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_estado: None | str | Unset
    if isinstance(estado, Unset):
        json_estado = UNSET
    else:
        json_estado = estado
    params["estado"] = json_estado

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/webhooks/{id}/entregas".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EntregaPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EntregaPagina.from_dict(response.json())

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
) -> Response[EntregaPagina | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    limite: int | Unset = 20,
) -> Response[EntregaPagina | HTTPValidationError]:
    """Entregas

     Log de entregas do webhook (RLS do inquilino; `plat.webhook_entrega` é SELECT/UPDATE a plat_app,
    INSERT só pelo gatilho de despacho).

    Args:
        id (str):
        estado (None | str | Unset):
        limite (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EntregaPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        estado=estado,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    limite: int | Unset = 20,
) -> EntregaPagina | HTTPValidationError | None:
    """Entregas

     Log de entregas do webhook (RLS do inquilino; `plat.webhook_entrega` é SELECT/UPDATE a plat_app,
    INSERT só pelo gatilho de despacho).

    Args:
        id (str):
        estado (None | str | Unset):
        limite (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EntregaPagina | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        estado=estado,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    limite: int | Unset = 20,
) -> Response[EntregaPagina | HTTPValidationError]:
    """Entregas

     Log de entregas do webhook (RLS do inquilino; `plat.webhook_entrega` é SELECT/UPDATE a plat_app,
    INSERT só pelo gatilho de despacho).

    Args:
        id (str):
        estado (None | str | Unset):
        limite (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EntregaPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        estado=estado,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    limite: int | Unset = 20,
) -> EntregaPagina | HTTPValidationError | None:
    """Entregas

     Log de entregas do webhook (RLS do inquilino; `plat.webhook_entrega` é SELECT/UPDATE a plat_app,
    INSERT só pelo gatilho de despacho).

    Args:
        id (str):
        estado (None | str | Unset):
        limite (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EntregaPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            estado=estado,
            limite=limite,
        )
    ).parsed
