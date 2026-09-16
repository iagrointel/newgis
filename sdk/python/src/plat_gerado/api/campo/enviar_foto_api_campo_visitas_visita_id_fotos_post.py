from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.visita_foto_entrada import VisitaFotoEntrada
from ...types import Response


def _get_kwargs(
    visita_id: str,
    *,
    body: VisitaFotoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/campo/visitas/{visita_id}/fotos".format(
            visita_id=quote(str(visita_id), safe=""),
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
    visita_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: VisitaFotoEntrada,
) -> Response[Any | HTTPValidationError]:
    """Enviar Foto

    Args:
        visita_id (str):
        body (VisitaFotoEntrada): Imagem em base64 (mesmo contrato de
            app/catalogo/modelos.py::MiniaturaEntrada — o CSRF sob cookie
            exige application/json; a PWA de campo roda sob a MESMA sessão do navegador, nunca token).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        visita_id=visita_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    visita_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: VisitaFotoEntrada,
) -> Any | HTTPValidationError | None:
    """Enviar Foto

    Args:
        visita_id (str):
        body (VisitaFotoEntrada): Imagem em base64 (mesmo contrato de
            app/catalogo/modelos.py::MiniaturaEntrada — o CSRF sob cookie
            exige application/json; a PWA de campo roda sob a MESMA sessão do navegador, nunca token).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        visita_id=visita_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    visita_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: VisitaFotoEntrada,
) -> Response[Any | HTTPValidationError]:
    """Enviar Foto

    Args:
        visita_id (str):
        body (VisitaFotoEntrada): Imagem em base64 (mesmo contrato de
            app/catalogo/modelos.py::MiniaturaEntrada — o CSRF sob cookie
            exige application/json; a PWA de campo roda sob a MESMA sessão do navegador, nunca token).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        visita_id=visita_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    visita_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: VisitaFotoEntrada,
) -> Any | HTTPValidationError | None:
    """Enviar Foto

    Args:
        visita_id (str):
        body (VisitaFotoEntrada): Imagem em base64 (mesmo contrato de
            app/catalogo/modelos.py::MiniaturaEntrada — o CSRF sob cookie
            exige application/json; a PWA de campo roda sob a MESMA sessão do navegador, nunca token).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            visita_id=visita_id,
            client=client,
            body=body,
        )
    ).parsed
