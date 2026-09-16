from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.execucao import Execucao
from ...models.execucao_entrada import ExecucaoEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: ExecucaoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/multiescala/execucoes/{id}/micro".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Execucao | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = Execucao.from_dict(response.json())

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
) -> Response[Execucao | HTTPValidationError]:
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
    body: ExecucaoEntrada,
) -> Response[Execucao | HTTPValidationError]:
    """Executar Micro

     Gera a grade micro SÓ dentro das regiões aprovadas pela execução macro `id` e executa a combinação —
    a
    segunda das 'duas execuções ligadas'. Célula micro fora das regiões macro nunca é gerada
    (aritmético, não
    filtrado depois): é a cláusula central do portão.

    Args:
        id (str):
        body (ExecucaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Execucao | HTTPValidationError]
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
    body: ExecucaoEntrada,
) -> Execucao | HTTPValidationError | None:
    """Executar Micro

     Gera a grade micro SÓ dentro das regiões aprovadas pela execução macro `id` e executa a combinação —
    a
    segunda das 'duas execuções ligadas'. Célula micro fora das regiões macro nunca é gerada
    (aritmético, não
    filtrado depois): é a cláusula central do portão.

    Args:
        id (str):
        body (ExecucaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Execucao | HTTPValidationError
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
    body: ExecucaoEntrada,
) -> Response[Execucao | HTTPValidationError]:
    """Executar Micro

     Gera a grade micro SÓ dentro das regiões aprovadas pela execução macro `id` e executa a combinação —
    a
    segunda das 'duas execuções ligadas'. Célula micro fora das regiões macro nunca é gerada
    (aritmético, não
    filtrado depois): é a cláusula central do portão.

    Args:
        id (str):
        body (ExecucaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Execucao | HTTPValidationError]
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
    body: ExecucaoEntrada,
) -> Execucao | HTTPValidationError | None:
    """Executar Micro

     Gera a grade micro SÓ dentro das regiões aprovadas pela execução macro `id` e executa a combinação —
    a
    segunda das 'duas execuções ligadas'. Célula micro fora das regiões macro nunca é gerada
    (aritmético, não
    filtrado depois): é a cláusula central do portão.

    Args:
        id (str):
        body (ExecucaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Execucao | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
