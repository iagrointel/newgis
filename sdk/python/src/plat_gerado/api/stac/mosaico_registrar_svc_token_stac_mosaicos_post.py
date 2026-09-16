from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mosaico_registrar_svc_token_stac_mosaicos_post_corpo import MosaicoRegistrarSvcTokenStacMosaicosPostCorpo
from ...types import Response


def _get_kwargs(
    token: str,
    *,
    body: MosaicoRegistrarSvcTokenStacMosaicosPostCorpo,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/svc/{token}/stac/mosaicos".format(
            token=quote(str(token), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: MosaicoRegistrarSvcTokenStacMosaicosPostCorpo,
) -> Response[Any | HTTPValidationError]:
    """registra um mosaico (busca STAC nomeada; item L1-07)

    Args:
        token (str):
        body (MosaicoRegistrarSvcTokenStacMosaicosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: MosaicoRegistrarSvcTokenStacMosaicosPostCorpo,
) -> Any | HTTPValidationError | None:
    """registra um mosaico (busca STAC nomeada; item L1-07)

    Args:
        token (str):
        body (MosaicoRegistrarSvcTokenStacMosaicosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: MosaicoRegistrarSvcTokenStacMosaicosPostCorpo,
) -> Response[Any | HTTPValidationError]:
    """registra um mosaico (busca STAC nomeada; item L1-07)

    Args:
        token (str):
        body (MosaicoRegistrarSvcTokenStacMosaicosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: MosaicoRegistrarSvcTokenStacMosaicosPostCorpo,
) -> Any | HTTPValidationError | None:
    """registra um mosaico (busca STAC nomeada; item L1-07)

    Args:
        token (str):
        body (MosaicoRegistrarSvcTokenStacMosaicosPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            client=client,
            body=body,
        )
    ).parsed
