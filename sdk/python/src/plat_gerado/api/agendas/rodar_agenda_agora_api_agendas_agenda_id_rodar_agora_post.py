from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.erro import Erro
from ...models.job import Job
from ...types import Response


def _get_kwargs(
    agenda_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/agendas/{agenda_id}/rodar-agora".format(
            agenda_id=quote(str(agenda_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Erro | Job | None:
    if response.status_code == 201:
        response_201 = Job.from_dict(response.json())

        return response_201

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Erro | Job]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    agenda_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Erro | Job]:
    """Rodar Agenda Agora

    Args:
        agenda_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | Job]
    """

    kwargs = _get_kwargs(
        agenda_id=agenda_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    agenda_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Erro | Job | None:
    """Rodar Agenda Agora

    Args:
        agenda_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | Job
    """

    return sync_detailed(
        agenda_id=agenda_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    agenda_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Erro | Job]:
    """Rodar Agenda Agora

    Args:
        agenda_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | Job]
    """

    kwargs = _get_kwargs(
        agenda_id=agenda_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    agenda_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Erro | Job | None:
    """Rodar Agenda Agora

    Args:
        agenda_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | Job
    """

    return (
        await asyncio_detailed(
            agenda_id=agenda_id,
            client=client,
        )
    ).parsed
