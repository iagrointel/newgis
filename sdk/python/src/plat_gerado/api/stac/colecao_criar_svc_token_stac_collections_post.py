from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.colecao_criar_svc_token_stac_collections_post_corpo import ColecaoCriarSvcTokenStacCollectionsPostCorpo
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    token: str,
    *,
    body: ColecaoCriarSvcTokenStacCollectionsPostCorpo,
    slug: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["slug"] = slug

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/svc/{token}/stac/collections".format(
            token=quote(str(token), safe=""),
        ),
        "params": params,
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
    body: ColecaoCriarSvcTokenStacCollectionsPostCorpo,
    slug: str,
) -> Response[Any | HTTPValidationError]:
    """Colecao Criar

    Args:
        token (str):
        slug (str):
        body (ColecaoCriarSvcTokenStacCollectionsPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        body=body,
        slug=slug,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: ColecaoCriarSvcTokenStacCollectionsPostCorpo,
    slug: str,
) -> Any | HTTPValidationError | None:
    """Colecao Criar

    Args:
        token (str):
        slug (str):
        body (ColecaoCriarSvcTokenStacCollectionsPostCorpo):

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
        slug=slug,
    ).parsed


async def asyncio_detailed(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: ColecaoCriarSvcTokenStacCollectionsPostCorpo,
    slug: str,
) -> Response[Any | HTTPValidationError]:
    """Colecao Criar

    Args:
        token (str):
        slug (str):
        body (ColecaoCriarSvcTokenStacCollectionsPostCorpo):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        body=body,
        slug=slug,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    *,
    client: AuthenticatedClient | Client,
    body: ColecaoCriarSvcTokenStacCollectionsPostCorpo,
    slug: str,
) -> Any | HTTPValidationError | None:
    """Colecao Criar

    Args:
        token (str):
        slug (str):
        body (ColecaoCriarSvcTokenStacCollectionsPostCorpo):

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
            slug=slug,
        )
    ).parsed
