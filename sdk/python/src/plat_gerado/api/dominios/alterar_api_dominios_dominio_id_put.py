from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.dominio_entrada import DominioEntrada
from ...models.dominio_saida import DominioSaida
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    dominio_id: str,
    *,
    body: DominioEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/dominios/{dominio_id}".format(
            dominio_id=quote(str(dominio_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DominioSaida | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DominioSaida.from_dict(response.json())

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
) -> Response[DominioSaida | HTTPValidationError]:
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
    body: DominioEntrada,
) -> Response[DominioSaida | HTTPValidationError]:
    """Alterar

     Substitui o domínio inteiro. Duas recusas próprias desta rota, antes de qualquer escrita: trocar o
    tipo de campo para um incompatível com algum campo já ligado (409) e remover valor em uso (409, com
    a
    contagem — quem levanta é o gatilho do banco, para valer também para quem escreve por fora da API).

    Args:
        dominio_id (str):
        body (DominioEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DominioSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dominio_id=dominio_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DominioEntrada,
) -> DominioSaida | HTTPValidationError | None:
    """Alterar

     Substitui o domínio inteiro. Duas recusas próprias desta rota, antes de qualquer escrita: trocar o
    tipo de campo para um incompatível com algum campo já ligado (409) e remover valor em uso (409, com
    a
    contagem — quem levanta é o gatilho do banco, para valer também para quem escreve por fora da API).

    Args:
        dominio_id (str):
        body (DominioEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DominioSaida | HTTPValidationError
    """

    return sync_detailed(
        dominio_id=dominio_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DominioEntrada,
) -> Response[DominioSaida | HTTPValidationError]:
    """Alterar

     Substitui o domínio inteiro. Duas recusas próprias desta rota, antes de qualquer escrita: trocar o
    tipo de campo para um incompatível com algum campo já ligado (409) e remover valor em uso (409, com
    a
    contagem — quem levanta é o gatilho do banco, para valer também para quem escreve por fora da API).

    Args:
        dominio_id (str):
        body (DominioEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DominioSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dominio_id=dominio_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    dominio_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DominioEntrada,
) -> DominioSaida | HTTPValidationError | None:
    """Alterar

     Substitui o domínio inteiro. Duas recusas próprias desta rota, antes de qualquer escrita: trocar o
    tipo de campo para um incompatível com algum campo já ligado (409) e remover valor em uso (409, com
    a
    contagem — quem levanta é o gatilho do banco, para valer também para quem escreve por fora da API).

    Args:
        dominio_id (str):
        body (DominioEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DominioSaida | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            dominio_id=dominio_id,
            client=client,
            body=body,
        )
    ).parsed
