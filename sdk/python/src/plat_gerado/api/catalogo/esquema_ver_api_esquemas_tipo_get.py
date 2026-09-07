from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    tipo: str,
    *,
    versao: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_versao: int | None | Unset
    if isinstance(versao, Unset):
        json_versao = UNSET
    else:
        json_versao = versao
    params["versao"] = json_versao

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/esquemas/{tipo}".format(
            tipo=quote(str(tipo), safe=""),
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
    tipo: str,
    *,
    client: AuthenticatedClient | Client,
    versao: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Esquema Ver

    Args:
        tipo (str):
        versao (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        versao=versao,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    tipo: str,
    *,
    client: AuthenticatedClient | Client,
    versao: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Esquema Ver

    Args:
        tipo (str):
        versao (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        tipo=tipo,
        client=client,
        versao=versao,
    ).parsed


async def asyncio_detailed(
    tipo: str,
    *,
    client: AuthenticatedClient | Client,
    versao: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Esquema Ver

    Args:
        tipo (str):
        versao (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        versao=versao,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    tipo: str,
    *,
    client: AuthenticatedClient | Client,
    versao: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Esquema Ver

    Args:
        tipo (str):
        versao (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            tipo=tipo,
            client=client,
            versao=versao,
        )
    ).parsed
