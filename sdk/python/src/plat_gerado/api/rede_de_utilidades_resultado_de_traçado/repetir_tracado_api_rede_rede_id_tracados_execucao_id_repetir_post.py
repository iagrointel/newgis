from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    execucao_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/tracados/{execucao_id}/repetir".format(
            rede_id=quote(str(rede_id), safe=""),
            execucao_id=quote(str(execucao_id), safe=""),
        ),
    }

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
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Repetir Tracado

     Roda de novo o pedido guardado, sobre a rede de HOJE. A resposta traz `contagem_anterior` ao lado da
    contagem nova: se a rede mudou desde então, os dois números divergem, e é isso que se quer ver.

    Args:
        rede_id (str):
        execucao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        execucao_id=execucao_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Repetir Tracado

     Roda de novo o pedido guardado, sobre a rede de HOJE. A resposta traz `contagem_anterior` ao lado da
    contagem nova: se a rede mudou desde então, os dois números divergem, e é isso que se quer ver.

    Args:
        rede_id (str):
        execucao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        execucao_id=execucao_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Repetir Tracado

     Roda de novo o pedido guardado, sobre a rede de HOJE. A resposta traz `contagem_anterior` ao lado da
    contagem nova: se a rede mudou desde então, os dois números divergem, e é isso que se quer ver.

    Args:
        rede_id (str):
        execucao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        execucao_id=execucao_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Repetir Tracado

     Roda de novo o pedido guardado, sobre a rede de HOJE. A resposta traz `contagem_anterior` ao lado da
    contagem nova: se a rede mudou desde então, os dois números divergem, e é isso que se quer ver.

    Args:
        rede_id (str):
        execucao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            execucao_id=execucao_id,
            client=client,
        )
    ).parsed
