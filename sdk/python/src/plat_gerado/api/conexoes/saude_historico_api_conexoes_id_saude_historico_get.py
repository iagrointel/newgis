from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.saude_historico_pagina import SaudeHistoricoPagina
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    limite: int | Unset = 10,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/saude-historico".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SaudeHistoricoPagina | None:
    if response.status_code == 200:
        response_200 = SaudeHistoricoPagina.from_dict(response.json())

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
) -> Response[HTTPValidationError | SaudeHistoricoPagina]:
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
    limite: int | Unset = 10,
) -> Response[HTTPValidationError | SaudeHistoricoPagina]:
    """Saude Historico

     Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10,
    teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que
    existe.

    Args:
        id (str):
        limite (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SaudeHistoricoPagina]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 10,
) -> HTTPValidationError | SaudeHistoricoPagina | None:
    """Saude Historico

     Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10,
    teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que
    existe.

    Args:
        id (str):
        limite (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SaudeHistoricoPagina
    """

    return sync_detailed(
        id=id,
        client=client,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 10,
) -> Response[HTTPValidationError | SaudeHistoricoPagina]:
    """Saude Historico

     Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10,
    teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que
    existe.

    Args:
        id (str):
        limite (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SaudeHistoricoPagina]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 10,
) -> HTTPValidationError | SaudeHistoricoPagina | None:
    """Saude Historico

     Últimos testes de saúde da conexão (item L6-02-l-saude), mais recente primeiro; `limite` (padrão 10,
    teto
    30 — o mesmo teto de guarda de `plat.conexao_saude_historico`) evita que a tela peça mais do que
    existe.

    Args:
        id (str):
        limite (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SaudeHistoricoPagina
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            limite=limite,
        )
    ).parsed
