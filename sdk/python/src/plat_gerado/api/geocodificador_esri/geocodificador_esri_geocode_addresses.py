from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/rest/services/Geocodificador/GeocodeServer/geocodeAddresses",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 200:
        return None

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Geocode Addresses

     Lote (item L2-11-a-geocodificacao-csv reusa este mesmo caminho para o motor, não esta rota HTTP).
    Corpo: {"addresses": {"records": [{"attributes": {"OBJECTID": 1, "SingleLine": "..."}}]}} — igual ao
    parâmetro `addresses` do geocodeAddresses da Esri (aqui já como JSON de corpo, não form-encoded,
    porque
    o único cliente medido neste turno é o teste HTTP direto; um cliente Esri real manda
    form/querystring —
    registrado como pendência em docs/PARIDADE.md, não como feito).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Geocode Addresses

     Lote (item L2-11-a-geocodificacao-csv reusa este mesmo caminho para o motor, não esta rota HTTP).
    Corpo: {"addresses": {"records": [{"attributes": {"OBJECTID": 1, "SingleLine": "..."}}]}} — igual ao
    parâmetro `addresses` do geocodeAddresses da Esri (aqui já como JSON de corpo, não form-encoded,
    porque
    o único cliente medido neste turno é o teste HTTP direto; um cliente Esri real manda
    form/querystring —
    registrado como pendência em docs/PARIDADE.md, não como feito).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
