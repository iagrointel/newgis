from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.divide_entrada import DivideEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: DivideEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/parcelas/fabrica/divide",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DivideEntrada,
) -> Response[Any | HTTPValidationError]:
    """Divide

     Divide (forma da doc `.../ParcelFabricServer/divide`): por rumo com divideOption
    (ProportionalArea/EqualArea/EqualWidth) ou por linha de corte direta (campo `linha`).

    Args:
        body (DivideEntrada): Divide na forma da doc (divideOption + bearing) OU com linha de
            corte direta (campo
            `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: DivideEntrada,
) -> Any | HTTPValidationError | None:
    """Divide

     Divide (forma da doc `.../ParcelFabricServer/divide`): por rumo com divideOption
    (ProportionalArea/EqualArea/EqualWidth) ou por linha de corte direta (campo `linha`).

    Args:
        body (DivideEntrada): Divide na forma da doc (divideOption + bearing) OU com linha de
            corte direta (campo
            `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DivideEntrada,
) -> Response[Any | HTTPValidationError]:
    """Divide

     Divide (forma da doc `.../ParcelFabricServer/divide`): por rumo com divideOption
    (ProportionalArea/EqualArea/EqualWidth) ou por linha de corte direta (campo `linha`).

    Args:
        body (DivideEntrada): Divide na forma da doc (divideOption + bearing) OU com linha de
            corte direta (campo
            `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: DivideEntrada,
) -> Any | HTTPValidationError | None:
    """Divide

     Divide (forma da doc `.../ParcelFabricServer/divide`): por rumo com divideOption
    (ProportionalArea/EqualArea/EqualWidth) ou por linha de corte direta (campo `linha`).

    Args:
        body (DivideEntrada): Divide na forma da doc (divideOption + bearing) OU com linha de
            corte direta (campo
            `linha`, com 2 pontos) — o corte por linha é extra declarado da casa (§11).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
