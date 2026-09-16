from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.listar_visitas_api_campo_visitas_get_response_listar_visitas_api_campo_visitas_get import (
    ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    fila_id: None | str | Unset = UNSET,
    alvo_id: None | str | Unset = UNSET,
    roteiro_id: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_fila_id: None | str | Unset
    if isinstance(fila_id, Unset):
        json_fila_id = UNSET
    else:
        json_fila_id = fila_id
    params["fila_id"] = json_fila_id

    json_alvo_id: None | str | Unset
    if isinstance(alvo_id, Unset):
        json_alvo_id = UNSET
    else:
        json_alvo_id = alvo_id
    params["alvo_id"] = json_alvo_id

    json_roteiro_id: None | str | Unset
    if isinstance(roteiro_id, Unset):
        json_roteiro_id = UNSET
    else:
        json_roteiro_id = roteiro_id
    params["roteiro_id"] = json_roteiro_id

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/campo/visitas",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet | None:
    if response.status_code == 200:
        response_200 = ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet.from_dict(response.json())

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
) -> Response[HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
    alvo_id: None | str | Unset = UNSET,
    roteiro_id: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet]:
    """Listar Visitas

    Args:
        fila_id (None | str | Unset):
        alvo_id (None | str | Unset):
        roteiro_id (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet]
    """

    kwargs = _get_kwargs(
        fila_id=fila_id,
        alvo_id=alvo_id,
        roteiro_id=roteiro_id,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
    alvo_id: None | str | Unset = UNSET,
    roteiro_id: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet | None:
    """Listar Visitas

    Args:
        fila_id (None | str | Unset):
        alvo_id (None | str | Unset):
        roteiro_id (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet
    """

    return sync_detailed(
        client=client,
        fila_id=fila_id,
        alvo_id=alvo_id,
        roteiro_id=roteiro_id,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
    alvo_id: None | str | Unset = UNSET,
    roteiro_id: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet]:
    """Listar Visitas

    Args:
        fila_id (None | str | Unset):
        alvo_id (None | str | Unset):
        roteiro_id (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet]
    """

    kwargs = _get_kwargs(
        fila_id=fila_id,
        alvo_id=alvo_id,
        roteiro_id=roteiro_id,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    fila_id: None | str | Unset = UNSET,
    alvo_id: None | str | Unset = UNSET,
    roteiro_id: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet | None:
    """Listar Visitas

    Args:
        fila_id (None | str | Unset):
        alvo_id (None | str | Unset):
        roteiro_id (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarVisitasApiCampoVisitasGetResponseListarVisitasApiCampoVisitasGet
    """

    return (
        await asyncio_detailed(
            client=client,
            fila_id=fila_id,
            alvo_id=alvo_id,
            roteiro_id=roteiro_id,
            limite=limite,
        )
    ).parsed
