from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ativo_pagina import AtivoPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    tipo_id: None | str | Unset = UNSET,
    codigo_externo: None | str | Unset = UNSET,
    limite: int | Unset = 200,
    deslocamento: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tipo_id: None | str | Unset
    if isinstance(tipo_id, Unset):
        json_tipo_id = UNSET
    else:
        json_tipo_id = tipo_id
    params["tipo_id"] = json_tipo_id

    json_codigo_externo: None | str | Unset
    if isinstance(codigo_externo, Unset):
        json_codigo_externo = UNSET
    else:
        json_codigo_externo = codigo_externo
    params["codigo_externo"] = json_codigo_externo

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/ativos".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AtivoPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AtivoPagina.from_dict(response.json())

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
) -> Response[AtivoPagina | HTTPValidationError]:
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
    codigo_externo: None | str | Unset = UNSET,
    limite: int | Unset = 200,
    deslocamento: int | Unset = 0,
) -> Response[AtivoPagina | HTTPValidationError]:
    """Listar Ativos

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        codigo_externo (None | str | Unset):
        limite (int | Unset):  Default: 200.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AtivoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        codigo_externo=codigo_externo,
        limite=limite,
        deslocamento=deslocamento,
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
    codigo_externo: None | str | Unset = UNSET,
    limite: int | Unset = 200,
    deslocamento: int | Unset = 0,
) -> AtivoPagina | HTTPValidationError | None:
    """Listar Ativos

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        codigo_externo (None | str | Unset):
        limite (int | Unset):  Default: 200.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AtivoPagina | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        tipo_id=tipo_id,
        codigo_externo=codigo_externo,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    codigo_externo: None | str | Unset = UNSET,
    limite: int | Unset = 200,
    deslocamento: int | Unset = 0,
) -> Response[AtivoPagina | HTTPValidationError]:
    """Listar Ativos

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        codigo_externo (None | str | Unset):
        limite (int | Unset):  Default: 200.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AtivoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        codigo_externo=codigo_externo,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    tipo_id: None | str | Unset = UNSET,
    codigo_externo: None | str | Unset = UNSET,
    limite: int | Unset = 200,
    deslocamento: int | Unset = 0,
) -> AtivoPagina | HTTPValidationError | None:
    """Listar Ativos

    Args:
        rede_id (str):
        tipo_id (None | str | Unset):
        codigo_externo (None | str | Unset):
        limite (int | Unset):  Default: 200.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AtivoPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            tipo_id=tipo_id,
            codigo_externo=codigo_externo,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
