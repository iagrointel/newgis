from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.resolver_api_camadas_id_versoes_versao_conflitos_globalid_resolver_post_response_resolver_api_camadas_id_versoes_versao_conflitos_globalid_resolver_post import (
    ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost,
)
from ...models.resolver_entrada import ResolverEntrada
from ...types import Response


def _get_kwargs(
    id: str,
    versao: str,
    globalid: str,
    *,
    body: ResolverEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/versoes/{versao}/conflitos/{globalid}/resolver".format(
            id=quote(str(id), safe=""),
            versao=quote(str(versao), safe=""),
            globalid=quote(str(globalid), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
    | None
):
    if response.status_code == 200:
        response_200 = ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost.from_dict(
            response.json()
        )

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
) -> Response[
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    versao: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: ResolverEntrada,
) -> Response[
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
]:
    """Resolver

    Args:
        id (str):
        versao (str):
        globalid (str):
        body (ResolverEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost]
    """

    kwargs = _get_kwargs(
        id=id,
        versao=versao,
        globalid=globalid,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    versao: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: ResolverEntrada,
) -> (
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
    | None
):
    """Resolver

    Args:
        id (str):
        versao (str):
        globalid (str):
        body (ResolverEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
    """

    return sync_detailed(
        id=id,
        versao=versao,
        globalid=globalid,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    versao: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: ResolverEntrada,
) -> Response[
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
]:
    """Resolver

    Args:
        id (str):
        versao (str):
        globalid (str):
        body (ResolverEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost]
    """

    kwargs = _get_kwargs(
        id=id,
        versao=versao,
        globalid=globalid,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    versao: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: ResolverEntrada,
) -> (
    HTTPValidationError
    | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
    | None
):
    """Resolver

    Args:
        id (str):
        versao (str):
        globalid (str):
        body (ResolverEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPostResponseResolverApiCamadasIdVersoesVersaoConflitosGlobalidResolverPost
    """

    return (
        await asyncio_detailed(
            id=id,
            versao=versao,
            globalid=globalid,
            client=client,
            body=body,
        )
    ).parsed
