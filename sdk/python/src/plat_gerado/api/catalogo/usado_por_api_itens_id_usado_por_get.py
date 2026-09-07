from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.usado_por import UsadoPor
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    profundidade: int | Unset = 2,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["profundidade"] = profundidade

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/usado-por".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[UsadoPor] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = UsadoPor.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[UsadoPor]]:
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
    profundidade: int | Unset = 2,
) -> Response[HTTPValidationError | list[UsadoPor]]:
    """Usado Por

    Args:
        id (str):
        profundidade (int | Unset):  Default: 2.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[UsadoPor]]
    """

    kwargs = _get_kwargs(
        id=id,
        profundidade=profundidade,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    profundidade: int | Unset = 2,
) -> HTTPValidationError | list[UsadoPor] | None:
    """Usado Por

    Args:
        id (str):
        profundidade (int | Unset):  Default: 2.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[UsadoPor]
    """

    return sync_detailed(
        id=id,
        client=client,
        profundidade=profundidade,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    profundidade: int | Unset = 2,
) -> Response[HTTPValidationError | list[UsadoPor]]:
    """Usado Por

    Args:
        id (str):
        profundidade (int | Unset):  Default: 2.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[UsadoPor]]
    """

    kwargs = _get_kwargs(
        id=id,
        profundidade=profundidade,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    profundidade: int | Unset = 2,
) -> HTTPValidationError | list[UsadoPor] | None:
    """Usado Por

    Args:
        id (str):
        profundidade (int | Unset):  Default: 2.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[UsadoPor]
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            profundidade=profundidade,
        )
    ).parsed
