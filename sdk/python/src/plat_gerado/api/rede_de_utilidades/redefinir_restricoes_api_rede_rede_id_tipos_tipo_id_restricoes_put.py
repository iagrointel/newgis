from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.restricoes_entrada import RestricoesEntrada
from ...types import Response


def _get_kwargs(
    rede_id: str,
    tipo_id: str,
    *,
    body: RestricoesEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/rede/{rede_id}/tipos/{tipo_id}/restricoes".format(
            rede_id=quote(str(rede_id), safe=""),
            tipo_id=quote(str(tipo_id), safe=""),
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
    rede_id: str,
    tipo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: RestricoesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Redefinir Restricoes

     Substitui as restrições de feição de um tipo de ativo (`sem_ponto_partida`, `sem_terminal`).

    Args:
        rede_id (str):
        tipo_id (str):
        body (RestricoesEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    tipo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: RestricoesEntrada,
) -> Any | HTTPValidationError | None:
    """Redefinir Restricoes

     Substitui as restrições de feição de um tipo de ativo (`sem_ponto_partida`, `sem_terminal`).

    Args:
        rede_id (str):
        tipo_id (str):
        body (RestricoesEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        tipo_id=tipo_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    tipo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: RestricoesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Redefinir Restricoes

     Substitui as restrições de feição de um tipo de ativo (`sem_ponto_partida`, `sem_terminal`).

    Args:
        rede_id (str):
        tipo_id (str):
        body (RestricoesEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        tipo_id=tipo_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    tipo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: RestricoesEntrada,
) -> Any | HTTPValidationError | None:
    """Redefinir Restricoes

     Substitui as restrições de feição de um tipo de ativo (`sem_ponto_partida`, `sem_terminal`).

    Args:
        rede_id (str):
        tipo_id (str):
        body (RestricoesEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            tipo_id=tipo_id,
            client=client,
            body=body,
        )
    ).parsed
