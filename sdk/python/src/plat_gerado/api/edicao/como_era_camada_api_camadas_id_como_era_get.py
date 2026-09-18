import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.como_era_camada_api_camadas_id_como_era_get_response_como_era_camada_api_camadas_id_como_era_get import (
    ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    em: datetime.datetime,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_em = em.isoformat()
    params["em"] = json_em

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/como-era".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet.from_dict(
            response.json()
        )

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
) -> Response[ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError]:
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
    em: datetime.datetime,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
) -> Response[ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError]:
    """Como Era Camada

     "Como era a camada em <em>" (equivalente ao historicMoment do FeatureServer, item L2-03-d): estado
    reconstruído DO HISTÓRICO por gatilho — vale para qualquer escrita, não só a da API.

    Args:
        id (str):
        em (datetime.datetime):
        cursor (None | str | Unset):
        limite (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        em=em,
        cursor=cursor,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    em: datetime.datetime,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
) -> ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError | None:
    """Como Era Camada

     "Como era a camada em <em>" (equivalente ao historicMoment do FeatureServer, item L2-03-d): estado
    reconstruído DO HISTÓRICO por gatilho — vale para qualquer escrita, não só a da API.

    Args:
        id (str):
        em (datetime.datetime):
        cursor (None | str | Unset):
        limite (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        em=em,
        cursor=cursor,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    em: datetime.datetime,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
) -> Response[ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError]:
    """Como Era Camada

     "Como era a camada em <em>" (equivalente ao historicMoment do FeatureServer, item L2-03-d): estado
    reconstruído DO HISTÓRICO por gatilho — vale para qualquer escrita, não só a da API.

    Args:
        id (str):
        em (datetime.datetime):
        cursor (None | str | Unset):
        limite (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        em=em,
        cursor=cursor,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    em: datetime.datetime,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
) -> ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError | None:
    """Como Era Camada

     "Como era a camada em <em>" (equivalente ao historicMoment do FeatureServer, item L2-03-d): estado
    reconstruído DO HISTÓRICO por gatilho — vale para qualquer escrita, não só a da API.

    Args:
        id (str):
        em (datetime.datetime):
        cursor (None | str | Unset):
        limite (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ComoEraCamadaApiCamadasIdComoEraGetResponseComoEraCamadaApiCamadasIdComoEraGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            em=em,
            cursor=cursor,
            limite=limite,
        )
    ).parsed
