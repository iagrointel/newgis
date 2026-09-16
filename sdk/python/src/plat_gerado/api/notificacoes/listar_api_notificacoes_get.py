from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.lista_notificacoes import ListaNotificacoes
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limite: int | Unset = 20,
    deslocamento: int | Unset = 0,
    apenas_nao_lidas: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params["apenas_nao_lidas"] = apenas_nao_lidas

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/notificacoes",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ListaNotificacoes | None:
    if response.status_code == 200:
        response_200 = ListaNotificacoes.from_dict(response.json())

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
) -> Response[HTTPValidationError | ListaNotificacoes]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 20,
    deslocamento: int | Unset = 0,
    apenas_nao_lidas: bool | Unset = False,
) -> Response[HTTPValidationError | ListaNotificacoes]:
    """Listar

    Args:
        limite (int | Unset):  Default: 20.
        deslocamento (int | Unset):  Default: 0.
        apenas_nao_lidas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListaNotificacoes]
    """

    kwargs = _get_kwargs(
        limite=limite,
        deslocamento=deslocamento,
        apenas_nao_lidas=apenas_nao_lidas,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 20,
    deslocamento: int | Unset = 0,
    apenas_nao_lidas: bool | Unset = False,
) -> HTTPValidationError | ListaNotificacoes | None:
    """Listar

    Args:
        limite (int | Unset):  Default: 20.
        deslocamento (int | Unset):  Default: 0.
        apenas_nao_lidas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListaNotificacoes
    """

    return sync_detailed(
        client=client,
        limite=limite,
        deslocamento=deslocamento,
        apenas_nao_lidas=apenas_nao_lidas,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 20,
    deslocamento: int | Unset = 0,
    apenas_nao_lidas: bool | Unset = False,
) -> Response[HTTPValidationError | ListaNotificacoes]:
    """Listar

    Args:
        limite (int | Unset):  Default: 20.
        deslocamento (int | Unset):  Default: 0.
        apenas_nao_lidas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListaNotificacoes]
    """

    kwargs = _get_kwargs(
        limite=limite,
        deslocamento=deslocamento,
        apenas_nao_lidas=apenas_nao_lidas,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 20,
    deslocamento: int | Unset = 0,
    apenas_nao_lidas: bool | Unset = False,
) -> HTTPValidationError | ListaNotificacoes | None:
    """Listar

    Args:
        limite (int | Unset):  Default: 20.
        deslocamento (int | Unset):  Default: 0.
        apenas_nao_lidas (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListaNotificacoes
    """

    return (
        await asyncio_detailed(
            client=client,
            limite=limite,
            deslocamento=deslocamento,
            apenas_nao_lidas=apenas_nao_lidas,
        )
    ).parsed
