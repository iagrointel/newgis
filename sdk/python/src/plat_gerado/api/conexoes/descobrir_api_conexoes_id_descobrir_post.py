from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.descobrir_resultado import DescobrirResultado
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/conexoes/{id}/descobrir".format(
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DescobrirResultado | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DescobrirResultado.from_dict(response.json())

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
) -> Response[DescobrirResultado | HTTPValidationError]:
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
) -> Response[DescobrirResultado | HTTPValidationError]:
    """Descobrir

     Sonda o serviço agora (`GetCapabilities`/`/collections`/`f=json`, conforme o tipo) e SUBSTITUI a
    lista
    guardada de camadas (item L6-02-conectores-vivos): a lista de hoje reflete o que o serviço declara
    HOJE,
    nunca uma mistura com uma descoberta antiga que uma camada tenha sumido do serviço. Sem rede fora de
    `app.conexao.seguranca.buscar_seguro` (mesmo caminho auditado contra SSRF do teste de saúde).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DescobrirResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> DescobrirResultado | HTTPValidationError | None:
    """Descobrir

     Sonda o serviço agora (`GetCapabilities`/`/collections`/`f=json`, conforme o tipo) e SUBSTITUI a
    lista
    guardada de camadas (item L6-02-conectores-vivos): a lista de hoje reflete o que o serviço declara
    HOJE,
    nunca uma mistura com uma descoberta antiga que uma camada tenha sumido do serviço. Sem rede fora de
    `app.conexao.seguranca.buscar_seguro` (mesmo caminho auditado contra SSRF do teste de saúde).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DescobrirResultado | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[DescobrirResultado | HTTPValidationError]:
    """Descobrir

     Sonda o serviço agora (`GetCapabilities`/`/collections`/`f=json`, conforme o tipo) e SUBSTITUI a
    lista
    guardada de camadas (item L6-02-conectores-vivos): a lista de hoje reflete o que o serviço declara
    HOJE,
    nunca uma mistura com uma descoberta antiga que uma camada tenha sumido do serviço. Sem rede fora de
    `app.conexao.seguranca.buscar_seguro` (mesmo caminho auditado contra SSRF do teste de saúde).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DescobrirResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> DescobrirResultado | HTTPValidationError | None:
    """Descobrir

     Sonda o serviço agora (`GetCapabilities`/`/collections`/`f=json`, conforme o tipo) e SUBSTITUI a
    lista
    guardada de camadas (item L6-02-conectores-vivos): a lista de hoje reflete o que o serviço declara
    HOJE,
    nunca uma mistura com uma descoberta antiga que uma camada tenha sumido do serviço. Sem rede fora de
    `app.conexao.seguranca.buscar_seguro` (mesmo caminho auditado contra SSRF do teste de saúde).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DescobrirResultado | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
        )
    ).parsed
