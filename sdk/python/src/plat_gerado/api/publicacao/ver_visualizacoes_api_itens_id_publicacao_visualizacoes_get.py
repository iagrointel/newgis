from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.visualizacao_dia import VisualizacaoDia
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    dias: int | Unset = 30,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["dias"] = dias

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/publicacao/visualizacoes".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[VisualizacaoDia] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = VisualizacaoDia.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[VisualizacaoDia]]:
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
    dias: int | Unset = 30,
) -> Response[HTTPValidationError | list[VisualizacaoDia]]:
    """Ver Visualizacoes

    Args:
        id (str):
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[VisualizacaoDia]]
    """

    kwargs = _get_kwargs(
        id=id,
        dias=dias,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> HTTPValidationError | list[VisualizacaoDia] | None:
    """Ver Visualizacoes

    Args:
        id (str):
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[VisualizacaoDia]
    """

    return sync_detailed(
        id=id,
        client=client,
        dias=dias,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> Response[HTTPValidationError | list[VisualizacaoDia]]:
    """Ver Visualizacoes

    Args:
        id (str):
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[VisualizacaoDia]]
    """

    kwargs = _get_kwargs(
        id=id,
        dias=dias,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> HTTPValidationError | list[VisualizacaoDia] | None:
    """Ver Visualizacoes

    Args:
        id (str):
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[VisualizacaoDia]
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            dias=dias,
        )
    ).parsed
