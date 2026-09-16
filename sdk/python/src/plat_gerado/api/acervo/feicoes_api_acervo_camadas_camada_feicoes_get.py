from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_feicoes import AcervoFeicoes
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    camada: str,
    *,
    bbox: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/camadas/{camada}/feicoes".format(
            camada=quote(str(camada), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoFeicoes | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoFeicoes.from_dict(response.json())

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
) -> Response[AcervoFeicoes | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[AcervoFeicoes | HTTPValidationError]:
    """Feicoes

    Args:
        camada (str):
        bbox (None | str | Unset): oeste,sul,leste,norte em graus (EPSG:4326)
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoFeicoes | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        bbox=bbox,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> AcervoFeicoes | HTTPValidationError | None:
    """Feicoes

    Args:
        camada (str):
        bbox (None | str | Unset): oeste,sul,leste,norte em graus (EPSG:4326)
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoFeicoes | HTTPValidationError
    """

    return sync_detailed(
        camada=camada,
        client=client,
        bbox=bbox,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[AcervoFeicoes | HTTPValidationError]:
    """Feicoes

    Args:
        camada (str):
        bbox (None | str | Unset): oeste,sul,leste,norte em graus (EPSG:4326)
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoFeicoes | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        bbox=bbox,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> AcervoFeicoes | HTTPValidationError | None:
    """Feicoes

    Args:
        camada (str):
        bbox (None | str | Unset): oeste,sul,leste,norte em graus (EPSG:4326)
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoFeicoes | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            camada=camada,
            client=client,
            bbox=bbox,
            limite=limite,
        )
    ).parsed
