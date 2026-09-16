from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.provedor_saml_entrada import ProvedorSamlEntrada
from ...models.provedor_saml_saida import ProvedorSamlSaida
from ...types import Response


def _get_kwargs(
    provedor_id: int,
    *,
    body: ProvedorSamlEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/org/saml/{provedor_id}".format(
            provedor_id=quote(str(provedor_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProvedorSamlSaida | None:
    if response.status_code == 200:
        response_200 = ProvedorSamlSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProvedorSamlSaida]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    provedor_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: ProvedorSamlEntrada,
) -> Response[HTTPValidationError | ProvedorSamlSaida]:
    """Org Saml Atualizar

    Args:
        provedor_id (int):
        body (ProvedorSamlEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProvedorSamlSaida]
    """

    kwargs = _get_kwargs(
        provedor_id=provedor_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    provedor_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: ProvedorSamlEntrada,
) -> HTTPValidationError | ProvedorSamlSaida | None:
    """Org Saml Atualizar

    Args:
        provedor_id (int):
        body (ProvedorSamlEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProvedorSamlSaida
    """

    return sync_detailed(
        provedor_id=provedor_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    provedor_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: ProvedorSamlEntrada,
) -> Response[HTTPValidationError | ProvedorSamlSaida]:
    """Org Saml Atualizar

    Args:
        provedor_id (int):
        body (ProvedorSamlEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProvedorSamlSaida]
    """

    kwargs = _get_kwargs(
        provedor_id=provedor_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    provedor_id: int,
    *,
    client: AuthenticatedClient | Client,
    body: ProvedorSamlEntrada,
) -> HTTPValidationError | ProvedorSamlSaida | None:
    """Org Saml Atualizar

    Args:
        provedor_id (int):
        body (ProvedorSamlEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProvedorSamlSaida
    """

    return (
        await asyncio_detailed(
            provedor_id=provedor_id,
            client=client,
            body=body,
        )
    ).parsed
