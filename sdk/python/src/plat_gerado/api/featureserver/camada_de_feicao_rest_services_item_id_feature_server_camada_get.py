from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    camada: int,
    *,
    f: str | Unset = "json",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["f"] = f

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/rest/services/{item_id}/FeatureServer/{camada}".format(
            item_id=quote(str(item_id), safe=""),
            camada=quote(str(camada), safe=""),
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
    item_id: str,
    camada: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "json",
) -> Response[Any | HTTPValidationError]:
    """Camada De Feicao

     Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice
    diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número.

    Args:
        item_id (str):
        camada (int):
        f (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        camada=camada,
        f=f,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    camada: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "json",
) -> Any | HTTPValidationError | None:
    """Camada De Feicao

     Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice
    diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número.

    Args:
        item_id (str):
        camada (int):
        f (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        camada=camada,
        client=client,
        f=f,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    camada: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "json",
) -> Response[Any | HTTPValidationError]:
    """Camada De Feicao

     Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice
    diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número.

    Args:
        item_id (str):
        camada (int):
        f (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        camada=camada,
        f=f,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    camada: int,
    *,
    client: AuthenticatedClient | Client,
    f: str | Unset = "json",
) -> Any | HTTPValidationError | None:
    """Camada De Feicao

     Só a camada 0 existe: um item de catálogo `camada_vetorial` é UMA tabela (ADR 0005). Índice
    diferente
    de 0 responde 404 em vez de devolver a mesma camada com outro número.

    Args:
        item_id (str):
        camada (int):
        f (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            camada=camada,
            client=client,
            f=f,
        )
    ).parsed
