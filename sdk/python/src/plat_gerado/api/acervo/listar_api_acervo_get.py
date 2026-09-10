from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_pagina import AcervoPagina
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    dominio: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_dominio: None | str | Unset
    if isinstance(dominio, Unset):
        json_dominio = UNSET
    else:
        json_dominio = dominio
    params["dominio"] = json_dominio

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

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
        "url": "/api/acervo",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoPagina | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoPagina.from_dict(response.json())

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
) -> Response[AcervoPagina | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    dominio: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[AcervoPagina | HTTPValidationError]:
    """Listar

    Args:
        dominio (None | str | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dominio=dominio,
        q=q,
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
    dominio: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> AcervoPagina | HTTPValidationError | None:
    """Listar

    Args:
        dominio (None | str | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoPagina | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        dominio=dominio,
        q=q,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    dominio: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[AcervoPagina | HTTPValidationError]:
    """Listar

    Args:
        dominio (None | str | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoPagina | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dominio=dominio,
        q=q,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    dominio: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> AcervoPagina | HTTPValidationError | None:
    """Listar

    Args:
        dominio (None | str | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoPagina | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            dominio=dominio,
            q=q,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
