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
    tipo: list[str] | None | Unset = UNSET,
    familia: list[str] | None | Unset = UNSET,
    dono_id: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    categoria: list[str] | None | Unset = UNSET,
    status: list[str] | None | Unset = UNSET,
    acesso: list[str] | None | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    origem: None | str | Unset = UNSET,
    criado_de: None | str | Unset = UNSET,
    criado_ate: None | str | Unset = UNSET,
    modificado_de: None | str | Unset = UNSET,
    modificado_ate: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    grupo_id: None | str | Unset = UNSET,
    favoritos: bool | Unset = False,
    meus: bool | Unset = False,
    prefixo: bool | Unset = False,
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

    json_tipo: list[str] | None | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    elif isinstance(tipo, list):
        json_tipo = tipo

    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    json_familia: list[str] | None | Unset
    if isinstance(familia, Unset):
        json_familia = UNSET
    elif isinstance(familia, list):
        json_familia = familia

    else:
        json_familia = familia
    params["familia"] = json_familia

    json_dono_id: list[str] | None | Unset
    if isinstance(dono_id, Unset):
        json_dono_id = UNSET
    elif isinstance(dono_id, list):
        json_dono_id = dono_id

    else:
        json_dono_id = dono_id
    params["dono_id"] = json_dono_id

    json_tags: list[str] | None | Unset
    if isinstance(tags, Unset):
        json_tags = UNSET
    elif isinstance(tags, list):
        json_tags = tags

    else:
        json_tags = tags
    params["tags"] = json_tags

    json_categoria: list[str] | None | Unset
    if isinstance(categoria, Unset):
        json_categoria = UNSET
    elif isinstance(categoria, list):
        json_categoria = categoria

    else:
        json_categoria = categoria
    params["categoria"] = json_categoria

    json_status: list[str] | None | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, list):
        json_status = status

    else:
        json_status = status
    params["status"] = json_status

    json_acesso: list[str] | None | Unset
    if isinstance(acesso, Unset):
        json_acesso = UNSET
    elif isinstance(acesso, list):
        json_acesso = acesso

    else:
        json_acesso = acesso
    params["acesso"] = json_acesso

    json_pasta_id: None | str | Unset
    if isinstance(pasta_id, Unset):
        json_pasta_id = UNSET
    else:
        json_pasta_id = pasta_id
    params["pasta_id"] = json_pasta_id

    json_origem: None | str | Unset
    if isinstance(origem, Unset):
        json_origem = UNSET
    else:
        json_origem = origem
    params["origem"] = json_origem

    json_criado_de: None | str | Unset
    if isinstance(criado_de, Unset):
        json_criado_de = UNSET
    else:
        json_criado_de = criado_de
    params["criado_de"] = json_criado_de

    json_criado_ate: None | str | Unset
    if isinstance(criado_ate, Unset):
        json_criado_ate = UNSET
    else:
        json_criado_ate = criado_ate
    params["criado_ate"] = json_criado_ate

    json_modificado_de: None | str | Unset
    if isinstance(modificado_de, Unset):
        json_modificado_de = UNSET
    else:
        json_modificado_de = modificado_de
    params["modificado_de"] = json_modificado_de

    json_modificado_ate: None | str | Unset
    if isinstance(modificado_ate, Unset):
        json_modificado_ate = UNSET
    else:
        json_modificado_ate = modificado_ate
    params["modificado_ate"] = json_modificado_ate

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_grupo_id: None | str | Unset
    if isinstance(grupo_id, Unset):
        json_grupo_id = UNSET
    else:
        json_grupo_id = grupo_id
    params["grupo_id"] = json_grupo_id

    params["favoritos"] = favoritos

    params["meus"] = meus

    params["prefixo"] = prefixo

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
        "url": "/api/itens",
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
    tipo: list[str] | None | Unset = UNSET,
    familia: list[str] | None | Unset = UNSET,
    dono_id: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    categoria: list[str] | None | Unset = UNSET,
    status: list[str] | None | Unset = UNSET,
    acesso: list[str] | None | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    origem: None | str | Unset = UNSET,
    criado_de: None | str | Unset = UNSET,
    criado_ate: None | str | Unset = UNSET,
    modificado_de: None | str | Unset = UNSET,
    modificado_ate: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    grupo_id: None | str | Unset = UNSET,
    favoritos: bool | Unset = False,
    meus: bool | Unset = False,
    prefixo: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Listar

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        tipo (list[str] | None | Unset):
        familia (list[str] | None | Unset):
        dono_id (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        categoria (list[str] | None | Unset):
        status (list[str] | None | Unset):
        acesso (list[str] | None | Unset):
        pasta_id (None | str | Unset):
        origem (None | str | Unset):
        criado_de (None | str | Unset):
        criado_ate (None | str | Unset):
        modificado_de (None | str | Unset):
        modificado_ate (None | str | Unset):
        bbox (None | str | Unset):
        grupo_id (None | str | Unset):
        favoritos (bool | Unset):  Default: False.
        meus (bool | Unset):  Default: False.
        prefixo (bool | Unset):  Default: False.
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
        tipo=tipo,
        familia=familia,
        dono_id=dono_id,
        tags=tags,
        categoria=categoria,
        status=status,
        acesso=acesso,
        pasta_id=pasta_id,
        origem=origem,
        criado_de=criado_de,
        criado_ate=criado_ate,
        modificado_de=modificado_de,
        modificado_ate=modificado_ate,
        bbox=bbox,
        grupo_id=grupo_id,
        favoritos=favoritos,
        meus=meus,
        prefixo=prefixo,
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
    tipo: list[str] | None | Unset = UNSET,
    familia: list[str] | None | Unset = UNSET,
    dono_id: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    categoria: list[str] | None | Unset = UNSET,
    status: list[str] | None | Unset = UNSET,
    acesso: list[str] | None | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    origem: None | str | Unset = UNSET,
    criado_de: None | str | Unset = UNSET,
    criado_ate: None | str | Unset = UNSET,
    modificado_de: None | str | Unset = UNSET,
    modificado_ate: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    grupo_id: None | str | Unset = UNSET,
    favoritos: bool | Unset = False,
    meus: bool | Unset = False,
    prefixo: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Listar

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        tipo (list[str] | None | Unset):
        familia (list[str] | None | Unset):
        dono_id (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        categoria (list[str] | None | Unset):
        status (list[str] | None | Unset):
        acesso (list[str] | None | Unset):
        pasta_id (None | str | Unset):
        origem (None | str | Unset):
        criado_de (None | str | Unset):
        criado_ate (None | str | Unset):
        modificado_de (None | str | Unset):
        modificado_ate (None | str | Unset):
        bbox (None | str | Unset):
        grupo_id (None | str | Unset):
        favoritos (bool | Unset):  Default: False.
        meus (bool | Unset):  Default: False.
        prefixo (bool | Unset):  Default: False.
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
        tipo=tipo,
        familia=familia,
        dono_id=dono_id,
        tags=tags,
        categoria=categoria,
        status=status,
        acesso=acesso,
        pasta_id=pasta_id,
        origem=origem,
        criado_de=criado_de,
        criado_ate=criado_ate,
        modificado_de=modificado_de,
        modificado_ate=modificado_ate,
        bbox=bbox,
        grupo_id=grupo_id,
        favoritos=favoritos,
        meus=meus,
        prefixo=prefixo,
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
    tipo: list[str] | None | Unset = UNSET,
    familia: list[str] | None | Unset = UNSET,
    dono_id: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    categoria: list[str] | None | Unset = UNSET,
    status: list[str] | None | Unset = UNSET,
    acesso: list[str] | None | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    origem: None | str | Unset = UNSET,
    criado_de: None | str | Unset = UNSET,
    criado_ate: None | str | Unset = UNSET,
    modificado_de: None | str | Unset = UNSET,
    modificado_ate: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    grupo_id: None | str | Unset = UNSET,
    favoritos: bool | Unset = False,
    meus: bool | Unset = False,
    prefixo: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Listar

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        tipo (list[str] | None | Unset):
        familia (list[str] | None | Unset):
        dono_id (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        categoria (list[str] | None | Unset):
        status (list[str] | None | Unset):
        acesso (list[str] | None | Unset):
        pasta_id (None | str | Unset):
        origem (None | str | Unset):
        criado_de (None | str | Unset):
        criado_ate (None | str | Unset):
        modificado_de (None | str | Unset):
        modificado_ate (None | str | Unset):
        bbox (None | str | Unset):
        grupo_id (None | str | Unset):
        favoritos (bool | Unset):  Default: False.
        meus (bool | Unset):  Default: False.
        prefixo (bool | Unset):  Default: False.
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
        tipo=tipo,
        familia=familia,
        dono_id=dono_id,
        tags=tags,
        categoria=categoria,
        status=status,
        acesso=acesso,
        pasta_id=pasta_id,
        origem=origem,
        criado_de=criado_de,
        criado_ate=criado_ate,
        modificado_de=modificado_de,
        modificado_ate=modificado_ate,
        bbox=bbox,
        grupo_id=grupo_id,
        favoritos=favoritos,
        meus=meus,
        prefixo=prefixo,
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
    tipo: list[str] | None | Unset = UNSET,
    familia: list[str] | None | Unset = UNSET,
    dono_id: list[str] | None | Unset = UNSET,
    tags: list[str] | None | Unset = UNSET,
    categoria: list[str] | None | Unset = UNSET,
    status: list[str] | None | Unset = UNSET,
    acesso: list[str] | None | Unset = UNSET,
    pasta_id: None | str | Unset = UNSET,
    origem: None | str | Unset = UNSET,
    criado_de: None | str | Unset = UNSET,
    criado_ate: None | str | Unset = UNSET,
    modificado_de: None | str | Unset = UNSET,
    modificado_ate: None | str | Unset = UNSET,
    bbox: None | str | Unset = UNSET,
    grupo_id: None | str | Unset = UNSET,
    favoritos: bool | Unset = False,
    meus: bool | Unset = False,
    prefixo: bool | Unset = False,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Listar

    Args:
        q (None | str | Unset):
        ordenar (None | str | Unset):
        direcao (None | str | Unset):
        tipo (list[str] | None | Unset):
        familia (list[str] | None | Unset):
        dono_id (list[str] | None | Unset):
        tags (list[str] | None | Unset):
        categoria (list[str] | None | Unset):
        status (list[str] | None | Unset):
        acesso (list[str] | None | Unset):
        pasta_id (None | str | Unset):
        origem (None | str | Unset):
        criado_de (None | str | Unset):
        criado_ate (None | str | Unset):
        modificado_de (None | str | Unset):
        modificado_ate (None | str | Unset):
        bbox (None | str | Unset):
        grupo_id (None | str | Unset):
        favoritos (bool | Unset):  Default: False.
        meus (bool | Unset):  Default: False.
        prefixo (bool | Unset):  Default: False.
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
            tipo=tipo,
            familia=familia,
            dono_id=dono_id,
            tags=tags,
            categoria=categoria,
            status=status,
            acesso=acesso,
            pasta_id=pasta_id,
            origem=origem,
            criado_de=criado_de,
            criado_ate=criado_ate,
            modificado_de=modificado_de,
            modificado_ate=modificado_ate,
            bbox=bbox,
            grupo_id=grupo_id,
            favoritos=favoritos,
            meus=meus,
            prefixo=prefixo,
            limite=limite,
            deslocamento=deslocamento,
            cursor=cursor,
        )
    ).parsed
