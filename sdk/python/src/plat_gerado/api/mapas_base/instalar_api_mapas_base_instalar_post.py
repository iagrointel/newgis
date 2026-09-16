from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.item import Item
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/mapas-base/instalar",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> list[Item] | None:
    if response.status_code == 201:
        response_201 = []
        _response_201 = response.json()
        for response_201_item_data in _response_201:
            response_201_item = Item.from_dict(response_201_item_data)

            response_201.append(response_201_item)

        return response_201

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[list[Item]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[list[Item]]:
    """Instalar

     Cria os itens que faltam entre as fontes padrão (semear.definicoes_padrao); pular o que o admin já
    tem
    instalado (por `dados.tipo`, nunca por título — o admin pode ter renomeado) faz a rota ser chamável
    de
    novo sem duplicar nem sobrescrever edição manual (ordem/padrão/título já mudados).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Item]]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> list[Item] | None:
    """Instalar

     Cria os itens que faltam entre as fontes padrão (semear.definicoes_padrao); pular o que o admin já
    tem
    instalado (por `dados.tipo`, nunca por título — o admin pode ter renomeado) faz a rota ser chamável
    de
    novo sem duplicar nem sobrescrever edição manual (ordem/padrão/título já mudados).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Item]
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[list[Item]]:
    """Instalar

     Cria os itens que faltam entre as fontes padrão (semear.definicoes_padrao); pular o que o admin já
    tem
    instalado (por `dados.tipo`, nunca por título — o admin pode ter renomeado) faz a rota ser chamável
    de
    novo sem duplicar nem sobrescrever edição manual (ordem/padrão/título já mudados).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Item]]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> list[Item] | None:
    """Instalar

     Cria os itens que faltam entre as fontes padrão (semear.definicoes_padrao); pular o que o admin já
    tem
    instalado (por `dados.tipo`, nunca por título — o admin pode ter renomeado) faz a rota ser chamável
    de
    novo sem duplicar nem sobrescrever edição manual (ordem/padrão/título já mudados).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Item]
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
