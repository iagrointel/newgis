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
    mosaico_id: str,
    *,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["SERVICE"] = service

    params["REQUEST"] = request

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

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/mosaico/{mosaico_id}/wmts".format(
            token=quote(str(token), safe=""),
            mosaico_id=quote(str(mosaico_id), safe=""),
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
    mosaico_id: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """WMTS 1.0.0 KVP do mosaico registrado (GetCapabilities e GetTile)

    Args:
        token (str):
        mosaico_id (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        mosaico_id=mosaico_id,
        service=service,
        request=request,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    mosaico_id: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """WMTS 1.0.0 KVP do mosaico registrado (GetCapabilities e GetTile)

    Args:
        token (str):
        mosaico_id (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        mosaico_id=mosaico_id,
        client=client,
        service=service,
        request=request,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
    ).parsed


async def asyncio_detailed(
    token: str,
    mosaico_id: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """WMTS 1.0.0 KVP do mosaico registrado (GetCapabilities e GetTile)

    Args:
        token (str):
        mosaico_id (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        mosaico_id=mosaico_id,
        service=service,
        request=request,
        tilematrix=tilematrix,
        tilerow=tilerow,
        tilecol=tilecol,
        format_=format_,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    mosaico_id: str,
    *,
    client: AuthenticatedClient | Client,
    service: str | Unset = "WMTS",
    request: str | Unset = "GetCapabilities",
    tilematrix: None | str | Unset = UNSET,
    tilerow: int | None | Unset = UNSET,
    tilecol: int | None | Unset = UNSET,
    format_: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """WMTS 1.0.0 KVP do mosaico registrado (GetCapabilities e GetTile)

    Args:
        token (str):
        mosaico_id (str):
        service (str | Unset):  Default: 'WMTS'.
        request (str | Unset):  Default: 'GetCapabilities'.
        tilematrix (None | str | Unset):
        tilerow (int | None | Unset):
        tilecol (int | None | Unset):
        format_ (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            mosaico_id=mosaico_id,
            client=client,
            service=service,
            request=request,
            tilematrix=tilematrix,
            tilerow=tilerow,
            tilecol=tilecol,
            format_=format_,
        )
    ).parsed
