from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.painel import Painel
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    dias: int | Unset = 30,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["dias"] = dias

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/atividade",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | Painel | None:
    if response.status_code == 200:
        response_200 = Painel.from_dict(response.json())

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
) -> Response[HTTPValidationError | Painel]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> Response[HTTPValidationError | Painel]:
    """Atividade

    Args:
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Painel]
    """

    kwargs = _get_kwargs(
        dias=dias,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> HTTPValidationError | Painel | None:
    """Atividade

    Args:
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Painel
    """

    return sync_detailed(
        client=client,
        dias=dias,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> Response[HTTPValidationError | Painel]:
    """Atividade

    Args:
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Painel]
    """

    kwargs = _get_kwargs(
        dias=dias,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    dias: int | Unset = 30,
) -> HTTPValidationError | Painel | None:
    """Atividade

    Args:
        dias (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Painel
    """

    return (
        await asyncio_detailed(
            client=client,
            dias=dias,
        )
    ).parsed
