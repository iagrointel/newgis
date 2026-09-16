from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.evento_pagina import EventoPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    rastro: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_desde: None | str | Unset
    if isinstance(desde, Unset):
        json_desde = UNSET
    else:
        json_desde = desde
    params["desde"] = json_desde

    json_ate: None | str | Unset
    if isinstance(ate, Unset):
        json_ate = UNSET
    else:
        json_ate = ate
    params["ate"] = json_ate

    json_rastro: None | str | Unset
    if isinstance(rastro, Unset):
        json_rastro = UNSET
    else:
        json_rastro = rastro
    params["rastro"] = json_rastro

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/fluxos/{id}/eventos".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EventoPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EventoPagina.from_dict(response.json())

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
) -> Response[EventoPagina | HTTPValidationError]:
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
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    rastro: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> Response[EventoPagina | HTTPValidationError]:
    """Eventos

    Args:
        id (str):
        desde (None | str | Unset):
        ate (None | str | Unset):
        rastro (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        desde=desde,
        ate=ate,
        rastro=rastro,
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
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    rastro: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> EventoPagina | HTTPValidationError | None:
    """Eventos

    Args:
        id (str):
        desde (None | str | Unset):
        ate (None | str | Unset):
        rastro (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventoPagina | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        desde=desde,
        ate=ate,
        rastro=rastro,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    rastro: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> Response[EventoPagina | HTTPValidationError]:
    """Eventos

    Args:
        id (str):
        desde (None | str | Unset):
        ate (None | str | Unset):
        rastro (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EventoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        desde=desde,
        ate=ate,
        rastro=rastro,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    rastro: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> EventoPagina | HTTPValidationError | None:
    """Eventos

    Args:
        id (str):
        desde (None | str | Unset):
        ate (None | str | Unset):
        rastro (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EventoPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            desde=desde,
            ate=ate,
            rastro=rastro,
            limite=limite,
        )
    ).parsed
