from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_adicionar_entrada import AcervoAdicionarEntrada
from ...models.http_validation_error import HTTPValidationError
from ...models.item import Item
from ...types import UNSET, Response, Unset


def _get_kwargs(
    fonte_id: str,
    *,
    body: AcervoAdicionarEntrada | None | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/acervo/{fonte_id}/adicionar".format(
            fonte_id=quote(str(fonte_id), safe=""),
        ),
    }

    if isinstance(body, AcervoAdicionarEntrada):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | Item | None:
    if response.status_code == 201:
        response_201 = Item.from_dict(response.json())

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
) -> Response[HTTPValidationError | Item]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAdicionarEntrada | None | Unset = UNSET,
) -> Response[HTTPValidationError | Item]:
    """Adicionar

    Args:
        fonte_id (str):
        body (AcervoAdicionarEntrada | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        fonte_id=fonte_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAdicionarEntrada | None | Unset = UNSET,
) -> HTTPValidationError | Item | None:
    """Adicionar

    Args:
        fonte_id (str):
        body (AcervoAdicionarEntrada | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return sync_detailed(
        fonte_id=fonte_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAdicionarEntrada | None | Unset = UNSET,
) -> Response[HTTPValidationError | Item]:
    """Adicionar

    Args:
        fonte_id (str):
        body (AcervoAdicionarEntrada | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | Item]
    """

    kwargs = _get_kwargs(
        fonte_id=fonte_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    fonte_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAdicionarEntrada | None | Unset = UNSET,
) -> HTTPValidationError | Item | None:
    """Adicionar

    Args:
        fonte_id (str):
        body (AcervoAdicionarEntrada | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | Item
    """

    return (
        await asyncio_detailed(
            fonte_id=fonte_id,
            client=client,
            body=body,
        )
    ).parsed
