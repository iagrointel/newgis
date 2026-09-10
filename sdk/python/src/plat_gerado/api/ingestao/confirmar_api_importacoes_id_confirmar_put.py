from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.confirmar_entrada import ConfirmarEntrada
from ...models.http_validation_error import HTTPValidationError
from ...models.job_criado import JobCriado
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: ConfirmarEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/importacoes/{id}/confirmar".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | JobCriado | None:
    if response.status_code == 202:
        response_202 = JobCriado.from_dict(response.json())

        return response_202

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | JobCriado]:
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
    body: ConfirmarEntrada,
) -> Response[HTTPValidationError | JobCriado]:
    """Confirmar

    Args:
        id (str):
        body (ConfirmarEntrada): O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que
            a tela deixa mudar. Cada um é validado
            contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as
            opções válidas).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobCriado]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarEntrada,
) -> HTTPValidationError | JobCriado | None:
    """Confirmar

    Args:
        id (str):
        body (ConfirmarEntrada): O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que
            a tela deixa mudar. Cada um é validado
            contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as
            opções válidas).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobCriado
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarEntrada,
) -> Response[HTTPValidationError | JobCriado]:
    """Confirmar

    Args:
        id (str):
        body (ConfirmarEntrada): O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que
            a tela deixa mudar. Cada um é validado
            contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as
            opções válidas).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobCriado]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ConfirmarEntrada,
) -> HTTPValidationError | JobCriado | None:
    """Confirmar

    Args:
        id (str):
        body (ConfirmarEntrada): O corpo é a proposta EDITADA (ADR 0005 seção 5): só os campos que
            a tela deixa mudar. Cada um é validado
            contra a proposta gravada dentro da rota (nunca um esquema fixo — a proposta é que dá as
            opções válidas).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobCriado
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
