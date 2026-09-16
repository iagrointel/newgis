from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    exportacao_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/exportacoes/{exportacao_id}".format(
            exportacao_id=quote(str(exportacao_id), safe=""),
        ),
    }

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
    exportacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Apagar

     Cancela a que ainda roda (o job é cancelado junto) ou apaga o arquivo da que já está pronta.

    Item de seguimento de L0-04-a/L0-11: exigia token `admin:inquilino` para cancelar/apagar a PRÓPRIA
    exportação — só perfil admin conseguia emitir esse escopo (`app/auth/rotas_tokens.py`), embora
    `conteudo.exportar` (o privilégio que já cobre `POST /api/exportacoes`, teto editor/admin) baste, e
    `_carregar` acima já recusa com 404 quem não é dono (nem tem `jobs.gerir_todos`).

    Args:
        exportacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        exportacao_id=exportacao_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    exportacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Apagar

     Cancela a que ainda roda (o job é cancelado junto) ou apaga o arquivo da que já está pronta.

    Item de seguimento de L0-04-a/L0-11: exigia token `admin:inquilino` para cancelar/apagar a PRÓPRIA
    exportação — só perfil admin conseguia emitir esse escopo (`app/auth/rotas_tokens.py`), embora
    `conteudo.exportar` (o privilégio que já cobre `POST /api/exportacoes`, teto editor/admin) baste, e
    `_carregar` acima já recusa com 404 quem não é dono (nem tem `jobs.gerir_todos`).

    Args:
        exportacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        exportacao_id=exportacao_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    exportacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Apagar

     Cancela a que ainda roda (o job é cancelado junto) ou apaga o arquivo da que já está pronta.

    Item de seguimento de L0-04-a/L0-11: exigia token `admin:inquilino` para cancelar/apagar a PRÓPRIA
    exportação — só perfil admin conseguia emitir esse escopo (`app/auth/rotas_tokens.py`), embora
    `conteudo.exportar` (o privilégio que já cobre `POST /api/exportacoes`, teto editor/admin) baste, e
    `_carregar` acima já recusa com 404 quem não é dono (nem tem `jobs.gerir_todos`).

    Args:
        exportacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        exportacao_id=exportacao_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    exportacao_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Apagar

     Cancela a que ainda roda (o job é cancelado junto) ou apaga o arquivo da que já está pronta.

    Item de seguimento de L0-04-a/L0-11: exigia token `admin:inquilino` para cancelar/apagar a PRÓPRIA
    exportação — só perfil admin conseguia emitir esse escopo (`app/auth/rotas_tokens.py`), embora
    `conteudo.exportar` (o privilégio que já cobre `POST /api/exportacoes`, teto editor/admin) baste, e
    `_carregar` acima já recusa com 404 quem não é dono (nem tem `jobs.gerir_todos`).

    Args:
        exportacao_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            exportacao_id=exportacao_id,
            client=client,
        )
    ).parsed
