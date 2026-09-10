from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.versao_completa import VersaoCompleta
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    n: int,
    *,
    diff_de: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_diff_de: int | None | Unset
    if isinstance(diff_de, Unset):
        json_diff_de = UNSET
    else:
        json_diff_de = diff_de
    params["diff_de"] = json_diff_de

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/versoes/{n}".format(
            id=quote(str(id), safe=""),
            n=quote(str(n), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | VersaoCompleta | None:
    if response.status_code == 200:
        response_200 = VersaoCompleta.from_dict(response.json())

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
) -> Response[HTTPValidationError | VersaoCompleta]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    n: int,
    *,
    client: AuthenticatedClient | Client,
    diff_de: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | VersaoCompleta]:
    """Versao

    Args:
        id (str):
        n (int):
        diff_de (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | VersaoCompleta]
    """

    kwargs = _get_kwargs(
        id=id,
        n=n,
        diff_de=diff_de,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    n: int,
    *,
    client: AuthenticatedClient | Client,
    diff_de: int | None | Unset = UNSET,
) -> HTTPValidationError | VersaoCompleta | None:
    """Versao

    Args:
        id (str):
        n (int):
        diff_de (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | VersaoCompleta
    """

    return sync_detailed(
        id=id,
        n=n,
        client=client,
        diff_de=diff_de,
    ).parsed


async def asyncio_detailed(
    id: str,
    n: int,
    *,
    client: AuthenticatedClient | Client,
    diff_de: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | VersaoCompleta]:
    """Versao

    Args:
        id (str):
        n (int):
        diff_de (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | VersaoCompleta]
    """

    kwargs = _get_kwargs(
        id=id,
        n=n,
        diff_de=diff_de,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    n: int,
    *,
    client: AuthenticatedClient | Client,
    diff_de: int | None | Unset = UNSET,
) -> HTTPValidationError | VersaoCompleta | None:
    """Versao

    Args:
        id (str):
        n (int):
        diff_de (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | VersaoCompleta
    """

    return (
        await asyncio_detailed(
            id=id,
            n=n,
            client=client,
            diff_de=diff_de,
        )
    ).parsed
