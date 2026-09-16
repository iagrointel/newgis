from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    lat: float,
    lon: float,
    instante: str,
    intensidade: float | Unset = 0.35,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["lat"] = lat

    params["lon"] = lon

    params["instante"] = instante

    params["intensidade"] = intensidade

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/cena/sol",
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
    *,
    client: AuthenticatedClient | Client,
    lat: float,
    lon: float,
    instante: str,
    intensidade: float | Unset = 0.35,
) -> Response[Any | HTTPValidationError]:
    """Sol

     Posição geométrica do Sol (sem refração) pelo algoritmo do NOAA, e a luz correspondente.

    Args:
        lat (float): latitude em graus, norte positivo
        lon (float): longitude em graus, leste positivo
        instante (str): instante ISO 8601 com fuso (ex.: 2026-06-21T12:00:00-03:00)
        intensidade (float | Unset): intensidade da luz devolvida no bloco do MapLibre Default:
            0.35.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lat=lat,
        lon=lon,
        instante=instante,
        intensidade=intensidade,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    lat: float,
    lon: float,
    instante: str,
    intensidade: float | Unset = 0.35,
) -> Any | HTTPValidationError | None:
    """Sol

     Posição geométrica do Sol (sem refração) pelo algoritmo do NOAA, e a luz correspondente.

    Args:
        lat (float): latitude em graus, norte positivo
        lon (float): longitude em graus, leste positivo
        instante (str): instante ISO 8601 com fuso (ex.: 2026-06-21T12:00:00-03:00)
        intensidade (float | Unset): intensidade da luz devolvida no bloco do MapLibre Default:
            0.35.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        lat=lat,
        lon=lon,
        instante=instante,
        intensidade=intensidade,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    lat: float,
    lon: float,
    instante: str,
    intensidade: float | Unset = 0.35,
) -> Response[Any | HTTPValidationError]:
    """Sol

     Posição geométrica do Sol (sem refração) pelo algoritmo do NOAA, e a luz correspondente.

    Args:
        lat (float): latitude em graus, norte positivo
        lon (float): longitude em graus, leste positivo
        instante (str): instante ISO 8601 com fuso (ex.: 2026-06-21T12:00:00-03:00)
        intensidade (float | Unset): intensidade da luz devolvida no bloco do MapLibre Default:
            0.35.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lat=lat,
        lon=lon,
        instante=instante,
        intensidade=intensidade,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    lat: float,
    lon: float,
    instante: str,
    intensidade: float | Unset = 0.35,
) -> Any | HTTPValidationError | None:
    """Sol

     Posição geométrica do Sol (sem refração) pelo algoritmo do NOAA, e a luz correspondente.

    Args:
        lat (float): latitude em graus, norte positivo
        lon (float): longitude em graus, leste positivo
        instante (str): instante ISO 8601 com fuso (ex.: 2026-06-21T12:00:00-03:00)
        intensidade (float | Unset): intensidade da luz devolvida no bloco do MapLibre Default:
            0.35.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            lat=lat,
            lon=lon,
            instante=instante,
            intensidade=intensidade,
        )
    ).parsed
