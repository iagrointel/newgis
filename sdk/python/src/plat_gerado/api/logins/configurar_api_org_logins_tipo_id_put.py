from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.login_provedor import LoginProvedor
from ...models.login_provedor_entrada import LoginProvedorEntrada
from ...types import Response


def _get_kwargs(
    tipo: str,
    id: int,
    *,
    body: LoginProvedorEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/org/logins/{tipo}/{id}".format(
            tipo=quote(str(tipo), safe=""),
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | LoginProvedor | None:
    if response.status_code == 200:
        response_200 = LoginProvedor.from_dict(response.json())

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
) -> Response[HTTPValidationError | LoginProvedor]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    tipo: str,
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoginProvedorEntrada,
) -> Response[HTTPValidationError | LoginProvedor]:
    """Configurar

     Rótulo, ordem, habilitação e regras de provisionamento de um provedor; para `ldap` o id é o do
    inquilino
    (único). Papel e grupos citados têm de existir neste inquilino (422 nomeando o que falta).

    Args:
        tipo (str):
        id (int):
        body (LoginProvedorEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LoginProvedor]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    tipo: str,
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoginProvedorEntrada,
) -> HTTPValidationError | LoginProvedor | None:
    """Configurar

     Rótulo, ordem, habilitação e regras de provisionamento de um provedor; para `ldap` o id é o do
    inquilino
    (único). Papel e grupos citados têm de existir neste inquilino (422 nomeando o que falta).

    Args:
        tipo (str):
        id (int):
        body (LoginProvedorEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LoginProvedor
    """

    return sync_detailed(
        tipo=tipo,
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    tipo: str,
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoginProvedorEntrada,
) -> Response[HTTPValidationError | LoginProvedor]:
    """Configurar

     Rótulo, ordem, habilitação e regras de provisionamento de um provedor; para `ldap` o id é o do
    inquilino
    (único). Papel e grupos citados têm de existir neste inquilino (422 nomeando o que falta).

    Args:
        tipo (str):
        id (int):
        body (LoginProvedorEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | LoginProvedor]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    tipo: str,
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: LoginProvedorEntrada,
) -> HTTPValidationError | LoginProvedor | None:
    """Configurar

     Rótulo, ordem, habilitação e regras de provisionamento de um provedor; para `ldap` o id é o do
    inquilino
    (único). Papel e grupos citados têm de existir neste inquilino (422 nomeando o que falta).

    Args:
        tipo (str):
        id (int):
        body (LoginProvedorEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | LoginProvedor
    """

    return (
        await asyncio_detailed(
            tipo=tipo,
            id=id,
            client=client,
            body=body,
        )
    ).parsed
