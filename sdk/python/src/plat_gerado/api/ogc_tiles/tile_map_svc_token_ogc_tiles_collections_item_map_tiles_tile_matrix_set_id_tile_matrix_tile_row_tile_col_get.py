from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    token: str,
    item: str,
    tile_matrix_set_id: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    *,
    f: str | Unset = "png",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["f"] = f

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/ogc/tiles/collections/{item}/map/tiles/{tile_matrix_set_id}/{tile_matrix}/{tile_row}/{tile_col}".format(
            token=quote(str(token), safe=""),
            item=quote(str(item), safe=""),
            tile_matrix_set_id=quote(str(tile_matrix_set_id), safe=""),
            tile_matrix=quote(str(tile_matrix), safe=""),
            tile_row=quote(str(tile_row), safe=""),
            tile_col=quote(str(tile_col), safe=""),
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
    token: str,
    item: str,
    tile_matrix_set_id: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "png",
) -> Response[Any | HTTPValidationError]:
    """ladrilho (map tile)

    Args:
        token (str):
        item (str):
        tile_matrix_set_id (str):
        tile_matrix (int):
        tile_row (int):
        tile_col (int):
        f (str | Unset):  Default: 'png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        tile_matrix_set_id=tile_matrix_set_id,
        tile_matrix=tile_matrix,
        tile_row=tile_row,
        tile_col=tile_col,
        f=f,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item: str,
    tile_matrix_set_id: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "png",
) -> Any | HTTPValidationError | None:
    """ladrilho (map tile)

    Args:
        token (str):
        item (str):
        tile_matrix_set_id (str):
        tile_matrix (int):
        tile_row (int):
        tile_col (int):
        f (str | Unset):  Default: 'png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item=item,
        tile_matrix_set_id=tile_matrix_set_id,
        tile_matrix=tile_matrix,
        tile_row=tile_row,
        tile_col=tile_col,
        client=client,
        f=f,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    tile_matrix_set_id: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "png",
) -> Response[Any | HTTPValidationError]:
    """ladrilho (map tile)

    Args:
        token (str):
        item (str):
        tile_matrix_set_id (str):
        tile_matrix (int):
        tile_row (int):
        tile_col (int):
        f (str | Unset):  Default: 'png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        tile_matrix_set_id=tile_matrix_set_id,
        tile_matrix=tile_matrix,
        tile_row=tile_row,
        tile_col=tile_col,
        f=f,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    tile_matrix_set_id: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "png",
) -> Any | HTTPValidationError | None:
    """ladrilho (map tile)

    Args:
        token (str):
        item (str):
        tile_matrix_set_id (str):
        tile_matrix (int):
        tile_row (int):
        tile_col (int):
        f (str | Unset):  Default: 'png'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            item=item,
            tile_matrix_set_id=tile_matrix_set_id,
            tile_matrix=tile_matrix,
            tile_row=tile_row,
            tile_col=tile_col,
            client=client,
            f=f,
        )
    ).parsed
