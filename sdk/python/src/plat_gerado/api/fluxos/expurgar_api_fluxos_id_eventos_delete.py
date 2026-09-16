from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.expurgo import Expurgo
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    id: str,
    *,
    antes_de: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["antes_de"] = antes_de

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/fluxos/{id}/eventos".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Expurgo | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = Expurgo.from_dict(response.json())

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
) -> Response[Expurgo | HTTPValidationError]:
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
    antes_de: str,
) -> Response[Expurgo | HTTPValidationError]:
    """Expurgar

    Args:
        id (str):
        antes_de (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Expurgo | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        antes_de=antes_de,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    antes_de: str,
) -> Expurgo | HTTPValidationError | None:
    """Expurgar

    Args:
        id (str):
        antes_de (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Expurgo | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        antes_de=antes_de,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    antes_de: str,
) -> Response[Expurgo | HTTPValidationError]:
    """Expurgar

    Args:
        id (str):
        antes_de (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Expurgo | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        antes_de=antes_de,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    antes_de: str,
) -> Expurgo | HTTPValidationError | None:
    """Expurgar

    Args:
        id (str):
        antes_de (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Expurgo | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            antes_de=antes_de,
        )
    ).parsed
