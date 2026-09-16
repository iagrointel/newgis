from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.credencial_entrada import CredencialEntrada
from ...models.credencial_saida import CredencialSaida
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CredencialEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/agol/credencial",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CredencialSaida | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CredencialSaida.from_dict(response.json())

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
) -> Response[CredencialSaida | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CredencialEntrada,
) -> Response[CredencialSaida | HTTPValidationError]:
    """Credencial Gravar

    Args:
        body (CredencialEntrada): PUT /api/agol/credencial (mesmo desenho de
            `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
            (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo;
            `remover_credencial=true` apaga
            a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é
            informada,
            `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem
            usuário).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredencialSaida | HTTPValidationError]
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
    body: CredencialEntrada,
) -> CredencialSaida | HTTPValidationError | None:
    """Credencial Gravar

    Args:
        body (CredencialEntrada): PUT /api/agol/credencial (mesmo desenho de
            `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
            (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo;
            `remover_credencial=true` apaga
            a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é
            informada,
            `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem
            usuário).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredencialSaida | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CredencialEntrada,
) -> Response[CredencialSaida | HTTPValidationError]:
    """Credencial Gravar

    Args:
        body (CredencialEntrada): PUT /api/agol/credencial (mesmo desenho de
            `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
            (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo;
            `remover_credencial=true` apaga
            a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é
            informada,
            `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem
            usuário).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CredencialSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CredencialEntrada,
) -> CredencialSaida | HTTPValidationError | None:
    """Credencial Gravar

    Args:
        body (CredencialEntrada): PUT /api/agol/credencial (mesmo desenho de
            `app.conexao.modelos.ConexaoEditar`): `credencial` ausente
            (None) preserva a cifra já guardada, só atualizando portal/usuario/rotulo;
            `remover_credencial=true` apaga
            a credencial cifrada (e o `tipo`) sem apagar portal/usuario/rotulo. Quando `credencial` é
            informada,
            `tipo` é obrigatório ('senha', pareada com `usuario`, ou 'token', de longa duração, sem
            usuário).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CredencialSaida | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
