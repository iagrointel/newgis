from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_camada_frescor_pagina import AcervoCamadaFrescorPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    fonte_id: None | str | Unset = UNSET,
    vencida: bool | None | Unset = UNSET,
    estado: str | Unset = "exposta",
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_fonte_id: None | str | Unset
    if isinstance(fonte_id, Unset):
        json_fonte_id = UNSET
    else:
        json_fonte_id = fonte_id
    params["fonte_id"] = json_fonte_id

    json_vencida: bool | None | Unset
    if isinstance(vencida, Unset):
        json_vencida = UNSET
    else:
        json_vencida = vencida
    params["vencida"] = json_vencida

    params["estado"] = estado

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    json_deslocamento: int | None | Unset
    if isinstance(deslocamento, Unset):
        json_deslocamento = UNSET
    else:
        json_deslocamento = deslocamento
    params["deslocamento"] = json_deslocamento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/camadas",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoCamadaFrescorPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoCamadaFrescorPagina.from_dict(response.json())

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
) -> Response[AcervoCamadaFrescorPagina | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    fonte_id: None | str | Unset = UNSET,
    vencida: bool | None | Unset = UNSET,
    estado: str | Unset = "exposta",
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[AcervoCamadaFrescorPagina | HTTPValidationError]:
    """Listar Camadas

    Args:
        fonte_id (None | str | Unset):
        vencida (bool | None | Unset):
        estado (str | Unset):  Default: 'exposta'.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoCamadaFrescorPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        fonte_id=fonte_id,
        vencida=vencida,
        estado=estado,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    fonte_id: None | str | Unset = UNSET,
    vencida: bool | None | Unset = UNSET,
    estado: str | Unset = "exposta",
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> AcervoCamadaFrescorPagina | HTTPValidationError | None:
    """Listar Camadas

    Args:
        fonte_id (None | str | Unset):
        vencida (bool | None | Unset):
        estado (str | Unset):  Default: 'exposta'.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoCamadaFrescorPagina | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        fonte_id=fonte_id,
        vencida=vencida,
        estado=estado,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    fonte_id: None | str | Unset = UNSET,
    vencida: bool | None | Unset = UNSET,
    estado: str | Unset = "exposta",
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[AcervoCamadaFrescorPagina | HTTPValidationError]:
    """Listar Camadas

    Args:
        fonte_id (None | str | Unset):
        vencida (bool | None | Unset):
        estado (str | Unset):  Default: 'exposta'.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoCamadaFrescorPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        fonte_id=fonte_id,
        vencida=vencida,
        estado=estado,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    fonte_id: None | str | Unset = UNSET,
    vencida: bool | None | Unset = UNSET,
    estado: str | Unset = "exposta",
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> AcervoCamadaFrescorPagina | HTTPValidationError | None:
    """Listar Camadas

    Args:
        fonte_id (None | str | Unset):
        vencida (bool | None | Unset):
        estado (str | Unset):  Default: 'exposta'.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoCamadaFrescorPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            fonte_id=fonte_id,
            vencida=vencida,
            estado=estado,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
