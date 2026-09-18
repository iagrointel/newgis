from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.modelo_galeria import ModeloGaleria
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    escopo: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_escopo: None | str | Unset
    if isinstance(escopo, Unset):
        json_escopo = UNSET
    else:
        json_escopo = escopo
    params["escopo"] = json_escopo

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/modelos",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[ModeloGaleria] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ModeloGaleria.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[ModeloGaleria]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    escopo: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | list[ModeloGaleria]]:
    """Listar Modelos

     Modelos do próprio inquilino e os de escopo `plataforma` (a política de linha da tabela é quem
    decide; a rota não filtra por inquilino à mão).

    Args:
        escopo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ModeloGaleria]]
    """

    kwargs = _get_kwargs(
        escopo=escopo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    escopo: None | str | Unset = UNSET,
) -> HTTPValidationError | list[ModeloGaleria] | None:
    """Listar Modelos

     Modelos do próprio inquilino e os de escopo `plataforma` (a política de linha da tabela é quem
    decide; a rota não filtra por inquilino à mão).

    Args:
        escopo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ModeloGaleria]
    """

    return sync_detailed(
        client=client,
        escopo=escopo,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    escopo: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | list[ModeloGaleria]]:
    """Listar Modelos

     Modelos do próprio inquilino e os de escopo `plataforma` (a política de linha da tabela é quem
    decide; a rota não filtra por inquilino à mão).

    Args:
        escopo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ModeloGaleria]]
    """

    kwargs = _get_kwargs(
        escopo=escopo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    escopo: None | str | Unset = UNSET,
) -> HTTPValidationError | list[ModeloGaleria] | None:
    """Listar Modelos

     Modelos do próprio inquilino e os de escopo `plataforma` (a política de linha da tabela é quem
    decide; a rota não filtra por inquilino à mão).

    Args:
        escopo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ModeloGaleria]
    """

    return (
        await asyncio_detailed(
            client=client,
            escopo=escopo,
        )
    ).parsed
