from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/integridade".format(
            id=quote(str(id), safe=""),
        ),
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Integridade

     item L5-05-documento-versoes: recomputa `sha256` de cada versão a partir do `corpo` GRAVADO em
    `plat.item_versao` e compara com o `sha256` da própria linha. As duas colunas só nascem juntas pelo
    gatilho
    `plat.tg_item_versao` (`app/catalogo/documento.py` explica por que o hash não é reproduzível por
    `sha256sum`
    puro fora deste Postgres — é `dados.corpo`, não `item_versao.corpo` inteiro, que tem o hash canônico
    externo); editar `corpo` direto no banco, por fora do gatilho, é exatamente o que este endpoint
    pega.

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
) -> Any | HTTPValidationError | None:
    """Integridade

     item L5-05-documento-versoes: recomputa `sha256` de cada versão a partir do `corpo` GRAVADO em
    `plat.item_versao` e compara com o `sha256` da própria linha. As duas colunas só nascem juntas pelo
    gatilho
    `plat.tg_item_versao` (`app/catalogo/documento.py` explica por que o hash não é reproduzível por
    `sha256sum`
    puro fora deste Postgres — é `dados.corpo`, não `item_versao.corpo` inteiro, que tem o hash canônico
    externo); editar `corpo` direto no banco, por fora do gatilho, é exatamente o que este endpoint
    pega.

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Integridade

     item L5-05-documento-versoes: recomputa `sha256` de cada versão a partir do `corpo` GRAVADO em
    `plat.item_versao` e compara com o `sha256` da própria linha. As duas colunas só nascem juntas pelo
    gatilho
    `plat.tg_item_versao` (`app/catalogo/documento.py` explica por que o hash não é reproduzível por
    `sha256sum`
    puro fora deste Postgres — é `dados.corpo`, não `item_versao.corpo` inteiro, que tem o hash canônico
    externo); editar `corpo` direto no banco, por fora do gatilho, é exatamente o que este endpoint
    pega.

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
) -> Any | HTTPValidationError | None:
    """Integridade

     item L5-05-documento-versoes: recomputa `sha256` de cada versão a partir do `corpo` GRAVADO em
    `plat.item_versao` e compara com o `sha256` da própria linha. As duas colunas só nascem juntas pelo
    gatilho
    `plat.tg_item_versao` (`app/catalogo/documento.py` explica por que o hash não é reproduzível por
    `sha256sum`
    puro fora deste Postgres — é `dados.corpo`, não `item_versao.corpo` inteiro, que tem o hash canônico
    externo); editar `corpo` direto no banco, por fora do gatilho, é exatamente o que este endpoint
    pega.

    Args:
        id (str):

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
        )
    ).parsed
