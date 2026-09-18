from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_meu_mapa_camada import AcervoMeuMapaCamada
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/meu-mapa",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> list[AcervoMeuMapaCamada] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = AcervoMeuMapaCamada.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[list[AcervoMeuMapaCamada]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[list[AcervoMeuMapaCamada]]:
    """Meu Mapa

     As camadas do acervo que ESTE inquilino já adicionou, para a legenda do mapa (item L6-01-c). O
    filtro é `dados->>'protocolo' = 'acervo'`, não o tipo do item: uma conexão externa comum (item
    L6-02)
    também é `conexao` e não é camada do acervo. O isolamento entre inquilinos é o mesmo do resto do
    catálogo (RLS por `tenant_id` em `plat.item`), não uma cláusula escrita aqui.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[AcervoMeuMapaCamada]]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> list[AcervoMeuMapaCamada] | None:
    """Meu Mapa

     As camadas do acervo que ESTE inquilino já adicionou, para a legenda do mapa (item L6-01-c). O
    filtro é `dados->>'protocolo' = 'acervo'`, não o tipo do item: uma conexão externa comum (item
    L6-02)
    também é `conexao` e não é camada do acervo. O isolamento entre inquilinos é o mesmo do resto do
    catálogo (RLS por `tenant_id` em `plat.item`), não uma cláusula escrita aqui.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[AcervoMeuMapaCamada]
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[list[AcervoMeuMapaCamada]]:
    """Meu Mapa

     As camadas do acervo que ESTE inquilino já adicionou, para a legenda do mapa (item L6-01-c). O
    filtro é `dados->>'protocolo' = 'acervo'`, não o tipo do item: uma conexão externa comum (item
    L6-02)
    também é `conexao` e não é camada do acervo. O isolamento entre inquilinos é o mesmo do resto do
    catálogo (RLS por `tenant_id` em `plat.item`), não uma cláusula escrita aqui.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[AcervoMeuMapaCamada]]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> list[AcervoMeuMapaCamada] | None:
    """Meu Mapa

     As camadas do acervo que ESTE inquilino já adicionou, para a legenda do mapa (item L6-01-c). O
    filtro é `dados->>'protocolo' = 'acervo'`, não o tipo do item: uma conexão externa comum (item
    L6-02)
    também é `conexao` e não é camada do acervo. O isolamento entre inquilinos é o mesmo do resto do
    catálogo (RLS por `tenant_id` em `plat.item`), não uma cláusula escrita aqui.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[AcervoMeuMapaCamada]
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
