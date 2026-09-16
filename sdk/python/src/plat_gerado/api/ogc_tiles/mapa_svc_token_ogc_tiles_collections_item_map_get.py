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
    bbox: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    width: int | Unset = 800,
    height: int | Unset = 600,
    f: str | Unset = "png",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_crs: None | str | Unset
    if isinstance(crs, Unset):
        json_crs = UNSET
    else:
        json_crs = crs
    params["crs"] = json_crs

    params["width"] = width

    params["height"] = height

    params["f"] = f

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/ogc/tiles/collections/{item}/map".format(
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
    bbox: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    width: int | Unset = 800,
    height: int | Unset = 600,
    f: str | Unset = "png",
) -> Response[Any | HTTPValidationError]:
    """OGC API Maps — recorte por bbox/crs/width/height (a irmã do GetMap do WMS)

    Args:
        token (str):
        item (str):
        bbox (None | str | Unset): minx,miny,maxx,maxy no CRS do parâmetro crs
        crs (None | str | Unset): CRS do bbox e da imagem de saída (mesmo uso do CRS do WMS
            GetMap)
        width (int | Unset):  Default: 800.
        height (int | Unset):  Default: 600.
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
        bbox=bbox,
        crs=crs,
        width=width,
        height=height,
        f=f,
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
    bbox: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    width: int | Unset = 800,
    height: int | Unset = 600,
    f: str | Unset = "png",
) -> Any | HTTPValidationError | None:
    """OGC API Maps — recorte por bbox/crs/width/height (a irmã do GetMap do WMS)

    Args:
        token (str):
        item (str):
        bbox (None | str | Unset): minx,miny,maxx,maxy no CRS do parâmetro crs
        crs (None | str | Unset): CRS do bbox e da imagem de saída (mesmo uso do CRS do WMS
            GetMap)
        width (int | Unset):  Default: 800.
        height (int | Unset):  Default: 600.
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
        client=client,
        bbox=bbox,
        crs=crs,
        width=width,
        height=height,
        f=f,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    width: int | Unset = 800,
    height: int | Unset = 600,
    f: str | Unset = "png",
) -> Response[Any | HTTPValidationError]:
    """OGC API Maps — recorte por bbox/crs/width/height (a irmã do GetMap do WMS)

    Args:
        token (str):
        item (str):
        bbox (None | str | Unset): minx,miny,maxx,maxy no CRS do parâmetro crs
        crs (None | str | Unset): CRS do bbox e da imagem de saída (mesmo uso do CRS do WMS
            GetMap)
        width (int | Unset):  Default: 800.
        height (int | Unset):  Default: 600.
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
        bbox=bbox,
        crs=crs,
        width=width,
        height=height,
        f=f,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    crs: None | str | Unset = UNSET,
    width: int | Unset = 800,
    height: int | Unset = 600,
    f: str | Unset = "png",
) -> Any | HTTPValidationError | None:
    """OGC API Maps — recorte por bbox/crs/width/height (a irmã do GetMap do WMS)

    Args:
        token (str):
        item (str):
        bbox (None | str | Unset): minx,miny,maxx,maxy no CRS do parâmetro crs
        crs (None | str | Unset): CRS do bbox e da imagem de saída (mesmo uso do CRS do WMS
            GetMap)
        width (int | Unset):  Default: 800.
        height (int | Unset):  Default: 600.
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
            client=client,
            bbox=bbox,
            crs=crs,
            width=width,
            height=height,
            f=f,
        )
    ).parsed
