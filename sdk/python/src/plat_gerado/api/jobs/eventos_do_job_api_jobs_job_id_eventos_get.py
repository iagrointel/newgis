from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.erro import Erro
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    *,
    desde: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_desde: int | None | Unset
    if isinstance(desde, Unset):
        json_desde = UNSET
    else:
        json_desde = desde
    params["desde"] = json_desde

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/jobs/{job_id}/eventos".format(
            job_id=quote(str(job_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | Erro | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 401:
        response_401 = Erro.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Erro.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Erro.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Erro.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = Erro.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Erro.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Erro.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | Erro]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    desde: int | None | Unset = UNSET,
) -> Response[Any | Erro]:
    """Eventos Do Job

     SSE: primeiro evento `estado`, depois `log`/`estado`, `fim` no estado final; Last-Event-ID reenvia o
    log.
    `desde` é o mesmo valor por query (fallback do `Last-Event-ID`, que o EventSource nativo do
    navegador não
    consegue mandar numa reconexão aberta à mão pelo cliente — só no retry automático do próprio
    navegador,
    que o front não usa depois do `fim` de conexão forçado aos 30 min; ver web/js/jobs/eventos.js).

    Args:
        job_id (UUID):
        desde (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Erro]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        desde=desde,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    desde: int | None | Unset = UNSET,
) -> Any | Erro | None:
    """Eventos Do Job

     SSE: primeiro evento `estado`, depois `log`/`estado`, `fim` no estado final; Last-Event-ID reenvia o
    log.
    `desde` é o mesmo valor por query (fallback do `Last-Event-ID`, que o EventSource nativo do
    navegador não
    consegue mandar numa reconexão aberta à mão pelo cliente — só no retry automático do próprio
    navegador,
    que o front não usa depois do `fim` de conexão forçado aos 30 min; ver web/js/jobs/eventos.js).

    Args:
        job_id (UUID):
        desde (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Erro
    """

    return sync_detailed(
        job_id=job_id,
        client=client,
        desde=desde,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    desde: int | None | Unset = UNSET,
) -> Response[Any | Erro]:
    """Eventos Do Job

     SSE: primeiro evento `estado`, depois `log`/`estado`, `fim` no estado final; Last-Event-ID reenvia o
    log.
    `desde` é o mesmo valor por query (fallback do `Last-Event-ID`, que o EventSource nativo do
    navegador não
    consegue mandar numa reconexão aberta à mão pelo cliente — só no retry automático do próprio
    navegador,
    que o front não usa depois do `fim` de conexão forçado aos 30 min; ver web/js/jobs/eventos.js).

    Args:
        job_id (UUID):
        desde (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Erro]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        desde=desde,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    desde: int | None | Unset = UNSET,
) -> Any | Erro | None:
    """Eventos Do Job

     SSE: primeiro evento `estado`, depois `log`/`estado`, `fim` no estado final; Last-Event-ID reenvia o
    log.
    `desde` é o mesmo valor por query (fallback do `Last-Event-ID`, que o EventSource nativo do
    navegador não
    consegue mandar numa reconexão aberta à mão pelo cliente — só no retry automático do próprio
    navegador,
    que o front não usa depois do `fim` de conexão forçado aos 30 min; ver web/js/jobs/eventos.js).

    Args:
        job_id (UUID):
        desde (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Erro
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            client=client,
            desde=desde,
        )
    ).parsed
