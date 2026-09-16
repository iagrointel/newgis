from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.apply_edits_entrada import ApplyEditsEntrada
from ...models.apply_edits_resultado import ApplyEditsResultado
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    *,
    body: ApplyEditsEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/applyEdits".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApplyEditsResultado | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApplyEditsResultado.from_dict(response.json())

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
) -> Response[ApplyEditsResultado | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ApplyEditsEntrada,
) -> Response[ApplyEditsResultado | HTTPValidationError]:
    """Apply Edits

     Lote atômico de edição. Síncrono de propósito: o teto é MAX_POR_LOTE operações por tipo e a
    derivação
    é por feição com índice GiST — o caso medido no teste (lote de 5 feições) fecha em dezenas de ms.

    Args:
        rede_id (str):
        body (ApplyEditsEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplyEditsResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ApplyEditsEntrada,
) -> ApplyEditsResultado | HTTPValidationError | None:
    """Apply Edits

     Lote atômico de edição. Síncrono de propósito: o teto é MAX_POR_LOTE operações por tipo e a
    derivação
    é por feição com índice GiST — o caso medido no teste (lote de 5 feições) fecha em dezenas de ms.

    Args:
        rede_id (str):
        body (ApplyEditsEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplyEditsResultado | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ApplyEditsEntrada,
) -> Response[ApplyEditsResultado | HTTPValidationError]:
    """Apply Edits

     Lote atômico de edição. Síncrono de propósito: o teto é MAX_POR_LOTE operações por tipo e a
    derivação
    é por feição com índice GiST — o caso medido no teste (lote de 5 feições) fecha em dezenas de ms.

    Args:
        rede_id (str):
        body (ApplyEditsEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApplyEditsResultado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ApplyEditsEntrada,
) -> ApplyEditsResultado | HTTPValidationError | None:
    """Apply Edits

     Lote atômico de edição. Síncrono de propósito: o teto é MAX_POR_LOTE operações por tipo e a
    derivação
    é por feição com índice GiST — o caso medido no teste (lote de 5 feições) fecha em dezenas de ms.

    Args:
        rede_id (str):
        body (ApplyEditsEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApplyEditsResultado | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            body=body,
        )
    ).parsed
