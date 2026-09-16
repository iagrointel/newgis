from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    token_path: str,
    colecao_id: str,
    *,
    limit: int | Unset = 10,
    bbox: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    token_query: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_datetime_: None | str | Unset
    if isinstance(datetime_, Unset):
        json_datetime_ = UNSET
    else:
        json_datetime_ = datetime_
    params["datetime"] = json_datetime_

    json_token_query: None | str | Unset
    if isinstance(token_query, Unset):
        json_token_query = UNSET
    else:
        json_token_query = token_query
    params["token"] = json_token_query

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token_path}/stac/collections/{colecao_id}/items".format(
            token_path=quote(str(token_path), safe=""),
            colecao_id=quote(str(colecao_id), safe=""),
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
    token_path: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 10,
    bbox: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    token_query: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Itens Listar

    Args:
        token_path (str):
        colecao_id (str):
        limit (int | Unset):  Default: 10.
        bbox (None | str | Unset):
        datetime_ (None | str | Unset):
        token_query (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token_path=token_path,
        colecao_id=colecao_id,
        limit=limit,
        bbox=bbox,
        datetime_=datetime_,
        token_query=token_query,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token_path: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 10,
    bbox: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    token_query: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Itens Listar

    Args:
        token_path (str):
        colecao_id (str):
        limit (int | Unset):  Default: 10.
        bbox (None | str | Unset):
        datetime_ (None | str | Unset):
        token_query (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token_path=token_path,
        colecao_id=colecao_id,
        client=client,
        limit=limit,
        bbox=bbox,
        datetime_=datetime_,
        token_query=token_query,
    ).parsed


async def asyncio_detailed(
    token_path: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 10,
    bbox: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    token_query: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Itens Listar

    Args:
        token_path (str):
        colecao_id (str):
        limit (int | Unset):  Default: 10.
        bbox (None | str | Unset):
        datetime_ (None | str | Unset):
        token_query (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token_path=token_path,
        colecao_id=colecao_id,
        limit=limit,
        bbox=bbox,
        datetime_=datetime_,
        token_query=token_query,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token_path: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 10,
    bbox: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    token_query: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Itens Listar

    Args:
        token_path (str):
        colecao_id (str):
        limit (int | Unset):  Default: 10.
        bbox (None | str | Unset):
        datetime_ (None | str | Unset):
        token_query (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token_path=token_path,
            colecao_id=colecao_id,
            client=client,
            limit=limit,
            bbox=bbox,
            datetime_=datetime_,
            token_query=token_query,
        )
    ).parsed
