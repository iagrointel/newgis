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
    bbox: str,
    largura: int | Unset = 512,
    altura: int | Unset = 512,
    out_sr: int | Unset = 4326,
    formato: str | Unset = "png32",
    camadas: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["bbox"] = bbox

    params["largura"] = largura

    params["altura"] = altura

    params["outSR"] = out_sr

    params["formato"] = formato

    json_camadas: None | str | Unset
    if isinstance(camadas, Unset):
        json_camadas = UNSET
    else:
        json_camadas = camadas
    params["camadas"] = json_camadas

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/esri/mapa".format(
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
    bbox: str,
    largura: int | Unset = 512,
    altura: int | Unset = 512,
    out_sr: int | Unset = 4326,
    formato: str | Unset = "png32",
    camadas: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Mapa

     MapServer `/export`: imagem dinâmica renderizada pelo servidor, no modo referenciado (proxy — o
    navegador nunca vê a URL original nem a credencial).

    Args:
        id (str):
        bbox (str):
        largura (int | Unset):  Default: 512.
        altura (int | Unset):  Default: 512.
        out_sr (int | Unset):  Default: 4326.
        formato (str | Unset):  Default: 'png32'.
        camadas (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        bbox=bbox,
        largura=largura,
        altura=altura,
        out_sr=out_sr,
        formato=formato,
        camadas=camadas,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    largura: int | Unset = 512,
    altura: int | Unset = 512,
    out_sr: int | Unset = 4326,
    formato: str | Unset = "png32",
    camadas: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Mapa

     MapServer `/export`: imagem dinâmica renderizada pelo servidor, no modo referenciado (proxy — o
    navegador nunca vê a URL original nem a credencial).

    Args:
        id (str):
        bbox (str):
        largura (int | Unset):  Default: 512.
        altura (int | Unset):  Default: 512.
        out_sr (int | Unset):  Default: 4326.
        formato (str | Unset):  Default: 'png32'.
        camadas (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        bbox=bbox,
        largura=largura,
        altura=altura,
        out_sr=out_sr,
        formato=formato,
        camadas=camadas,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    largura: int | Unset = 512,
    altura: int | Unset = 512,
    out_sr: int | Unset = 4326,
    formato: str | Unset = "png32",
    camadas: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Mapa

     MapServer `/export`: imagem dinâmica renderizada pelo servidor, no modo referenciado (proxy — o
    navegador nunca vê a URL original nem a credencial).

    Args:
        id (str):
        bbox (str):
        largura (int | Unset):  Default: 512.
        altura (int | Unset):  Default: 512.
        out_sr (int | Unset):  Default: 4326.
        formato (str | Unset):  Default: 'png32'.
        camadas (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        bbox=bbox,
        largura=largura,
        altura=altura,
        out_sr=out_sr,
        formato=formato,
        camadas=camadas,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: str,
    largura: int | Unset = 512,
    altura: int | Unset = 512,
    out_sr: int | Unset = 4326,
    formato: str | Unset = "png32",
    camadas: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Mapa

     MapServer `/export`: imagem dinâmica renderizada pelo servidor, no modo referenciado (proxy — o
    navegador nunca vê a URL original nem a credencial).

    Args:
        id (str):
        bbox (str):
        largura (int | Unset):  Default: 512.
        altura (int | Unset):  Default: 512.
        out_sr (int | Unset):  Default: 4326.
        formato (str | Unset):  Default: 'png32'.
        camadas (None | str | Unset):

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
            bbox=bbox,
            largura=largura,
            altura=altura,
            out_sr=out_sr,
            formato=formato,
            camadas=camadas,
        )
    ).parsed
