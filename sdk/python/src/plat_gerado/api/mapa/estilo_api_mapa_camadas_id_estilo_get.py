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
    formato: str | Unset = "maplibre",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/mapa/camadas/{id}/estilo".format(
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
    formato: str | Unset = "maplibre",
) -> Response[Any | HTTPValidationError]:
    """Estilo

     `maplibre` devolve as camadas de estilo da Style Spec; `sld` devolve SLD 1.0.0 (mesmas classes).

    Args:
        id (str):
        formato (str | Unset):  Default: 'maplibre'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "maplibre",
) -> Any | HTTPValidationError | None:
    """Estilo

     `maplibre` devolve as camadas de estilo da Style Spec; `sld` devolve SLD 1.0.0 (mesmas classes).

    Args:
        id (str):
        formato (str | Unset):  Default: 'maplibre'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "maplibre",
) -> Response[Any | HTTPValidationError]:
    """Estilo

     `maplibre` devolve as camadas de estilo da Style Spec; `sld` devolve SLD 1.0.0 (mesmas classes).

    Args:
        id (str):
        formato (str | Unset):  Default: 'maplibre'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: str | Unset = "maplibre",
) -> Any | HTTPValidationError | None:
    """Estilo

     `maplibre` devolve as camadas de estilo da Style Spec; `sld` devolve SLD 1.0.0 (mesmas classes).

    Args:
        id (str):
        formato (str | Unset):  Default: 'maplibre'.

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
            formato=formato,
        )
    ).parsed
