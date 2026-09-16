from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.item import Item
from ...models.publicar_entrada_script import PublicarEntradaScript
from ...types import Response


def _get_kwargs(
    *,
    body: PublicarEntradaScript,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/ferramentas/script",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | Item | None:
    if response.status_code == 201:
        response_201 = Item.from_dict(response.json())

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
) -> Response[HTTPValidationError | Item]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PublicarEntradaScript,
) -> Response[HTTPValidationError | Item]:
    """Publicar

     Publica um script como ferramenta do catálogo (item `ferramenta_script`, versão 1).
    O cabeçalho YAML da docstring é validado antes de gravar; cabeçalho inválido é 422 e nada
    é gravado.

    Args:
        body (PublicarEntradaScript):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: PublicarEntradaScript,
) -> HTTPValidationError | Item | None:
    """Publicar

     Publica um script como ferramenta do catálogo (item `ferramenta_script`, versão 1).
    O cabeçalho YAML da docstring é validado antes de gravar; cabeçalho inválido é 422 e nada
    é gravado.

    Args:
        body (PublicarEntradaScript):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PublicarEntradaScript,
) -> Response[HTTPValidationError | Item]:
    """Publicar

     Publica um script como ferramenta do catálogo (item `ferramenta_script`, versão 1).
    O cabeçalho YAML da docstring é validado antes de gravar; cabeçalho inválido é 422 e nada
    é gravado.

    Args:
        body (PublicarEntradaScript):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: PublicarEntradaScript,
) -> HTTPValidationError | Item | None:
    """Publicar

     Publica um script como ferramenta do catálogo (item `ferramenta_script`, versão 1).
    O cabeçalho YAML da docstring é validado antes de gravar; cabeçalho inválido é 422 e nada
    é gravado.

    Args:
        body (PublicarEntradaScript):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
