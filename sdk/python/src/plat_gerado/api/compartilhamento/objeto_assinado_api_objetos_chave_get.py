from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    chave: str,
    *,
    ate: int | Unset = 0,
    assinatura: str | Unset = "",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["ate"] = ate

    params["assinatura"] = assinatura

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/objetos/{chave}".format(
            chave=quote(str(chave), safe=""),
        ),
        "params": params,
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
    chave: str,
    *,
    client: AuthenticatedClient | Client,
    ate: int | Unset = 0,
    assinatura: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Objeto Assinado

    Args:
        chave (str):
        ate (int | Unset):  Default: 0.
        assinatura (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        chave=chave,
        ate=ate,
        assinatura=assinatura,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    chave: str,
    *,
    client: AuthenticatedClient | Client,
    ate: int | Unset = 0,
    assinatura: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Objeto Assinado

    Args:
        chave (str):
        ate (int | Unset):  Default: 0.
        assinatura (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        chave=chave,
        client=client,
        ate=ate,
        assinatura=assinatura,
    ).parsed


async def asyncio_detailed(
    chave: str,
    *,
    client: AuthenticatedClient | Client,
    ate: int | Unset = 0,
    assinatura: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Objeto Assinado

    Args:
        chave (str):
        ate (int | Unset):  Default: 0.
        assinatura (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        chave=chave,
        ate=ate,
        assinatura=assinatura,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    chave: str,
    *,
    client: AuthenticatedClient | Client,
    ate: int | Unset = 0,
    assinatura: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Objeto Assinado

    Args:
        chave (str):
        ate (int | Unset):  Default: 0.
        assinatura (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            chave=chave,
            client=client,
            ate=ate,
            assinatura=assinatura,
        )
    ).parsed
