from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.smtp_entrada import SMTPEntrada
from ...models.smtp_saida import SMTPSaida
from ...types import Response


def _get_kwargs(
    *,
    body: SMTPEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/org/smtp",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SMTPSaida | None:
    if response.status_code == 200:
        response_200 = SMTPSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | SMTPSaida]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SMTPEntrada,
) -> Response[HTTPValidationError | SMTPSaida]:
    """Smtp Gravar

    Args:
        body (SMTPEntrada): PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""`
            (string vazia) apaga a senha
            guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a
            usar a
            instalação, se houver, ou o caminho manual).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SMTPSaida]
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
    body: SMTPEntrada,
) -> HTTPValidationError | SMTPSaida | None:
    """Smtp Gravar

    Args:
        body (SMTPEntrada): PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""`
            (string vazia) apaga a senha
            guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a
            usar a
            instalação, se houver, ou o caminho manual).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SMTPSaida
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SMTPEntrada,
) -> Response[HTTPValidationError | SMTPSaida]:
    """Smtp Gravar

    Args:
        body (SMTPEntrada): PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""`
            (string vazia) apaga a senha
            guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a
            usar a
            instalação, se houver, ou o caminho manual).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SMTPSaida]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: SMTPEntrada,
) -> HTTPValidationError | SMTPSaida | None:
    """Smtp Gravar

    Args:
        body (SMTPEntrada): PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""`
            (string vazia) apaga a senha
            guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a
            usar a
            instalação, se houver, ou o caminho manual).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SMTPSaida
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
