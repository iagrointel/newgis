from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.uniao_entrada import UniaoEntrada
from ...models.unir_feicoes_api_camadas_id_feicoes_unir_post_response_unir_feicoes_api_camadas_id_feicoes_unir_post import (
    UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost,
)
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: UniaoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/feicoes/unir".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost | None:
    if response.status_code == 200:
        response_200 = UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost.from_dict(
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
    HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost
]:
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
    body: UniaoEntrada,
) -> Response[
    HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost
]:
    """Unir Feicoes

    Args:
        id (str):
        body (UniaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UniaoEntrada,
) -> HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost | None:
    """Unir Feicoes

    Args:
        id (str):
        body (UniaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UniaoEntrada,
) -> Response[
    HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost
]:
    """Unir Feicoes

    Args:
        id (str):
        body (UniaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: UniaoEntrada,
) -> HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost | None:
    """Unir Feicoes

    Args:
        id (str):
        body (UniaoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UnirFeicoesApiCamadasIdFeicoesUnirPostResponseUnirFeicoesApiCamadasIdFeicoesUnirPost
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
