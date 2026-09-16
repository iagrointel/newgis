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
    *,
    collections: None | str | Unset = UNSET,
    ids: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    intersects: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | Unset = 10,
    token_query: None | str | Unset = UNSET,
    sortby: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_collections: None | str | Unset
    if isinstance(collections, Unset):
        json_collections = UNSET
    else:
        json_collections = collections
    params["collections"] = json_collections

    json_ids: None | str | Unset
    if isinstance(ids, Unset):
        json_ids = UNSET
    else:
        json_ids = ids
    params["ids"] = json_ids

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_intersects: None | str | Unset
    if isinstance(intersects, Unset):
        json_intersects = UNSET
    else:
        json_intersects = intersects
    params["intersects"] = json_intersects

    json_datetime_: None | str | Unset
    if isinstance(datetime_, Unset):
        json_datetime_ = UNSET
    else:
        json_datetime_ = datetime_
    params["datetime"] = json_datetime_

    params["limit"] = limit

    json_token_query: None | str | Unset
    if isinstance(token_query, Unset):
        json_token_query = UNSET
    else:
        json_token_query = token_query
    params["token"] = json_token_query

    json_sortby: None | str | Unset
    if isinstance(sortby, Unset):
        json_sortby = UNSET
    else:
        json_sortby = sortby
    params["sortby"] = json_sortby

    json_filter_: None | str | Unset
    if isinstance(filter_, Unset):
        json_filter_ = UNSET
    else:
        json_filter_ = filter_
    params["filter"] = json_filter_

    json_filter_lang: None | str | Unset
    if isinstance(filter_lang, Unset):
        json_filter_lang = UNSET
    else:
        json_filter_lang = filter_lang
    params["filter-lang"] = json_filter_lang

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token_path}/stac/search".format(
            token_path=quote(str(token_path), safe=""),
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
    *,
    client: AuthenticatedClient | Client,
    collections: None | str | Unset = UNSET,
    ids: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    intersects: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | Unset = 10,
    token_query: None | str | Unset = UNSET,
    sortby: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Busca Get

    Args:
        token_path (str):
        collections (None | str | Unset):
        ids (None | str | Unset):
        bbox (None | str | Unset):
        intersects (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | Unset):  Default: 10.
        token_query (None | str | Unset):
        sortby (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token_path=token_path,
        collections=collections,
        ids=ids,
        bbox=bbox,
        intersects=intersects,
        datetime_=datetime_,
        limit=limit,
        token_query=token_query,
        sortby=sortby,
        filter_=filter_,
        filter_lang=filter_lang,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token_path: str,
    *,
    client: AuthenticatedClient | Client,
    collections: None | str | Unset = UNSET,
    ids: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    intersects: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | Unset = 10,
    token_query: None | str | Unset = UNSET,
    sortby: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Busca Get

    Args:
        token_path (str):
        collections (None | str | Unset):
        ids (None | str | Unset):
        bbox (None | str | Unset):
        intersects (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | Unset):  Default: 10.
        token_query (None | str | Unset):
        sortby (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token_path=token_path,
        client=client,
        collections=collections,
        ids=ids,
        bbox=bbox,
        intersects=intersects,
        datetime_=datetime_,
        limit=limit,
        token_query=token_query,
        sortby=sortby,
        filter_=filter_,
        filter_lang=filter_lang,
    ).parsed


async def asyncio_detailed(
    token_path: str,
    *,
    client: AuthenticatedClient | Client,
    collections: None | str | Unset = UNSET,
    ids: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    intersects: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | Unset = 10,
    token_query: None | str | Unset = UNSET,
    sortby: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Busca Get

    Args:
        token_path (str):
        collections (None | str | Unset):
        ids (None | str | Unset):
        bbox (None | str | Unset):
        intersects (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | Unset):  Default: 10.
        token_query (None | str | Unset):
        sortby (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token_path=token_path,
        collections=collections,
        ids=ids,
        bbox=bbox,
        intersects=intersects,
        datetime_=datetime_,
        limit=limit,
        token_query=token_query,
        sortby=sortby,
        filter_=filter_,
        filter_lang=filter_lang,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token_path: str,
    *,
    client: AuthenticatedClient | Client,
    collections: None | str | Unset = UNSET,
    ids: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    intersects: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | Unset = 10,
    token_query: None | str | Unset = UNSET,
    sortby: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Busca Get

    Args:
        token_path (str):
        collections (None | str | Unset):
        ids (None | str | Unset):
        bbox (None | str | Unset):
        intersects (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | Unset):  Default: 10.
        token_query (None | str | Unset):
        sortby (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token_path=token_path,
            client=client,
            collections=collections,
            ids=ids,
            bbox=bbox,
            intersects=intersects,
            datetime_=datetime_,
            limit=limit,
            token_query=token_query,
            sortby=sortby,
            filter_=filter_,
            filter_lang=filter_lang,
        )
    ).parsed
