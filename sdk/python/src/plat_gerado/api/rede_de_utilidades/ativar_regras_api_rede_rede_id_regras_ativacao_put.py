from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ativacao_entrada import AtivacaoEntrada
from ...models.ativacao_resultado import AtivacaoResultado
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    *,
    body: AtivacaoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/rede/{rede_id}/regras/ativacao".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AtivacaoResultado | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AtivacaoResultado.from_dict(response.json())

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
) -> Response[AtivacaoResultado | HTTPValidationError]:
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
    body: AtivacaoEntrada,
) -> Response[AtivacaoResultado | HTTPValidationError]:
    """Ativar Regras

     Liga/desliga a avaliação de regras no applyEdits (a comporta de carga em massa). O padrão é LIGADA:
    'sem regra = proibido'. Desligar não apaga regra nem conexão — só grava as conexões novas com
    regra_id NULL; a validação em lote continua avaliando tudo contra o conjunto vigente.

    Args:
        rede_id (str):
        body (AtivacaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AtivacaoResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivacaoEntrada,
) -> AtivacaoResultado | HTTPValidationError | None:
    """Ativar Regras

     Liga/desliga a avaliação de regras no applyEdits (a comporta de carga em massa). O padrão é LIGADA:
    'sem regra = proibido'. Desligar não apaga regra nem conexão — só grava as conexões novas com
    regra_id NULL; a validação em lote continua avaliando tudo contra o conjunto vigente.

    Args:
        rede_id (str):
        body (AtivacaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AtivacaoResultado | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivacaoEntrada,
) -> Response[AtivacaoResultado | HTTPValidationError]:
    """Ativar Regras

     Liga/desliga a avaliação de regras no applyEdits (a comporta de carga em massa). O padrão é LIGADA:
    'sem regra = proibido'. Desligar não apaga regra nem conexão — só grava as conexões novas com
    regra_id NULL; a validação em lote continua avaliando tudo contra o conjunto vigente.

    Args:
        rede_id (str):
        body (AtivacaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AtivacaoResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivacaoEntrada,
) -> AtivacaoResultado | HTTPValidationError | None:
    """Ativar Regras

     Liga/desliga a avaliação de regras no applyEdits (a comporta de carga em massa). O padrão é LIGADA:
    'sem regra = proibido'. Desligar não apaga regra nem conexão — só grava as conexões novas com
    regra_id NULL; a validação em lote continua avaliando tudo contra o conjunto vigente.

    Args:
        rede_id (str):
        body (AtivacaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AtivacaoResultado | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            body=body,
        )
    ).parsed
