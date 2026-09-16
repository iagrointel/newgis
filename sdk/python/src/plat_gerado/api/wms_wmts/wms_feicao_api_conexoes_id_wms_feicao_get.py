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
    *,
    camada: str,
    coluna: int,
    linha: int,
    largura: int | Unset = 256,
    altura: int | Unset = 256,
    crs: str | Unset = "EPSG:3857",
    bbox: str,
    formato_info: str | Unset = "application/json",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["camada"] = camada

    params["coluna"] = coluna

    params["linha"] = linha

    params["largura"] = largura

    params["altura"] = altura

    params["crs"] = crs

    params["bbox"] = bbox

    params["formato_info"] = formato_info

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/wms/feicao".format(
            id=quote(str(id), safe=""),
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
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    coluna: int,
    linha: int,
    largura: int | Unset = 256,
    altura: int | Unset = 256,
    crs: str | Unset = "EPSG:3857",
    bbox: str,
    formato_info: str | Unset = "application/json",
) -> Response[Any | HTTPValidationError]:
    """Wms Feicao

    Args:
        id (str):
        camada (str):
        coluna (int):
        linha (int):
        largura (int | Unset):  Default: 256.
        altura (int | Unset):  Default: 256.
        crs (str | Unset):  Default: 'EPSG:3857'.
        bbox (str):
        formato_info (str | Unset):  Default: 'application/json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        camada=camada,
        coluna=coluna,
        linha=linha,
        largura=largura,
        altura=altura,
        crs=crs,
        bbox=bbox,
        formato_info=formato_info,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    coluna: int,
    linha: int,
    largura: int | Unset = 256,
    altura: int | Unset = 256,
    crs: str | Unset = "EPSG:3857",
    bbox: str,
    formato_info: str | Unset = "application/json",
) -> Any | HTTPValidationError | None:
    """Wms Feicao

    Args:
        id (str):
        camada (str):
        coluna (int):
        linha (int):
        largura (int | Unset):  Default: 256.
        altura (int | Unset):  Default: 256.
        crs (str | Unset):  Default: 'EPSG:3857'.
        bbox (str):
        formato_info (str | Unset):  Default: 'application/json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        camada=camada,
        coluna=coluna,
        linha=linha,
        largura=largura,
        altura=altura,
        crs=crs,
        bbox=bbox,
        formato_info=formato_info,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    coluna: int,
    linha: int,
    largura: int | Unset = 256,
    altura: int | Unset = 256,
    crs: str | Unset = "EPSG:3857",
    bbox: str,
    formato_info: str | Unset = "application/json",
) -> Response[Any | HTTPValidationError]:
    """Wms Feicao

    Args:
        id (str):
        camada (str):
        coluna (int):
        linha (int):
        largura (int | Unset):  Default: 256.
        altura (int | Unset):  Default: 256.
        crs (str | Unset):  Default: 'EPSG:3857'.
        bbox (str):
        formato_info (str | Unset):  Default: 'application/json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        camada=camada,
        coluna=coluna,
        linha=linha,
        largura=largura,
        altura=altura,
        crs=crs,
        bbox=bbox,
        formato_info=formato_info,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    camada: str,
    coluna: int,
    linha: int,
    largura: int | Unset = 256,
    altura: int | Unset = 256,
    crs: str | Unset = "EPSG:3857",
    bbox: str,
    formato_info: str | Unset = "application/json",
) -> Any | HTTPValidationError | None:
    """Wms Feicao

    Args:
        id (str):
        camada (str):
        coluna (int):
        linha (int):
        largura (int | Unset):  Default: 256.
        altura (int | Unset):  Default: 256.
        crs (str | Unset):  Default: 'EPSG:3857'.
        bbox (str):
        formato_info (str | Unset):  Default: 'application/json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            camada=camada,
            coluna=coluna,
            linha=linha,
            largura=largura,
            altura=altura,
            crs=crs,
            bbox=bbox,
            formato_info=formato_info,
        )
    ).parsed
