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
    fid: int,
    *,
    formato: str | Unset = "geojson",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/mapa/camadas/{id}/feicoes/{fid}".format(
            id=quote(str(id), safe=""),
            fid=quote(str(fid), safe=""),
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
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "geojson",
) -> Response[Any | HTTPValidationError]:
    """Copiar Feicao

     A feição inteira (geometria da TABELA, não do tile) como texto para a área de transferência.

    Args:
        id (str):
        fid (int):
        formato (str | Unset):  Default: 'geojson'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        fid=fid,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "geojson",
) -> Any | HTTPValidationError | None:
    """Copiar Feicao

     A feição inteira (geometria da TABELA, não do tile) como texto para a área de transferência.

    Args:
        id (str):
        fid (int):
        formato (str | Unset):  Default: 'geojson'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        fid=fid,
        client=client,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "geojson",
) -> Response[Any | HTTPValidationError]:
    """Copiar Feicao

     A feição inteira (geometria da TABELA, não do tile) como texto para a área de transferência.

    Args:
        id (str):
        fid (int):
        formato (str | Unset):  Default: 'geojson'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        fid=fid,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "geojson",
) -> Any | HTTPValidationError | None:
    """Copiar Feicao

     A feição inteira (geometria da TABELA, não do tile) como texto para a área de transferência.

    Args:
        id (str):
        fid (int):
        formato (str | Unset):  Default: 'geojson'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            fid=fid,
            client=client,
            formato=formato,
        )
    ).parsed
