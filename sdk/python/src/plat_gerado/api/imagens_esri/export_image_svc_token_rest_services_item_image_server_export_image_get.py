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
    *,
    bbox: str,
    bbox_sr: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    image_sr: None | str | Unset = UNSET,
    format_: str | Unset = "png",
    f: str | Unset = "image",
    asset: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["bbox"] = bbox

    json_bbox_sr: None | str | Unset
    if isinstance(bbox_sr, Unset):
        json_bbox_sr = UNSET
    else:
        json_bbox_sr = bbox_sr
    params["bboxSR"] = json_bbox_sr

    json_size: None | str | Unset
    if isinstance(size, Unset):
        json_size = UNSET
    else:
        json_size = size
    params["size"] = json_size

    json_image_sr: None | str | Unset
    if isinstance(image_sr, Unset):
        json_image_sr = UNSET
    else:
        json_image_sr = image_sr
    params["imageSR"] = json_image_sr

    params["format"] = format_

    params["f"] = f

    json_asset: None | str | Unset
    if isinstance(asset, Unset):
        json_asset = UNSET
    else:
        json_asset = asset
    params["asset"] = json_asset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/rest/services/{item}/ImageServer/exportImage".format(
            token=quote(str(token), safe=""),
            item=quote(str(item), safe=""),
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
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    bbox_sr: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    image_sr: None | str | Unset = UNSET,
    format_: str | Unset = "png",
    f: str | Unset = "image",
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """recorte por bbox (equivalente ao Export Image)

    Args:
        token (str):
        item (str):
        bbox (str): xmin,ymin,xmax,ymax na referência de bboxSR
        bbox_sr (None | str | Unset):
        size (None | str | Unset): largura,altura em pixels
        image_sr (None | str | Unset):
        format_ (str | Unset):  Default: 'png'.
        f (str | Unset):  Default: 'image'.
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        bbox=bbox,
        bbox_sr=bbox_sr,
        size=size,
        image_sr=image_sr,
        format_=format_,
        f=f,
        asset=asset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    bbox_sr: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    image_sr: None | str | Unset = UNSET,
    format_: str | Unset = "png",
    f: str | Unset = "image",
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """recorte por bbox (equivalente ao Export Image)

    Args:
        token (str):
        item (str):
        bbox (str): xmin,ymin,xmax,ymax na referência de bboxSR
        bbox_sr (None | str | Unset):
        size (None | str | Unset): largura,altura em pixels
        image_sr (None | str | Unset):
        format_ (str | Unset):  Default: 'png'.
        f (str | Unset):  Default: 'image'.
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item=item,
        client=client,
        bbox=bbox,
        bbox_sr=bbox_sr,
        size=size,
        image_sr=image_sr,
        format_=format_,
        f=f,
        asset=asset,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    bbox_sr: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    image_sr: None | str | Unset = UNSET,
    format_: str | Unset = "png",
    f: str | Unset = "image",
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """recorte por bbox (equivalente ao Export Image)

    Args:
        token (str):
        item (str):
        bbox (str): xmin,ymin,xmax,ymax na referência de bboxSR
        bbox_sr (None | str | Unset):
        size (None | str | Unset): largura,altura em pixels
        image_sr (None | str | Unset):
        format_ (str | Unset):  Default: 'png'.
        f (str | Unset):  Default: 'image'.
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        bbox=bbox,
        bbox_sr=bbox_sr,
        size=size,
        image_sr=image_sr,
        format_=format_,
        f=f,
        asset=asset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    bbox_sr: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    image_sr: None | str | Unset = UNSET,
    format_: str | Unset = "png",
    f: str | Unset = "image",
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """recorte por bbox (equivalente ao Export Image)

    Args:
        token (str):
        item (str):
        bbox (str): xmin,ymin,xmax,ymax na referência de bboxSR
        bbox_sr (None | str | Unset):
        size (None | str | Unset): largura,altura em pixels
        image_sr (None | str | Unset):
        format_ (str | Unset):  Default: 'png'.
        f (str | Unset):  Default: 'image'.
        asset (None | str | Unset):

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
            client=client,
            bbox=bbox,
            bbox_sr=bbox_sr,
            size=size,
            image_sr=image_sr,
            format_=format_,
            f=f,
            asset=asset,
        )
    ).parsed
