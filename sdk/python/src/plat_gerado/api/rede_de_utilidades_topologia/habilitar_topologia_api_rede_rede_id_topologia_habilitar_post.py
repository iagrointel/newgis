from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.topologia_resumo import TopologiaResumo
from ...types import Response


def _get_kwargs(
    rede_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/topologia/habilitar".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TopologiaResumo | None:
    if response.status_code == 201:
        response_201 = TopologiaResumo.from_dict(response.json())

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
) -> Response[HTTPValidationError | TopologiaResumo]:
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
) -> Response[HTTPValidationError | TopologiaResumo]:
    """Habilitar Topologia

     Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com
    as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TopologiaResumo]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | TopologiaResumo | None:
    """Habilitar Topologia

     Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com
    as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TopologiaResumo
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | TopologiaResumo]:
    """Habilitar Topologia

     Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com
    as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TopologiaResumo]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | TopologiaResumo | None:
    """Habilitar Topologia

     Reconstrói a topologia INTEIRA da rede a partir das feições atuais. Idempotente (chamar de novo com
    as
    mesmas feições dá o mesmo resultado); substitui qualquer topologia anterior, nunca soma.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TopologiaResumo
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
        )
    ).parsed
