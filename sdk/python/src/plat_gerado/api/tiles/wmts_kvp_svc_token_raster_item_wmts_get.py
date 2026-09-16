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
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    version: str | Unset = "1.0.0",
    layer: None | str | Unset = UNSET,
    tilematrixset: None | str | Unset = UNSET,
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
    style: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    bandas: None | str | Unset = UNSET,
    faixa: None | str | Unset = UNSET,
    colormap: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
    predef: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["SERVICE"] = service

    params["REQUEST"] = request

    params["VERSION"] = version

    json_layer: None | str | Unset
    if isinstance(layer, Unset):
        json_layer = UNSET
    else:
        json_layer = layer
    params["LAYER"] = json_layer

    json_tilematrixset: None | str | Unset
    if isinstance(tilematrixset, Unset):
        json_tilematrixset = UNSET
    else:
        json_tilematrixset = tilematrixset
    params["TILEMATRIXSET"] = json_tilematrixset

    json_tilematrix: None | str | Unset
    if isinstance(tilematrix, Unset):
        json_tilematrix = UNSET
    else:
        json_tilematrix = tilematrix
    params["TILEMATRIX"] = json_tilematrix

    json_tilerow: int | None | Unset
    if isinstance(tilerow, Unset):
        json_tilerow = UNSET
    else:
        json_tilerow = tilerow
    params["TILEROW"] = json_tilerow

    json_tilecol: int | None | Unset
    if isinstance(tilecol, Unset):
        json_tilecol = UNSET
    else:
        json_tilecol = tilecol
    params["TILECOL"] = json_tilecol

    json_format_: None | str | Unset
    if isinstance(format_, Unset):
        json_format_ = UNSET
    else:
        json_format_ = format_
    params["FORMAT"] = json_format_

    json_style: None | str | Unset
    if isinstance(style, Unset):
        json_style = UNSET
    else:
        json_style = style
    params["STYLE"] = json_style

    json_expressao: None | str | Unset
    if isinstance(expressao, Unset):
        json_expressao = UNSET
    else:
        json_expressao = expressao
    params["expressao"] = json_expressao

    json_bandas: None | str | Unset
    if isinstance(bandas, Unset):
        json_bandas = UNSET
    else:
        json_bandas = bandas
    params["bandas"] = json_bandas

    json_faixa: None | str | Unset
    if isinstance(faixa, Unset):
        json_faixa = UNSET
    else:
        json_faixa = faixa
    params["faixa"] = json_faixa

    json_colormap: None | str | Unset
    if isinstance(colormap, Unset):
        json_colormap = UNSET
    else:
        json_colormap = colormap
    params["colormap"] = json_colormap

    json_asset: None | str | Unset
    if isinstance(asset, Unset):
        json_asset = UNSET
    else:
        json_asset = asset
    params["asset"] = json_asset

    json_predef: None | str | Unset
    if isinstance(predef, Unset):
        json_predef = UNSET
    else:
        json_predef = predef
    params["predef"] = json_predef

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/raster/{item}/wmts".format(
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
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    version: str | Unset = "1.0.0",
    layer: None | str | Unset = UNSET,
    tilematrixset: None | str | Unset = UNSET,
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
    style: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    bandas: None | str | Unset = UNSET,
    faixa: None | str | Unset = UNSET,
    colormap: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
    predef: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """WMTS 1.0.0 KVP (GetCapabilities e GetTile)

    Args:
        token (str):
        item (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        version (str | Unset):  Default: '1.0.0'.
        layer (None | str | Unset):
        tilematrixset (None | str | Unset):
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):
        style (None | str | Unset):
        expressao (None | str | Unset):
        bandas (None | str | Unset):
        faixa (None | str | Unset):
        colormap (None | str | Unset):
        asset (None | str | Unset):
        predef (None | str | Unset): nome de predefinição de renderização (item L1-02-f)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        service=service,
        request=request,
        version=version,
        layer=layer,
        tilematrixset=tilematrixset,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
        style=style,
        expressao=expressao,
        bandas=bandas,
        faixa=faixa,
        colormap=colormap,
        asset=asset,
        predef=predef,
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
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    version: str | Unset = "1.0.0",
    layer: None | str | Unset = UNSET,
    tilematrixset: None | str | Unset = UNSET,
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
    style: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    bandas: None | str | Unset = UNSET,
    faixa: None | str | Unset = UNSET,
    colormap: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
    predef: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """WMTS 1.0.0 KVP (GetCapabilities e GetTile)

    Args:
        token (str):
        item (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        version (str | Unset):  Default: '1.0.0'.
        layer (None | str | Unset):
        tilematrixset (None | str | Unset):
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):
        style (None | str | Unset):
        expressao (None | str | Unset):
        bandas (None | str | Unset):
        faixa (None | str | Unset):
        colormap (None | str | Unset):
        asset (None | str | Unset):
        predef (None | str | Unset): nome de predefinição de renderização (item L1-02-f)

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
        service=service,
        request=request,
        version=version,
        layer=layer,
        tilematrixset=tilematrixset,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
        style=style,
        expressao=expressao,
        bandas=bandas,
        faixa=faixa,
        colormap=colormap,
        asset=asset,
        predef=predef,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    version: str | Unset = "1.0.0",
    layer: None | str | Unset = UNSET,
    tilematrixset: None | str | Unset = UNSET,
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
    style: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    bandas: None | str | Unset = UNSET,
    faixa: None | str | Unset = UNSET,
    colormap: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
    predef: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """WMTS 1.0.0 KVP (GetCapabilities e GetTile)

    Args:
        token (str):
        item (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        version (str | Unset):  Default: '1.0.0'.
        layer (None | str | Unset):
        tilematrixset (None | str | Unset):
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):
        style (None | str | Unset):
        expressao (None | str | Unset):
        bandas (None | str | Unset):
        faixa (None | str | Unset):
        colormap (None | str | Unset):
        asset (None | str | Unset):
        predef (None | str | Unset): nome de predefinição de renderização (item L1-02-f)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        service=service,
        request=request,
        version=version,
        layer=layer,
        tilematrixset=tilematrixset,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
        style=style,
        expressao=expressao,
        bandas=bandas,
        faixa=faixa,
        colormap=colormap,
        asset=asset,
        predef=predef,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    version: str | Unset = "1.0.0",
    layer: None | str | Unset = UNSET,
    tilematrixset: None | str | Unset = UNSET,
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
    style: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    bandas: None | str | Unset = UNSET,
    faixa: None | str | Unset = UNSET,
    colormap: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
    predef: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """WMTS 1.0.0 KVP (GetCapabilities e GetTile)

    Args:
        token (str):
        item (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        version (str | Unset):  Default: '1.0.0'.
        layer (None | str | Unset):
        tilematrixset (None | str | Unset):
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):
        style (None | str | Unset):
        expressao (None | str | Unset):
        bandas (None | str | Unset):
        faixa (None | str | Unset):
        colormap (None | str | Unset):
        asset (None | str | Unset):
        predef (None | str | Unset): nome de predefinição de renderização (item L1-02-f)

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
            service=service,
            request=request,
            version=version,
            layer=layer,
            tilematrixset=tilematrixset,
            tilematrix=tilematrix,
            tilerow=tilerow,
            tilecol=tilecol,
            format_=format_,
            style=style,
            expressao=expressao,
            bandas=bandas,
            faixa=faixa,
            colormap=colormap,
            asset=asset,
            predef=predef,
        )
    ).parsed
