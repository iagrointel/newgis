from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.camada_globalids_api_campo_camadas_camada_id_globalids_get_response_camada_globalids_api_campo_camadas_camada_id_globalids_get import (
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    camada_id: str,
    *,
    limite: int | Unset = 200,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/campo/camadas/{camada_id}/globalids".format(
            camada_id=quote(str(camada_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet.from_dict(
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
) -> Response[
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    camada_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 200,
) -> Response[
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
]:
    """Camada Globalids

     Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo.

    Args:
        camada_id (str):
        limite (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada_id=camada_id,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    camada_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 200,
) -> (
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
    | None
):
    """Camada Globalids

     Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo.

    Args:
        camada_id (str):
        limite (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet | HTTPValidationError
    """

    return sync_detailed(
        camada_id=camada_id,
        client=client,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    camada_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 200,
) -> Response[
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
]:
    """Camada Globalids

     Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo.

    Args:
        camada_id (str):
        limite (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada_id=camada_id,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    camada_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 200,
) -> (
    CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet
    | HTTPValidationError
    | None
):
    """Camada Globalids

     Lista curta de feições da camada (globalid + rótulo) para a tela de criação de fila escolher os
    alvos sem precisar de um visualizador de mapa completo.

    Args:
        camada_id (str):
        limite (int | Unset):  Default: 200.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGetResponseCamadaGlobalidsApiCampoCamadasCamadaIdGlobalidsGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            camada_id=camada_id,
            client=client,
            limite=limite,
        )
    ).parsed
