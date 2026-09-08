from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.convite_membro import ConviteMembro
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
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
        "url": "/api/convites",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[ConviteMembro] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ConviteMembro.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[ConviteMembro]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | list[ConviteMembro]]:
    """Listar

    Args:
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ConviteMembro]]
    """

    kwargs = _get_kwargs(
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
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | list[ConviteMembro] | None:
    """Listar

    Args:
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ConviteMembro]
    """

    return sync_detailed(
        client=client,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> Response[HTTPValidationError | list[ConviteMembro]]:
    """Listar

    Args:
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ConviteMembro]]
    """

    kwargs = _get_kwargs(
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
) -> HTTPValidationError | list[ConviteMembro] | None:
    """Listar

    Args:
        limite (int | None | Unset):
        deslocamento (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ConviteMembro]
    """

    return (
        await asyncio_detailed(
            client=client,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
