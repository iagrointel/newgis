from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.painel_dados_compartilhado_api_compartilhado_token_paineis_item_id_fontes_fonte_id_dados_post_corpo import (
    PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
)
from ...types import Response


def _get_kwargs(
    token: str,
    item_id: str,
    fonte_id: str,
    *,
    body: PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/compartilhado/{token}/paineis/{item_id}/fontes/{fonte_id}/dados".format(
            token=quote(str(token), safe=""),
            item_id=quote(str(item_id), safe=""),
            fonte_id=quote(str(fonte_id), safe=""),
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
    token: str,
    item_id: str,
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
) -> Response[Any | HTTPValidationError]:
    """Painel Dados Compartilhado

    Args:
        token (str):
        item_id (str):
        fonte_id (str):
        body
            (PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item_id=item_id,
        fonte_id=fonte_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item_id: str,
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
) -> Any | HTTPValidationError | None:
    """Painel Dados Compartilhado

    Args:
        token (str):
        item_id (str):
        fonte_id (str):
        body
            (PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item_id=item_id,
        fonte_id=fonte_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    token: str,
    item_id: str,
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
) -> Response[Any | HTTPValidationError]:
    """Painel Dados Compartilhado

    Args:
        token (str):
        item_id (str):
        fonte_id (str):
        body
            (PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item_id=item_id,
        fonte_id=fonte_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item_id: str,
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo,
) -> Any | HTTPValidationError | None:
    """Painel Dados Compartilhado

    Args:
        token (str):
        item_id (str):
        fonte_id (str):
        body
            (PainelDadosCompartilhadoApiCompartilhadoTokenPaineisItemIdFontesFonteIdDadosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            item_id=item_id,
            fonte_id=fonte_id,
            client=client,
            body=body,
        )
    ).parsed
