from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.editar_parcial_api_itens_id_patch_corpo import EditarParcialApiItensIdPatchCorpo
from ...models.http_validation_error import HTTPValidationError
from ...models.item import Item
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    body: EditarParcialApiItensIdPatchCorpo,
    rotulo: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    json_rotulo: None | str | Unset
    if isinstance(rotulo, Unset):
        json_rotulo = UNSET
    else:
        json_rotulo = rotulo
    params["rotulo"] = json_rotulo

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/itens/{id}".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | Item | None:
    if response.status_code == 200:
        response_200 = Item.from_dict(response.json())

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
) -> Response[HTTPValidationError | Item]:
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
    body: EditarParcialApiItensIdPatchCorpo,
    rotulo: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | Item]:
    """Editar Parcial

     `?rotulo=rascunho` é o autosave do editor (ADR 20260907T1522, item L5-09): grava a versão rotulada
    'rascunho' em vez de 'edicao'. Nenhum outro valor é aceito por fora (regex trava em `rascunho`); os
    demais rótulos do enum só o servidor escreve sozinho
    (edicao/restauracao/publicacao/compactada/migracao).
    Nunca toca `versao_publicada` — só `.../versoes/{n}/publicar` muda isso.

    Args:
        id (str):
        rotulo (None | str | Unset):
        body (EditarParcialApiItensIdPatchCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
        rotulo=rotulo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: EditarParcialApiItensIdPatchCorpo,
    rotulo: None | str | Unset = UNSET,
) -> HTTPValidationError | Item | None:
    """Editar Parcial

     `?rotulo=rascunho` é o autosave do editor (ADR 20260907T1522, item L5-09): grava a versão rotulada
    'rascunho' em vez de 'edicao'. Nenhum outro valor é aceito por fora (regex trava em `rascunho`); os
    demais rótulos do enum só o servidor escreve sozinho
    (edicao/restauracao/publicacao/compactada/migracao).
    Nunca toca `versao_publicada` — só `.../versoes/{n}/publicar` muda isso.

    Args:
        id (str):
        rotulo (None | str | Unset):
        body (EditarParcialApiItensIdPatchCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
        rotulo=rotulo,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: EditarParcialApiItensIdPatchCorpo,
    rotulo: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | Item]:
    """Editar Parcial

     `?rotulo=rascunho` é o autosave do editor (ADR 20260907T1522, item L5-09): grava a versão rotulada
    'rascunho' em vez de 'edicao'. Nenhum outro valor é aceito por fora (regex trava em `rascunho`); os
    demais rótulos do enum só o servidor escreve sozinho
    (edicao/restauracao/publicacao/compactada/migracao).
    Nunca toca `versao_publicada` — só `.../versoes/{n}/publicar` muda isso.

    Args:
        id (str):
        rotulo (None | str | Unset):
        body (EditarParcialApiItensIdPatchCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
        rotulo=rotulo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: EditarParcialApiItensIdPatchCorpo,
    rotulo: None | str | Unset = UNSET,
) -> HTTPValidationError | Item | None:
    """Editar Parcial

     `?rotulo=rascunho` é o autosave do editor (ADR 20260907T1522, item L5-09): grava a versão rotulada
    'rascunho' em vez de 'edicao'. Nenhum outro valor é aceito por fora (regex trava em `rascunho`); os
    demais rótulos do enum só o servidor escreve sozinho
    (edicao/restauracao/publicacao/compactada/migracao).
    Nunca toca `versao_publicada` — só `.../versoes/{n}/publicar` muda isso.

    Args:
        id (str):
        rotulo (None | str | Unset):
        body (EditarParcialApiItensIdPatchCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
            rotulo=rotulo,
        )
    ).parsed
