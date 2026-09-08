from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.erro import Erro
from ...models.log import Log
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    *,
    apos: int | Unset = 0,
    nivel: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["apos"] = apos

    json_nivel: None | str | Unset
    if isinstance(nivel, Unset):
        json_nivel = UNSET
    else:
        json_nivel = nivel
    params["nivel"] = json_nivel

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/jobs/{job_id}/log".format(
            job_id=quote(str(job_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Erro | Log | None:
    if response.status_code == 200:
        response_200 = Log.from_dict(response.json())

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Erro | Log]:
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
    apos: int | Unset = 0,
    nivel: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[Erro | Log]:
    """Log Do Job

    Args:
        job_id (UUID):
        apos (int | Unset):  Default: 0.
        nivel (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | Log]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        apos=apos,
        nivel=nivel,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    apos: int | Unset = 0,
    nivel: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Erro | Log | None:
    """Log Do Job

    Args:
        job_id (UUID):
        apos (int | Unset):  Default: 0.
        nivel (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | Log
    """

    return sync_detailed(
        job_id=job_id,
        client=client,
        apos=apos,
        nivel=nivel,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    apos: int | Unset = 0,
    nivel: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Response[Erro | Log]:
    """Log Do Job

    Args:
        job_id (UUID):
        apos (int | Unset):  Default: 0.
        nivel (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | Log]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        apos=apos,
        nivel=nivel,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    apos: int | Unset = 0,
    nivel: None | str | Unset = UNSET,
    limite: int | Unset = 500,
) -> Erro | Log | None:
    """Log Do Job

    Args:
        job_id (UUID):
        apos (int | Unset):  Default: 0.
        nivel (None | str | Unset):
        limite (int | Unset):  Default: 500.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | Log
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            client=client,
            apos=apos,
            nivel=nivel,
            limite=limite,
        )
    ).parsed
