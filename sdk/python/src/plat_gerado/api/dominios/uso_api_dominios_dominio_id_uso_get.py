from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.uso_saida import UsoSaida
from ...types import Response


def _get_kwargs(
    dominio_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/dominios/{dominio_id}/uso".format(
            dominio_id=quote(str(dominio_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UsoSaida | None:
    if response.status_code == 200:
        response_200 = UsoSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | UsoSaida]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | UsoSaida]:
    """Uso

     As camadas que usam o domínio e quantas feições usam cada código — é o que a tela de edição mostra
    ANTES de deixar remover um valor.

    Args:
        dominio_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UsoSaida]
    """

    kwargs = _get_kwargs(
        dominio_id=dominio_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | UsoSaida | None:
    """Uso

     As camadas que usam o domínio e quantas feições usam cada código — é o que a tela de edição mostra
    ANTES de deixar remover um valor.

    Args:
        dominio_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UsoSaida
    """

    return sync_detailed(
        dominio_id=dominio_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | UsoSaida]:
    """Uso

     As camadas que usam o domínio e quantas feições usam cada código — é o que a tela de edição mostra
    ANTES de deixar remover um valor.

    Args:
        dominio_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UsoSaida]
    """

    kwargs = _get_kwargs(
        dominio_id=dominio_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | UsoSaida | None:
    """Uso

     As camadas que usam o domínio e quantas feições usam cada código — é o que a tela de edição mostra
    ANTES de deixar remover um valor.

    Args:
        dominio_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UsoSaida
    """

    return (
        await asyncio_detailed(
            dominio_id=dominio_id,
            client=client,
        )
    ).parsed
