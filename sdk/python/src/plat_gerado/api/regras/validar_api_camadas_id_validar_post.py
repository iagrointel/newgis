from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.validar_saida import ValidarSaida
from ...types import Response


def _get_kwargs(
    id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/validar".format(
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ValidarSaida | None:
    if response.status_code == 201:
        response_201 = ValidarSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | ValidarSaida]:
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
) -> Response[HTTPValidationError | ValidarSaida]:
    """Validar

     Enfileira `camadas.validar` para a camada: avalia toda regra de validação habilitada em cada feição
    e grava
    os erros em e_<hex16> + camada de erros (equivalente ao Evaluate Rules). Evento `jobs/criar` (do
    serviço).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ValidarSaida]
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
) -> HTTPValidationError | ValidarSaida | None:
    """Validar

     Enfileira `camadas.validar` para a camada: avalia toda regra de validação habilitada em cada feição
    e grava
    os erros em e_<hex16> + camada de erros (equivalente ao Evaluate Rules). Evento `jobs/criar` (do
    serviço).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ValidarSaida
    """

    return sync_detailed(
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | ValidarSaida]:
    """Validar

     Enfileira `camadas.validar` para a camada: avalia toda regra de validação habilitada em cada feição
    e grava
    os erros em e_<hex16> + camada de erros (equivalente ao Evaluate Rules). Evento `jobs/criar` (do
    serviço).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ValidarSaida]
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
) -> HTTPValidationError | ValidarSaida | None:
    """Validar

     Enfileira `camadas.validar` para a camada: avalia toda regra de validação habilitada em cada feição
    e grava
    os erros em e_<hex16> + camada de erros (equivalente ao Evaluate Rules). Evento `jobs/criar` (do
    serviço).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ValidarSaida
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
        )
    ).parsed
