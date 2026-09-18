from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.restaurar_saida import RestaurarSaida
from ...types import Response


def _get_kwargs(
    id: str,
    globalid: str,
    historico_id: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/feicoes/{globalid}/historico/{historico_id}/restaurar".format(
            id=quote(str(id), safe=""),
            globalid=quote(str(globalid), safe=""),
            historico_id=quote(str(historico_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | RestaurarSaida | None:
    if response.status_code == 200:
        response_200 = RestaurarSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | RestaurarSaida]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    globalid: str,
    historico_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | RestaurarSaida]:
    """Restaurar Feicao

    Args:
        id (str):
        globalid (str):
        historico_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestaurarSaida]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        historico_id=historico_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    globalid: str,
    historico_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | RestaurarSaida | None:
    """Restaurar Feicao

    Args:
        id (str):
        globalid (str):
        historico_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestaurarSaida
    """

    return sync_detailed(
        id=id,
        globalid=globalid,
        historico_id=historico_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    globalid: str,
    historico_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | RestaurarSaida]:
    """Restaurar Feicao

    Args:
        id (str):
        globalid (str):
        historico_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestaurarSaida]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        historico_id=historico_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    globalid: str,
    historico_id: int,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | RestaurarSaida | None:
    """Restaurar Feicao

    Args:
        id (str):
        globalid (str):
        historico_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestaurarSaida
    """

    return (
        await asyncio_detailed(
            id=id,
            globalid=globalid,
            historico_id=historico_id,
            client=client,
        )
    ).parsed
