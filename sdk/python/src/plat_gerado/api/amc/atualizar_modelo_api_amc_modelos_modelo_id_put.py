from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.modelo_entrada_amc import ModeloEntradaAmc
from ...types import Response


def _get_kwargs(
    modelo_id: str,
    *,
    body: ModeloEntradaAmc,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/amc/modelos/{modelo_id}".format(
            modelo_id=quote(str(modelo_id), safe=""),
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
    modelo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ModeloEntradaAmc,
) -> Response[Any | HTTPValidationError]:
    """Atualizar Modelo

     Edita: grava versão NOVA e move a cabeça. A versão anterior fica; execução que a usou não muda de
    resultado.

    Args:
        modelo_id (str):
        body (ModeloEntradaAmc):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        modelo_id=modelo_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    modelo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ModeloEntradaAmc,
) -> Any | HTTPValidationError | None:
    """Atualizar Modelo

     Edita: grava versão NOVA e move a cabeça. A versão anterior fica; execução que a usou não muda de
    resultado.

    Args:
        modelo_id (str):
        body (ModeloEntradaAmc):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        modelo_id=modelo_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    modelo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ModeloEntradaAmc,
) -> Response[Any | HTTPValidationError]:
    """Atualizar Modelo

     Edita: grava versão NOVA e move a cabeça. A versão anterior fica; execução que a usou não muda de
    resultado.

    Args:
        modelo_id (str):
        body (ModeloEntradaAmc):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        modelo_id=modelo_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    modelo_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ModeloEntradaAmc,
) -> Any | HTTPValidationError | None:
    """Atualizar Modelo

     Edita: grava versão NOVA e move a cabeça. A versão anterior fica; execução que a usou não muda de
    resultado.

    Args:
        modelo_id (str):
        body (ModeloEntradaAmc):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            modelo_id=modelo_id,
            client=client,
            body=body,
        )
    ).parsed
