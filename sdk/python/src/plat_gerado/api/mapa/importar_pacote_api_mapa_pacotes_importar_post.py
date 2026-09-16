from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/mapa/pacotes/importar",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 201:
        return None

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Importar Pacote

     Recria, NESTE inquilino, o mapa que outro pacote levou: as camadas do GeoPackage viram tabelas
    novas do inquilino, cada uma com a sua simbologia, e o documento de mapa volta a apontar para elas.

    O corpo é o zip CRU (`application/zip`), não multipart: é o mesmo caminho de `app/uploads/rotas.py`
    e de `app/rotas_arquivos.py` nesta casa, e evita uma dependência nova só para envelopar um arquivo
    (o `python-multipart` não está instalado, e o brief proíbe mexer no venv compartilhado por isto).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Importar Pacote

     Recria, NESTE inquilino, o mapa que outro pacote levou: as camadas do GeoPackage viram tabelas
    novas do inquilino, cada uma com a sua simbologia, e o documento de mapa volta a apontar para elas.

    O corpo é o zip CRU (`application/zip`), não multipart: é o mesmo caminho de `app/uploads/rotas.py`
    e de `app/rotas_arquivos.py` nesta casa, e evita uma dependência nova só para envelopar um arquivo
    (o `python-multipart` não está instalado, e o brief proíbe mexer no venv compartilhado por isto).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
