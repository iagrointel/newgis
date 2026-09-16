from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tenant_cotas_entrada import TenantCotasEntrada
from ...types import Response


def _get_kwargs(
    id: int,
    *,
    body: TenantCotasEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/plataforma/inquilinos/{id}/cotas".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: TenantCotasEntrada,
) -> Response[Any | HTTPValidationError]:
    """Cotas Definir

     Único caminho HTTP que move o TETO de cota (cota_bytes_teto/cota_usuarios_teto) — o que o inquilino
    edita sozinho por PUT /api/org nunca ultrapassa (item L0-07-c-cotas-uso). Efeito imediato:
    plat.cota_*
    e plat.tenant.cota_bytes são lidos ao vivo em cada requisição, sem cache (mesmo contrato de PUT
    /api/org).

    Args:
        id (int):
        body (TenantCotasEntrada): POST /api/plataforma/inquilinos/{id}/cotas (só superadmin; item
            L0-07-c-cotas-uso): todo campo é
            opcional — só o que vier não-None muda. cota_bytes_teto/cota_usuarios_teto são o TETO que
            o próprio
            inquilino (PUT /api/org) nunca ultrapassa; sem valor aqui o teto vigente não muda.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: TenantCotasEntrada,
) -> Any | HTTPValidationError | None:
    """Cotas Definir

     Único caminho HTTP que move o TETO de cota (cota_bytes_teto/cota_usuarios_teto) — o que o inquilino
    edita sozinho por PUT /api/org nunca ultrapassa (item L0-07-c-cotas-uso). Efeito imediato:
    plat.cota_*
    e plat.tenant.cota_bytes são lidos ao vivo em cada requisição, sem cache (mesmo contrato de PUT
    /api/org).

    Args:
        id (int):
        body (TenantCotasEntrada): POST /api/plataforma/inquilinos/{id}/cotas (só superadmin; item
            L0-07-c-cotas-uso): todo campo é
            opcional — só o que vier não-None muda. cota_bytes_teto/cota_usuarios_teto são o TETO que
            o próprio
            inquilino (PUT /api/org) nunca ultrapassa; sem valor aqui o teto vigente não muda.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: TenantCotasEntrada,
) -> Response[Any | HTTPValidationError]:
    """Cotas Definir

     Único caminho HTTP que move o TETO de cota (cota_bytes_teto/cota_usuarios_teto) — o que o inquilino
    edita sozinho por PUT /api/org nunca ultrapassa (item L0-07-c-cotas-uso). Efeito imediato:
    plat.cota_*
    e plat.tenant.cota_bytes são lidos ao vivo em cada requisição, sem cache (mesmo contrato de PUT
    /api/org).

    Args:
        id (int):
        body (TenantCotasEntrada): POST /api/plataforma/inquilinos/{id}/cotas (só superadmin; item
            L0-07-c-cotas-uso): todo campo é
            opcional — só o que vier não-None muda. cota_bytes_teto/cota_usuarios_teto são o TETO que
            o próprio
            inquilino (PUT /api/org) nunca ultrapassa; sem valor aqui o teto vigente não muda.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: int,
    *,
    client: AuthenticatedClient | Client,
    body: TenantCotasEntrada,
) -> Any | HTTPValidationError | None:
    """Cotas Definir

     Único caminho HTTP que move o TETO de cota (cota_bytes_teto/cota_usuarios_teto) — o que o inquilino
    edita sozinho por PUT /api/org nunca ultrapassa (item L0-07-c-cotas-uso). Efeito imediato:
    plat.cota_*
    e plat.tenant.cota_bytes são lidos ao vivo em cada requisição, sem cache (mesmo contrato de PUT
    /api/org).

    Args:
        id (int):
        body (TenantCotasEntrada): POST /api/plataforma/inquilinos/{id}/cotas (só superadmin; item
            L0-07-c-cotas-uso): todo campo é
            opcional — só o que vier não-None muda. cota_bytes_teto/cota_usuarios_teto são o TETO que
            o próprio
            inquilino (PUT /api/org) nunca ultrapassa; sem valor aqui o teto vigente não muda.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
