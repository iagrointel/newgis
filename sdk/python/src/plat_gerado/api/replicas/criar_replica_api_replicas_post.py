from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.criar_replica_api_replicas_post_response_criar_replica_api_replicas_post import (
    CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.replica_entrada import ReplicaEntrada
from ...types import Response


def _get_kwargs(
    *,
    body: ReplicaEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/replicas",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost.from_dict(response.json())

        return response_202

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ReplicaEntrada,
) -> Response[CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError]:
    """Criar Replica

    Args:
        body (ReplicaEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: ReplicaEntrada,
) -> CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError | None:
    """Criar Replica

    Args:
        body (ReplicaEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ReplicaEntrada,
) -> Response[CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError]:
    """Criar Replica

    Args:
        body (ReplicaEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ReplicaEntrada,
) -> CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError | None:
    """Criar Replica

    Args:
        body (ReplicaEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CriarReplicaApiReplicasPostResponseCriarReplicaApiReplicasPost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
