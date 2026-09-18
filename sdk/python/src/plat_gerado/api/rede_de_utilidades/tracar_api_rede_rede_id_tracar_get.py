from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tracado_area_suja_resultado import TracadoAreaSujaResultado
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    feicao_id: None | str | Unset = UNSET,
    geometria: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_feicao_id: None | str | Unset
    if isinstance(feicao_id, Unset):
        json_feicao_id = UNSET
    else:
        json_feicao_id = feicao_id
    params["feicao_id"] = json_feicao_id

    json_geometria: None | str | Unset
    if isinstance(geometria, Unset):
        json_geometria = UNSET
    else:
        json_geometria = geometria
    params["geometria"] = json_geometria

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/tracar".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TracadoAreaSujaResultado | None:
    if response.status_code == 200:
        response_200 = TracadoAreaSujaResultado.from_dict(response.json())

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
) -> Response[HTTPValidationError | TracadoAreaSujaResultado]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    feicao_id: None | str | Unset = UNSET,
    geometria: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TracadoAreaSujaResultado]:
    """Tracar

     Ponto de partida de um traçado: `feicao_id` (uuid de uma feição já gravada) OU `geometria` (GeoJSON
    de ponto/linha, codificado como string de query). Só lê: não deriva conexão nem grava nada — a
    checagem
    de área suja aqui é a mesma que a rota de rota (`L2-11-c`) chamaria antes de rodar o algoritmo
    pesado.

    Args:
        rede_id (str):
        feicao_id (None | str | Unset):
        geometria (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TracadoAreaSujaResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        feicao_id=feicao_id,
        geometria=geometria,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    feicao_id: None | str | Unset = UNSET,
    geometria: None | str | Unset = UNSET,
) -> HTTPValidationError | TracadoAreaSujaResultado | None:
    """Tracar

     Ponto de partida de um traçado: `feicao_id` (uuid de uma feição já gravada) OU `geometria` (GeoJSON
    de ponto/linha, codificado como string de query). Só lê: não deriva conexão nem grava nada — a
    checagem
    de área suja aqui é a mesma que a rota de rota (`L2-11-c`) chamaria antes de rodar o algoritmo
    pesado.

    Args:
        rede_id (str):
        feicao_id (None | str | Unset):
        geometria (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TracadoAreaSujaResultado
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        feicao_id=feicao_id,
        geometria=geometria,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    feicao_id: None | str | Unset = UNSET,
    geometria: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TracadoAreaSujaResultado]:
    """Tracar

     Ponto de partida de um traçado: `feicao_id` (uuid de uma feição já gravada) OU `geometria` (GeoJSON
    de ponto/linha, codificado como string de query). Só lê: não deriva conexão nem grava nada — a
    checagem
    de área suja aqui é a mesma que a rota de rota (`L2-11-c`) chamaria antes de rodar o algoritmo
    pesado.

    Args:
        rede_id (str):
        feicao_id (None | str | Unset):
        geometria (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TracadoAreaSujaResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        feicao_id=feicao_id,
        geometria=geometria,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    feicao_id: None | str | Unset = UNSET,
    geometria: None | str | Unset = UNSET,
) -> HTTPValidationError | TracadoAreaSujaResultado | None:
    """Tracar

     Ponto de partida de um traçado: `feicao_id` (uuid de uma feição já gravada) OU `geometria` (GeoJSON
    de ponto/linha, codificado como string de query). Só lê: não deriva conexão nem grava nada — a
    checagem
    de área suja aqui é a mesma que a rota de rota (`L2-11-c`) chamaria antes de rodar o algoritmo
    pesado.

    Args:
        rede_id (str):
        feicao_id (None | str | Unset):
        geometria (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TracadoAreaSujaResultado
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            feicao_id=feicao_id,
            geometria=geometria,
        )
    ).parsed
