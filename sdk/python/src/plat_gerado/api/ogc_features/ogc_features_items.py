from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    colecao_id: str,
    *,
    bbox: None | str | Unset = UNSET,
    bbox_crs: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_bbox_crs: None | str | Unset
    if isinstance(bbox_crs, Unset):
        json_bbox_crs = UNSET
    else:
        json_bbox_crs = bbox_crs
    params["bbox-crs"] = json_bbox_crs

    json_crs: None | str | Unset
    if isinstance(crs, Unset):
        json_crs = UNSET
    else:
        json_crs = crs
    params["crs"] = json_crs

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

    json_datetime_: None | str | Unset
    if isinstance(datetime_, Unset):
        json_datetime_ = UNSET
    else:
        json_datetime_ = datetime_
    params["datetime"] = json_datetime_

    json_limit: int | None | Unset
    if isinstance(limit, Unset):
        json_limit = UNSET
    else:
        json_limit = limit
    params["limit"] = json_limit

    json_offset: int | None | Unset
    if isinstance(offset, Unset):
        json_offset = UNSET
    else:
        json_offset = offset
    params["offset"] = json_offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/ogc/features/{item_id}/collections/{colecao_id}/items".format(
            item_id=quote(str(item_id), safe=""),
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
    item_id: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    bbox_crs: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Items

    Args:
        item_id (str):
        colecao_id (str):
        bbox (None | str | Unset):
        bbox_crs (None | str | Unset):
        crs (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        colecao_id=colecao_id,
        bbox=bbox,
        bbox_crs=bbox_crs,
        crs=crs,
        filter_=filter_,
        filter_lang=filter_lang,
        datetime_=datetime_,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    bbox_crs: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Items

    Args:
        item_id (str):
        colecao_id (str):
        bbox (None | str | Unset):
        bbox_crs (None | str | Unset):
        crs (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        colecao_id=colecao_id,
        client=client,
        bbox=bbox,
        bbox_crs=bbox_crs,
        crs=crs,
        filter_=filter_,
        filter_lang=filter_lang,
        datetime_=datetime_,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    bbox_crs: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Items

    Args:
        item_id (str):
        colecao_id (str):
        bbox (None | str | Unset):
        bbox_crs (None | str | Unset):
        crs (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        colecao_id=colecao_id,
        bbox=bbox,
        bbox_crs=bbox_crs,
        crs=crs,
        filter_=filter_,
        filter_lang=filter_lang,
        datetime_=datetime_,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    bbox_crs: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    filter_: None | str | Unset = UNSET,
    filter_lang: None | str | Unset = UNSET,
    datetime_: None | str | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Items

    Args:
        item_id (str):
        colecao_id (str):
        bbox (None | str | Unset):
        bbox_crs (None | str | Unset):
        crs (None | str | Unset):
        filter_ (None | str | Unset):
        filter_lang (None | str | Unset):
        datetime_ (None | str | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            colecao_id=colecao_id,
            client=client,
            bbox=bbox,
            bbox_crs=bbox_crs,
            crs=crs,
            filter_=filter_,
            filter_lang=filter_lang,
            datetime_=datetime_,
            limit=limit,
            offset=offset,
        )
    ).parsed
