from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.erro import Erro
from ...models.lista_jobs import ListaJobs
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    estado: None | str | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    usuario_id: int | None | Unset = UNSET,
    de: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    agenda_id: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
    ordenar: str | Unset = "criado_em:desc",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_estado: None | str | Unset
    if isinstance(estado, Unset):
        json_estado = UNSET
    else:
        json_estado = estado
    params["estado"] = json_estado

    json_tipo: None | str | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    json_usuario_id: int | None | Unset
    if isinstance(usuario_id, Unset):
        json_usuario_id = UNSET
    else:
        json_usuario_id = usuario_id
    params["usuario_id"] = json_usuario_id

    json_de: None | str | Unset
    if isinstance(de, Unset):
        json_de = UNSET
    else:
        json_de = de
    params["de"] = json_de

    json_ate: None | str | Unset
    if isinstance(ate, Unset):
        json_ate = UNSET
    else:
        json_ate = ate
    params["ate"] = json_ate

    json_agenda_id: None | str | Unset
    if isinstance(agenda_id, Unset):
        json_agenda_id = UNSET
    else:
        json_agenda_id = agenda_id
    params["agenda_id"] = json_agenda_id

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params["ordenar"] = ordenar

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/jobs",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Erro | ListaJobs | None:
    if response.status_code == 200:
        response_200 = ListaJobs.from_dict(response.json())

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Erro | ListaJobs]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    usuario_id: int | None | Unset = UNSET,
    de: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    agenda_id: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
    ordenar: str | Unset = "criado_em:desc",
) -> Response[Erro | ListaJobs]:
    """Listar Jobs

    Args:
        estado (None | str | Unset):
        tipo (None | str | Unset):
        usuario_id (int | None | Unset):
        de (None | str | Unset):
        ate (None | str | Unset):
        agenda_id (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.
        ordenar (str | Unset):  Default: 'criado_em:desc'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | ListaJobs]
    """

    kwargs = _get_kwargs(
        estado=estado,
        tipo=tipo,
        usuario_id=usuario_id,
        de=de,
        ate=ate,
        agenda_id=agenda_id,
        limite=limite,
        deslocamento=deslocamento,
        ordenar=ordenar,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    usuario_id: int | None | Unset = UNSET,
    de: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    agenda_id: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
    ordenar: str | Unset = "criado_em:desc",
) -> Erro | ListaJobs | None:
    """Listar Jobs

    Args:
        estado (None | str | Unset):
        tipo (None | str | Unset):
        usuario_id (int | None | Unset):
        de (None | str | Unset):
        ate (None | str | Unset):
        agenda_id (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.
        ordenar (str | Unset):  Default: 'criado_em:desc'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | ListaJobs
    """

    return sync_detailed(
        client=client,
        estado=estado,
        tipo=tipo,
        usuario_id=usuario_id,
        de=de,
        ate=ate,
        agenda_id=agenda_id,
        limite=limite,
        deslocamento=deslocamento,
        ordenar=ordenar,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    usuario_id: int | None | Unset = UNSET,
    de: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    agenda_id: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
    ordenar: str | Unset = "criado_em:desc",
) -> Response[Erro | ListaJobs]:
    """Listar Jobs

    Args:
        estado (None | str | Unset):
        tipo (None | str | Unset):
        usuario_id (int | None | Unset):
        de (None | str | Unset):
        ate (None | str | Unset):
        agenda_id (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.
        ordenar (str | Unset):  Default: 'criado_em:desc'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Erro | ListaJobs]
    """

    kwargs = _get_kwargs(
        estado=estado,
        tipo=tipo,
        usuario_id=usuario_id,
        de=de,
        ate=ate,
        agenda_id=agenda_id,
        limite=limite,
        deslocamento=deslocamento,
        ordenar=ordenar,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    estado: None | str | Unset = UNSET,
    tipo: None | str | Unset = UNSET,
    usuario_id: int | None | Unset = UNSET,
    de: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    agenda_id: None | str | Unset = UNSET,
    limite: int | Unset = 50,
    deslocamento: int | Unset = 0,
    ordenar: str | Unset = "criado_em:desc",
) -> Erro | ListaJobs | None:
    """Listar Jobs

    Args:
        estado (None | str | Unset):
        tipo (None | str | Unset):
        usuario_id (int | None | Unset):
        de (None | str | Unset):
        ate (None | str | Unset):
        agenda_id (None | str | Unset):
        limite (int | Unset):  Default: 50.
        deslocamento (int | Unset):  Default: 0.
        ordenar (str | Unset):  Default: 'criado_em:desc'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Erro | ListaJobs
    """

    return (
        await asyncio_detailed(
            client=client,
            estado=estado,
            tipo=tipo,
            usuario_id=usuario_id,
            de=de,
            ate=ate,
            agenda_id=agenda_id,
            limite=limite,
            deslocamento=deslocamento,
            ordenar=ordenar,
        )
    ).parsed
