from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.listar_roteiros_api_campo_roteiros_get_response_listar_roteiros_api_campo_roteiros_get import (
    ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    fila_id: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_fila_id: None | str | Unset
    if isinstance(fila_id, Unset):
        json_fila_id = UNSET
    else:
        json_fila_id = fila_id
    params["fila_id"] = json_fila_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/campo/roteiros",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet | None:
    if response.status_code == 200:
        response_200 = ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet.from_dict(
            response.json()
        )

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
) -> Response[HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet]:
    """Listar Roteiros

    Args:
        fila_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet]
    """

    kwargs = _get_kwargs(
        fila_id=fila_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
) -> HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet | None:
    """Listar Roteiros

    Args:
        fila_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet
    """

    return sync_detailed(
        client=client,
        fila_id=fila_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet]:
    """Listar Roteiros

    Args:
        fila_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet]
    """

    kwargs = _get_kwargs(
        fila_id=fila_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
) -> HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet | None:
    """Listar Roteiros

    Args:
        fila_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarRoteirosApiCampoRoteirosGetResponseListarRoteirosApiCampoRoteirosGet
    """

    return (
        await asyncio_detailed(
            client=client,
            fila_id=fila_id,
        )
    ).parsed
