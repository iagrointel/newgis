from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pagina_auth import PaginaAuth
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    perfil: None | str | Unset = UNSET,
    ativo: bool | None | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    ordenar: str | Unset = "login",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_perfil: None | str | Unset
    if isinstance(perfil, Unset):
        json_perfil = UNSET
    else:
        json_perfil = perfil
    params["perfil"] = json_perfil

    json_ativo: bool | None | Unset
    if isinstance(ativo, Unset):
        json_ativo = UNSET
    else:
        json_ativo = ativo
    params["ativo"] = json_ativo

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    json_deslocamento: int | None | Unset
    if isinstance(deslocamento, Unset):
        json_deslocamento = UNSET
    else:
        json_deslocamento = deslocamento
    params["deslocamento"] = json_deslocamento

    params["ordenar"] = ordenar

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/usuarios",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PaginaAuth | None:
    if response.status_code == 200:
        response_200 = PaginaAuth.from_dict(response.json())

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
) -> Response[HTTPValidationError | PaginaAuth]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    perfil: None | str | Unset = UNSET,
    ativo: bool | None | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    ordenar: str | Unset = "login",
) -> Response[HTTPValidationError | PaginaAuth]:
    """Listar Usuarios

    Args:
        perfil (None | str | Unset):
        ativo (bool | None | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        ordenar (str | Unset):  Default: 'login'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        perfil=perfil,
        ativo=ativo,
        q=q,
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
    perfil: None | str | Unset = UNSET,
    ativo: bool | None | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    ordenar: str | Unset = "login",
) -> HTTPValidationError | PaginaAuth | None:
    """Listar Usuarios

    Args:
        perfil (None | str | Unset):
        ativo (bool | None | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        ordenar (str | Unset):  Default: 'login'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return sync_detailed(
        client=client,
        perfil=perfil,
        ativo=ativo,
        q=q,
        limite=limite,
        deslocamento=deslocamento,
        ordenar=ordenar,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    perfil: None | str | Unset = UNSET,
    ativo: bool | None | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    ordenar: str | Unset = "login",
) -> Response[HTTPValidationError | PaginaAuth]:
    """Listar Usuarios

    Args:
        perfil (None | str | Unset):
        ativo (bool | None | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        ordenar (str | Unset):  Default: 'login'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        perfil=perfil,
        ativo=ativo,
        q=q,
        limite=limite,
        deslocamento=deslocamento,
        ordenar=ordenar,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    perfil: None | str | Unset = UNSET,
    ativo: bool | None | Unset = UNSET,
    q: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    ordenar: str | Unset = "login",
) -> HTTPValidationError | PaginaAuth | None:
    """Listar Usuarios

    Args:
        perfil (None | str | Unset):
        ativo (bool | None | Unset):
        q (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        ordenar (str | Unset):  Default: 'login'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return (
        await asyncio_detailed(
            client=client,
            perfil=perfil,
            ativo=ativo,
            q=q,
            limite=limite,
            deslocamento=deslocamento,
            ordenar=ordenar,
        )
    ).parsed
