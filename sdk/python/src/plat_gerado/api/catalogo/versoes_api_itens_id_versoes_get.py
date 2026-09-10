from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pagina_catalogo import PaginaCatalogo
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    json_deslocamento: int | None | Unset
    if isinstance(deslocamento, Unset):
        json_deslocamento = UNSET
    else:
        json_deslocamento = deslocamento
    params["deslocamento"] = json_deslocamento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/versoes".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PaginaCatalogo | None:
    if response.status_code == 200:
        response_200 = PaginaCatalogo.from_dict(response.json())

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
) -> Response[HTTPValidationError | PaginaCatalogo]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Versoes

    Args:
        id (str):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaCatalogo]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Versoes

    Args:
        id (str):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaCatalogo
    """

    return sync_detailed(
        id=id,
        client=client,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaCatalogo]:
    """Versoes

    Args:
        id (str):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaCatalogo]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | PaginaCatalogo | None:
    """Versoes

    Args:
        id (str):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaCatalogo
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
