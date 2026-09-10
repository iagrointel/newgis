from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pagina_auth import PaginaAuth
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    tipo: None | str | Unset = UNSET,
    ator_id: int | None | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tipo: None | str | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    json_ator_id: int | None | Unset
    if isinstance(ator_id, Unset):
        json_ator_id = UNSET
    else:
        json_ator_id = ator_id
    params["ator_id"] = json_ator_id

    json_desde: None | str | Unset
    if isinstance(desde, Unset):
        json_desde = UNSET
    else:
        json_desde = desde
    params["desde"] = json_desde

    json_ate: None | str | Unset
    if isinstance(ate, Unset):
        json_ate = UNSET
    else:
        json_ate = ate
    params["ate"] = json_ate

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
        "url": "/api/eventos",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PaginaAuth | None:
    if response.status_code == 200:
        response_200 = PaginaAuth.from_dict(response.json())

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
) -> Response[HTTPValidationError | PaginaAuth]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    ator_id: int | None | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaAuth]:
    """Eventos

    Args:
        tipo (None | str | Unset):
        ator_id (int | None | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        ator_id=ator_id,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    ator_id: int | None | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | PaginaAuth | None:
    """Eventos

    Args:
        tipo (None | str | Unset):
        ator_id (int | None | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return sync_detailed(
        client=client,
        tipo=tipo,
        ator_id=ator_id,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    ator_id: int | None | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | PaginaAuth]:
    """Eventos

    Args:
        tipo (None | str | Unset):
        ator_id (int | None | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        tipo=tipo,
        ator_id=ator_id,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    ator_id: int | None | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | PaginaAuth | None:
    """Eventos

    Args:
        tipo (None | str | Unset):
        ator_id (int | None | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return (
        await asyncio_detailed(
            client=client,
            tipo=tipo,
            ator_id=ator_id,
            desde=desde,
            ate=ate,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
