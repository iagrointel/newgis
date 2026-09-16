from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    *,
    camada: str,
    formato: str | Unset = "image/png",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["camada"] = camada

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/wmts/tile/{tile_matrix_set}/{z}/{x}/{y}".format(
            id=quote(str(id), safe=""),
            tile_matrix_set=quote(str(tile_matrix_set), safe=""),
            z=quote(str(z), safe=""),
            x=quote(str(x), safe=""),
            y=quote(str(y), safe=""),
        ),
        "params": params,
    }

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
    id: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    formato: str | Unset = "image/png",
) -> Response[Any | HTTPValidationError]:
    """Wmts Tile

    Args:
        id (str):
        tile_matrix_set (str):
        z (int):
        x (int):
        y (int):
        camada (str):
        formato (str | Unset):  Default: 'image/png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        tile_matrix_set=tile_matrix_set,
        z=z,
        x=x,
        y=y,
        camada=camada,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    formato: str | Unset = "image/png",
) -> Any | HTTPValidationError | None:
    """Wmts Tile

    Args:
        id (str):
        tile_matrix_set (str):
        z (int):
        x (int):
        y (int):
        camada (str):
        formato (str | Unset):  Default: 'image/png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        tile_matrix_set=tile_matrix_set,
        z=z,
        x=x,
        y=y,
        client=client,
        camada=camada,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    id: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    formato: str | Unset = "image/png",
) -> Response[Any | HTTPValidationError]:
    """Wmts Tile

    Args:
        id (str):
        tile_matrix_set (str):
        z (int):
        x (int):
        y (int):
        camada (str):
        formato (str | Unset):  Default: 'image/png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        tile_matrix_set=tile_matrix_set,
        z=z,
        x=x,
        y=y,
        camada=camada,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    tile_matrix_set: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    formato: str | Unset = "image/png",
) -> Any | HTTPValidationError | None:
    """Wmts Tile

    Args:
        id (str):
        tile_matrix_set (str):
        z (int):
        x (int):
        y (int):
        camada (str):
        formato (str | Unset):  Default: 'image/png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            tile_matrix_set=tile_matrix_set,
            z=z,
            x=x,
            y=y,
            client=client,
            camada=camada,
            formato=formato,
        )
    ).parsed
