from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.erro import Erro
from ...models.lista_agendas import ListaAgendas
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    ativa: bool | None | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_ativa: bool | None | Unset
    if isinstance(ativa, Unset):
        json_ativa = UNSET
    else:
        json_ativa = ativa
    params["ativa"] = json_ativa

    json_tipo: None | str | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/agendas",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Erro | ListaAgendas | None:
    if response.status_code == 200:
        response_200 = ListaAgendas.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = Erro.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Erro.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Erro.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Erro.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = Erro.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Erro.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Erro.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Erro | ListaAgendas]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    ativa: bool | None | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
) -> Response[Erro | ListaAgendas]:
    """Listar Agendas

    Args:
        ativa (bool | None | Unset):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | ListaAgendas]
    """

    kwargs = _get_kwargs(
        ativa=ativa,
        tipo=tipo,
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
    ativa: bool | None | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
) -> Erro | ListaAgendas | None:
    """Listar Agendas

    Args:
        ativa (bool | None | Unset):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | ListaAgendas
    """

    return sync_detailed(
        client=client,
        ativa=ativa,
        tipo=tipo,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    ativa: bool | None | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
) -> Response[Erro | ListaAgendas]:
    """Listar Agendas

    Args:
        ativa (bool | None | Unset):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | ListaAgendas]
    """

    kwargs = _get_kwargs(
        ativa=ativa,
        tipo=tipo,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    ativa: bool | None | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
) -> Erro | ListaAgendas | None:
    """Listar Agendas

    Args:
        ativa (bool | None | Unset):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | ListaAgendas
    """

    return (
        await asyncio_detailed(
            client=client,
            ativa=ativa,
            tipo=tipo,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
