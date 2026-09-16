from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.metadado_editor_entrada import MetadadoEditorEntrada
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: MetadadoEditorEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/itens/{id}/metadado".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoEditorEntrada,
) -> Response[Any | HTTPValidationError]:
    """Metadado Salvar

     Grava a parte própria do metadado (`plat.item.metadado_iso`) e, se vier `item`, os campos
    sincronizados
    pelo MESMO caminho de `PUT/PATCH /api/itens/{id}` (`editar_item`) — nunca um segundo lugar de
    verdade para
    título/resumo/tags. Estrutura inválida (esquema, datas fora de ordem, corpo grande) = 422 com o
    caminho de
    cada erro; extent declarado que diverge do item real = aviso, nunca bloqueio (refutação do item
    L0-09-b).

    Args:
        id (str):
        body (MetadadoEditorEntrada): Corpo de `POST /api/itens/{id}/metadado/validar` e `PUT
            /api/itens/{id}/metadado` (item
            L0-09-metadado-catalogo, cláusula 3): `item` é o subconjunto sincronizado
            (título/resumo/tags/créditos/
            termos de uso — mesmo contrato de `ItemEditar`, validado por `editar_item`), `metadado` é
            a parte própria
            do Perfil MGB 2.0 (`app/catalogo/metadado_mgb.py`, `ESQUEMA_MGB`). Ambos ficam soltos
            (`dict`) aqui: quem
            valida estrutura é `metadado_mgb.validar_estrutura`/`editar_item`, nunca este modelo —
            repetir o esquema
            aqui seria um segundo lugar de verdade.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoEditorEntrada,
) -> Any | HTTPValidationError | None:
    """Metadado Salvar

     Grava a parte própria do metadado (`plat.item.metadado_iso`) e, se vier `item`, os campos
    sincronizados
    pelo MESMO caminho de `PUT/PATCH /api/itens/{id}` (`editar_item`) — nunca um segundo lugar de
    verdade para
    título/resumo/tags. Estrutura inválida (esquema, datas fora de ordem, corpo grande) = 422 com o
    caminho de
    cada erro; extent declarado que diverge do item real = aviso, nunca bloqueio (refutação do item
    L0-09-b).

    Args:
        id (str):
        body (MetadadoEditorEntrada): Corpo de `POST /api/itens/{id}/metadado/validar` e `PUT
            /api/itens/{id}/metadado` (item
            L0-09-metadado-catalogo, cláusula 3): `item` é o subconjunto sincronizado
            (título/resumo/tags/créditos/
            termos de uso — mesmo contrato de `ItemEditar`, validado por `editar_item`), `metadado` é
            a parte própria
            do Perfil MGB 2.0 (`app/catalogo/metadado_mgb.py`, `ESQUEMA_MGB`). Ambos ficam soltos
            (`dict`) aqui: quem
            valida estrutura é `metadado_mgb.validar_estrutura`/`editar_item`, nunca este modelo —
            repetir o esquema
            aqui seria um segundo lugar de verdade.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoEditorEntrada,
) -> Response[Any | HTTPValidationError]:
    """Metadado Salvar

     Grava a parte própria do metadado (`plat.item.metadado_iso`) e, se vier `item`, os campos
    sincronizados
    pelo MESMO caminho de `PUT/PATCH /api/itens/{id}` (`editar_item`) — nunca um segundo lugar de
    verdade para
    título/resumo/tags. Estrutura inválida (esquema, datas fora de ordem, corpo grande) = 422 com o
    caminho de
    cada erro; extent declarado que diverge do item real = aviso, nunca bloqueio (refutação do item
    L0-09-b).

    Args:
        id (str):
        body (MetadadoEditorEntrada): Corpo de `POST /api/itens/{id}/metadado/validar` e `PUT
            /api/itens/{id}/metadado` (item
            L0-09-metadado-catalogo, cláusula 3): `item` é o subconjunto sincronizado
            (título/resumo/tags/créditos/
            termos de uso — mesmo contrato de `ItemEditar`, validado por `editar_item`), `metadado` é
            a parte própria
            do Perfil MGB 2.0 (`app/catalogo/metadado_mgb.py`, `ESQUEMA_MGB`). Ambos ficam soltos
            (`dict`) aqui: quem
            valida estrutura é `metadado_mgb.validar_estrutura`/`editar_item`, nunca este modelo —
            repetir o esquema
            aqui seria um segundo lugar de verdade.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoEditorEntrada,
) -> Any | HTTPValidationError | None:
    """Metadado Salvar

     Grava a parte própria do metadado (`plat.item.metadado_iso`) e, se vier `item`, os campos
    sincronizados
    pelo MESMO caminho de `PUT/PATCH /api/itens/{id}` (`editar_item`) — nunca um segundo lugar de
    verdade para
    título/resumo/tags. Estrutura inválida (esquema, datas fora de ordem, corpo grande) = 422 com o
    caminho de
    cada erro; extent declarado que diverge do item real = aviso, nunca bloqueio (refutação do item
    L0-09-b).

    Args:
        id (str):
        body (MetadadoEditorEntrada): Corpo de `POST /api/itens/{id}/metadado/validar` e `PUT
            /api/itens/{id}/metadado` (item
            L0-09-metadado-catalogo, cláusula 3): `item` é o subconjunto sincronizado
            (título/resumo/tags/créditos/
            termos de uso — mesmo contrato de `ItemEditar`, validado por `editar_item`), `metadado` é
            a parte própria
            do Perfil MGB 2.0 (`app/catalogo/metadado_mgb.py`, `ESQUEMA_MGB`). Ambos ficam soltos
            (`dict`) aqui: quem
            valida estrutura é `metadado_mgb.validar_estrutura`/`editar_item`, nunca este modelo —
            repetir o esquema
            aqui seria um segundo lugar de verdade.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
