from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.faixa_pagina import FaixaPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    tipo_id: None | str | Unset = UNSET,
    minhas: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tipo_id: None | str | Unset
    if isinstance(tipo_id, Unset):
        json_tipo_id = UNSET
    else:
        json_tipo_id = tipo_id
    params["tipo_id"] = json_tipo_id

    params["minhas"] = minhas

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/faixas".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FaixaPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FaixaPagina.from_dict(response.json())

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
) -> Response[FaixaPagina | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    minhas: bool | Unset = False,
) -> Response[FaixaPagina | HTTPValidationError]:
    """Listar Faixas

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        minhas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FaixaPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        minhas=minhas,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    minhas: bool | Unset = False,
) -> FaixaPagina | HTTPValidationError | None:
    """Listar Faixas

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        minhas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FaixaPagina | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        tipo_id=tipo_id,
        minhas=minhas,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    minhas: bool | Unset = False,
) -> Response[FaixaPagina | HTTPValidationError]:
    """Listar Faixas

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        minhas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FaixaPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        minhas=minhas,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    minhas: bool | Unset = False,
) -> FaixaPagina | HTTPValidationError | None:
    """Listar Faixas

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        minhas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FaixaPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            tipo_id=tipo_id,
            minhas=minhas,
        )
    ).parsed
