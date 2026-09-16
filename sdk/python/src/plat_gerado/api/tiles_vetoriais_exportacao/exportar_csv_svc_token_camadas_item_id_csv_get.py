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
    item_id: str,
    *,
    where: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_where: None | str | Unset
    if isinstance(where, Unset):
        json_where = UNSET
    else:
        json_where = where
    params["where"] = json_where

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/camadas/{item_id}.csv".format(
            token=quote(str(token), safe=""),
            item_id=quote(str(item_id), safe=""),
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
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    where: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """exportação CSV (streaming, geometria em WKT)

    Args:
        token (str):
        item_id (str):
        where (None | str | Unset):
        bbox (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item_id=item_id,
        where=where,
        bbox=bbox,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    where: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """exportação CSV (streaming, geometria em WKT)

    Args:
        token (str):
        item_id (str):
        where (None | str | Unset):
        bbox (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item_id=item_id,
        client=client,
        where=where,
        bbox=bbox,
    ).parsed


async def asyncio_detailed(
    token: str,
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    where: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """exportação CSV (streaming, geometria em WKT)

    Args:
        token (str):
        item_id (str):
        where (None | str | Unset):
        bbox (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item_id=item_id,
        where=where,
        bbox=bbox,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    where: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """exportação CSV (streaming, geometria em WKT)

    Args:
        token (str):
        item_id (str):
        where (None | str | Unset):
        bbox (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            item_id=item_id,
            client=client,
            where=where,
            bbox=bbox,
        )
    ).parsed
