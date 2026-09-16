from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.campos_da_camada_api_camadas_id_campos_get_response_campos_da_camada_api_camadas_id_campos_get import (
    CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/campos".format(
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet.from_dict(
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
) -> Response[CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError]:
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
) -> Response[CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError]:
    """Campos Da Camada

     Paleta do construtor: atributos reais da camada (nome/tipo/alias) — o campo do desenho tem de
    casar com um destes, ou ser declarado `persistido: false` (portão cláusula 2).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError | None:
    """Campos Da Camada

     Paleta do construtor: atributos reais da camada (nome/tipo/alias) — o campo do desenho tem de
    casar com um destes, ou ser declarado `persistido: false` (portão cláusula 2).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError]:
    """Campos Da Camada

     Paleta do construtor: atributos reais da camada (nome/tipo/alias) — o campo do desenho tem de
    casar com um destes, ou ser declarado `persistido: false` (portão cláusula 2).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError | None:
    """Campos Da Camada

     Paleta do construtor: atributos reais da camada (nome/tipo/alias) — o campo do desenho tem de
    casar com um destes, ou ser declarado `persistido: false` (portão cláusula 2).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamposDaCamadaApiCamadasIdCamposGetResponseCamposDaCamadaApiCamadasIdCamposGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
        )
    ).parsed
