from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.entrega import Entrega
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    entrega_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/webhooks/{id}/entregas/{entrega_id}/reenviar".format(
            id=quote(str(id), safe=""),
            entrega_id=quote(str(entrega_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Entrega | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = Entrega.from_dict(response.json())

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
) -> Response[Entrega | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    entrega_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Entrega | HTTPValidationError]:
    """Reenviar

     Reenvio manual: a MESMA entrega volta a 'pendente' com o MESMO payload e o MESMO `webhook-id`
    (idempotência no receptor) e um job novo entra na fila (tentativas recomeçam no job; `tentativas`
    da entrega segue acumulando como histórico).

    Args:
        id (str):
        entrega_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Entrega | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        entrega_id=entrega_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    entrega_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Entrega | HTTPValidationError | None:
    """Reenviar

     Reenvio manual: a MESMA entrega volta a 'pendente' com o MESMO payload e o MESMO `webhook-id`
    (idempotência no receptor) e um job novo entra na fila (tentativas recomeçam no job; `tentativas`
    da entrega segue acumulando como histórico).

    Args:
        id (str):
        entrega_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Entrega | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        entrega_id=entrega_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    entrega_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Entrega | HTTPValidationError]:
    """Reenviar

     Reenvio manual: a MESMA entrega volta a 'pendente' com o MESMO payload e o MESMO `webhook-id`
    (idempotência no receptor) e um job novo entra na fila (tentativas recomeçam no job; `tentativas`
    da entrega segue acumulando como histórico).

    Args:
        id (str):
        entrega_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Entrega | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        entrega_id=entrega_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    entrega_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Entrega | HTTPValidationError | None:
    """Reenviar

     Reenvio manual: a MESMA entrega volta a 'pendente' com o MESMO payload e o MESMO `webhook-id`
    (idempotência no receptor) e um job novo entra na fila (tentativas recomeçam no job; `tentativas`
    da entrega segue acumulando como histórico).

    Args:
        id (str):
        entrega_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Entrega | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            entrega_id=entrega_id,
            client=client,
        )
    ).parsed
