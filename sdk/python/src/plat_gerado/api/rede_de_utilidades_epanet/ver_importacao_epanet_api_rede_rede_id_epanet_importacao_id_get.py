from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.epanet_importacao import EpanetImportacao
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    importacao_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/epanet/{importacao_id}".format(
            rede_id=quote(str(rede_id), safe=""),
            importacao_id=quote(str(importacao_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EpanetImportacao | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EpanetImportacao.from_dict(response.json())

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
) -> Response[EpanetImportacao | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    importacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[EpanetImportacao | HTTPValidationError]:
    """Ver Importacao Epanet

    Args:
        rede_id (str):
        importacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpanetImportacao | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        importacao_id=importacao_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    importacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> EpanetImportacao | HTTPValidationError | None:
    """Ver Importacao Epanet

    Args:
        rede_id (str):
        importacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpanetImportacao | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        importacao_id=importacao_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    importacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[EpanetImportacao | HTTPValidationError]:
    """Ver Importacao Epanet

    Args:
        rede_id (str):
        importacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpanetImportacao | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        importacao_id=importacao_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    importacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> EpanetImportacao | HTTPValidationError | None:
    """Ver Importacao Epanet

    Args:
        rede_id (str):
        importacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpanetImportacao | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            importacao_id=importacao_id,
            client=client,
        )
    ).parsed
