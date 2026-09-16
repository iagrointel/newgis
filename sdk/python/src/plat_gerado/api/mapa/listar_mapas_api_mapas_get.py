from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pagina_catalogo import PaginaCatalogo
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: None | str | Unset = UNSET,
    ordenar: None | str | Unset = UNSET,
    direcao: None | str | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    meus: bool | Unset = False,
    favoritos: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

    json_ordenar: None | str | Unset
    if isinstance(ordenar, Unset):
        json_ordenar = UNSET
    else:
        json_ordenar = ordenar
    params["ordenar"] = json_ordenar

    json_direcao: None | str | Unset
    if isinstance(direcao, Unset):
        json_direcao = UNSET
    else:
        json_direcao = direcao
    params["direcao"] = json_direcao

    json_pasta_id: None | str | Unset
    if isinstance(pasta_id, Unset):
        json_pasta_id = UNSET
    else:
        json_pasta_id = pasta_id
    params["pasta_id"] = json_pasta_id

    params["meus"] = meus

    params["favoritos"] = favoritos

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

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/mapas",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PaginaCatalogo | None:
    if response.status_code == 200:
        response_200 = PaginaCatalogo.from_dict(response.json())

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
) -> Response[HTTPValidationError | PaginaCatalogo]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    ordenar: None | str | Unset = UNSET,
    direcao: None | str | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    meus: bool | Unset = False,
    favoritos: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Listar Mapas

     Mesma lista de `/api/itens` com `tipo` travado em `mapa` (os demais filtros da query continuam
    valendo).

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        pasta_id (None | str | Unset):
        meus (bool | Unset):  Default: False.
        favoritos (bool | Unset):  Default: False.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaCatalogo]
    """

    kwargs = _get_kwargs(
        q=q,
        ordenar=ordenar,
        direcao=direcao,
        pasta_id=pasta_id,
        meus=meus,
        favoritos=favoritos,
        limite=limite,
        deslocamento=deslocamento,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    ordenar: None | str | Unset = UNSET,
    direcao: None | str | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    meus: bool | Unset = False,
    favoritos: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Listar Mapas

     Mesma lista de `/api/itens` com `tipo` travado em `mapa` (os demais filtros da query continuam
    valendo).

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        pasta_id (None | str | Unset):
        meus (bool | Unset):  Default: False.
        favoritos (bool | Unset):  Default: False.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaCatalogo
    """

    return sync_detailed(
        client=client,
        q=q,
        ordenar=ordenar,
        direcao=direcao,
        pasta_id=pasta_id,
        meus=meus,
        favoritos=favoritos,
        limite=limite,
        deslocamento=deslocamento,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    ordenar: None | str | Unset = UNSET,
    direcao: None | str | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    meus: bool | Unset = False,
    favoritos: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Listar Mapas

     Mesma lista de `/api/itens` com `tipo` travado em `mapa` (os demais filtros da query continuam
    valendo).

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        pasta_id (None | str | Unset):
        meus (bool | Unset):  Default: False.
        favoritos (bool | Unset):  Default: False.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaCatalogo]
    """

    kwargs = _get_kwargs(
        q=q,
        ordenar=ordenar,
        direcao=direcao,
        pasta_id=pasta_id,
        meus=meus,
        favoritos=favoritos,
        limite=limite,
        deslocamento=deslocamento,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    ordenar: None | str | Unset = UNSET,
    direcao: None | str | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    meus: bool | Unset = False,
    favoritos: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Listar Mapas

     Mesma lista de `/api/itens` com `tipo` travado em `mapa` (os demais filtros da query continuam
    valendo).

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        pasta_id (None | str | Unset):
        meus (bool | Unset):  Default: False.
        favoritos (bool | Unset):  Default: False.
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaCatalogo
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            ordenar=ordenar,
            direcao=direcao,
            pasta_id=pasta_id,
            meus=meus,
            favoritos=favoritos,
            limite=limite,
            deslocamento=deslocamento,
            cursor=cursor,
        )
    ).parsed
