from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    colecao_id: str,
    *,
    q: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    tipo: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_tipo: list[str] | None | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    elif isinstance(tipo, list):
        json_tipo = tipo

    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    json_tags: list[str] | None | Unset
    if isinstance(tags, Unset):
        json_tags = UNSET
    elif isinstance(tags, list):
        json_tags = tags

    else:
        json_tags = tags
    params["tags"] = json_tags

    json_limit: int | None | Unset
    if isinstance(limit, Unset):
        json_limit = UNSET
    else:
        json_limit = limit
    params["limit"] = json_limit

    json_offset: int | None | Unset
    if isinstance(offset, Unset):
        json_offset = UNSET
    else:
        json_offset = offset
    params["offset"] = json_offset

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/ogc/records/collections/{colecao_id}/items".format(
            colecao_id=quote(str(colecao_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    tipo: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Itens Da Colecao

     GetRecords equivalente: mesmos filtros simples de `GET /api/itens` (q, bbox, tipo, tags); paginação
    `limit`/`offset` no vocabulário OGC (mapeados aos `limite`/`deslocamento` internos), `cursor` para a
    página seguinte (link `rel=next`). RLS de `plat.item` garante que só itens do inquilino do
    token/sessão
    aparecem — nunca de outro (refutação do item).

    Args:
        colecao_id (str):
        q (None | str | Unset):
        bbox (None | str | Unset):
        tipo (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        colecao_id=colecao_id,
        q=q,
        bbox=bbox,
        tipo=tipo,
        tags=tags,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    tipo: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Itens Da Colecao

     GetRecords equivalente: mesmos filtros simples de `GET /api/itens` (q, bbox, tipo, tags); paginação
    `limit`/`offset` no vocabulário OGC (mapeados aos `limite`/`deslocamento` internos), `cursor` para a
    página seguinte (link `rel=next`). RLS de `plat.item` garante que só itens do inquilino do
    token/sessão
    aparecem — nunca de outro (refutação do item).

    Args:
        colecao_id (str):
        q (None | str | Unset):
        bbox (None | str | Unset):
        tipo (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        colecao_id=colecao_id,
        client=client,
        q=q,
        bbox=bbox,
        tipo=tipo,
        tags=tags,
        limit=limit,
        offset=offset,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    tipo: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Itens Da Colecao

     GetRecords equivalente: mesmos filtros simples de `GET /api/itens` (q, bbox, tipo, tags); paginação
    `limit`/`offset` no vocabulário OGC (mapeados aos `limite`/`deslocamento` internos), `cursor` para a
    página seguinte (link `rel=next`). RLS de `plat.item` garante que só itens do inquilino do
    token/sessão
    aparecem — nunca de outro (refutação do item).

    Args:
        colecao_id (str):
        q (None | str | Unset):
        bbox (None | str | Unset):
        tipo (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        colecao_id=colecao_id,
        q=q,
        bbox=bbox,
        tipo=tipo,
        tags=tags,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    colecao_id: str,
    *,
    client: AuthenticatedClient | Client,
    q: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    tipo: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    limit: int | None | Unset = UNSET,
    offset: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Itens Da Colecao

     GetRecords equivalente: mesmos filtros simples de `GET /api/itens` (q, bbox, tipo, tags); paginação
    `limit`/`offset` no vocabulário OGC (mapeados aos `limite`/`deslocamento` internos), `cursor` para a
    página seguinte (link `rel=next`). RLS de `plat.item` garante que só itens do inquilino do
    token/sessão
    aparecem — nunca de outro (refutação do item).

    Args:
        colecao_id (str):
        q (None | str | Unset):
        bbox (None | str | Unset):
        tipo (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        limit (int | None | Unset):
        offset (int | None | Unset):
        cursor (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            colecao_id=colecao_id,
            client=client,
            q=q,
            bbox=bbox,
            tipo=tipo,
            tags=tags,
            limit=limit,
            offset=offset,
            cursor=cursor,
        )
    ).parsed
