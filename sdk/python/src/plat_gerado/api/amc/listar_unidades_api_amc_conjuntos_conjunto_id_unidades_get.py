from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    conjunto_id: str,
    *,
    limite: int | Unset = 1000,
    deslocamento: int | Unset = 0,
    geometria: bool | Unset = True,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params["geometria"] = geometria

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/amc/conjuntos/{conjunto_id}/unidades".format(
            conjunto_id=quote(str(conjunto_id), safe=""),
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
    conjunto_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 1000,
    deslocamento: int | Unset = 0,
    geometria: bool | Unset = True,
) -> Response[Any | HTTPValidationError]:
    """Listar Unidades

     FeatureCollection paginada (ou só os ids e áreas com geometria=false).

    Args:
        conjunto_id (str):
        limite (int | Unset):  Default: 1000.
        deslocamento (int | Unset):  Default: 0.
        geometria (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        conjunto_id=conjunto_id,
        limite=limite,
        deslocamento=deslocamento,
        geometria=geometria,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    conjunto_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 1000,
    deslocamento: int | Unset = 0,
    geometria: bool | Unset = True,
) -> Any | HTTPValidationError | None:
    """Listar Unidades

     FeatureCollection paginada (ou só os ids e áreas com geometria=false).

    Args:
        conjunto_id (str):
        limite (int | Unset):  Default: 1000.
        deslocamento (int | Unset):  Default: 0.
        geometria (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        conjunto_id=conjunto_id,
        client=client,
        limite=limite,
        deslocamento=deslocamento,
        geometria=geometria,
    ).parsed


async def asyncio_detailed(
    conjunto_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 1000,
    deslocamento: int | Unset = 0,
    geometria: bool | Unset = True,
) -> Response[Any | HTTPValidationError]:
    """Listar Unidades

     FeatureCollection paginada (ou só os ids e áreas com geometria=false).

    Args:
        conjunto_id (str):
        limite (int | Unset):  Default: 1000.
        deslocamento (int | Unset):  Default: 0.
        geometria (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        conjunto_id=conjunto_id,
        limite=limite,
        deslocamento=deslocamento,
        geometria=geometria,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    conjunto_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 1000,
    deslocamento: int | Unset = 0,
    geometria: bool | Unset = True,
) -> Any | HTTPValidationError | None:
    """Listar Unidades

     FeatureCollection paginada (ou só os ids e áreas com geometria=false).

    Args:
        conjunto_id (str):
        limite (int | Unset):  Default: 1000.
        deslocamento (int | Unset):  Default: 0.
        geometria (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            conjunto_id=conjunto_id,
            client=client,
            limite=limite,
            deslocamento=deslocamento,
            geometria=geometria,
        )
    ).parsed
