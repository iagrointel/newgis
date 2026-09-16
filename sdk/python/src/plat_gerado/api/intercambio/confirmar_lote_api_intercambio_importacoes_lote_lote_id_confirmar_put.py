from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.confirmar_lote_entrada import ConfirmarLoteEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    lote_id: str,
    *,
    body: ConfirmarLoteEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/intercambio/importacoes-lote/{lote_id}/confirmar".format(
            lote_id=quote(str(lote_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = response.json()
        return response_202

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
    lote_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarLoteEntrada,
) -> Response[Any | HTTPValidationError]:
    """Confirmar Lote

    Args:
        lote_id (str):
        body (ConfirmarLoteEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lote_id=lote_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    lote_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarLoteEntrada,
) -> Any | HTTPValidationError | None:
    """Confirmar Lote

    Args:
        lote_id (str):
        body (ConfirmarLoteEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        lote_id=lote_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    lote_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarLoteEntrada,
) -> Response[Any | HTTPValidationError]:
    """Confirmar Lote

    Args:
        lote_id (str):
        body (ConfirmarLoteEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lote_id=lote_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    lote_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarLoteEntrada,
) -> Any | HTTPValidationError | None:
    """Confirmar Lote

    Args:
        lote_id (str):
        body (ConfirmarLoteEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            lote_id=lote_id,
            client=client,
            body=body,
        )
    ).parsed
