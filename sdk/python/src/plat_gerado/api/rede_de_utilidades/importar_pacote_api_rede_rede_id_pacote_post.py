from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.importacao_resultado import ImportacaoResultado
from ...types import Response


def _get_kwargs(
    rede_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/pacote".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ImportacaoResultado | None:
    if response.status_code == 201:
        response_201 = ImportacaoResultado.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | ImportacaoResultado]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | ImportacaoResultado]:
    """Importar Pacote

     Importa o pacote de ativos. Substitui o catálogo INTEIRO da rede, numa transação: ou entra tudo, ou
    nada.
    Só a leitura do corpo fica no laço de eventos (rápida, I/O); validação e gravação vão para o
    threadpool.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | ImportacaoResultado | None:
    """Importar Pacote

     Importa o pacote de ativos. Substitui o catálogo INTEIRO da rede, numa transação: ou entra tudo, ou
    nada.
    Só a leitura do corpo fica no laço de eventos (rápida, I/O); validação e gravação vão para o
    threadpool.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoResultado
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | ImportacaoResultado]:
    """Importar Pacote

     Importa o pacote de ativos. Substitui o catálogo INTEIRO da rede, numa transação: ou entra tudo, ou
    nada.
    Só a leitura do corpo fica no laço de eventos (rápida, I/O); validação e gravação vão para o
    threadpool.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | ImportacaoResultado | None:
    """Importar Pacote

     Importa o pacote de ativos. Substitui o catálogo INTEIRO da rede, numa transação: ou entra tudo, ou
    nada.
    Só a leitura do corpo fica no laço de eventos (rápida, I/O); validação e gravação vão para o
    threadpool.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoResultado
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
        )
    ).parsed
