from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/arquivos/_chave-leitura",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 200:
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
    """Chave Leitura

     A chave S3 SÓ-LEITURA do balde do inquilino: é o que a conexão S3 do ArcGIS Pro (`Create Cloud
    Storage
    Connection File`, provedor S3 compatível, endereçamento por caminho) e o TiTiler (`/vsis3`) precisam
    para ler
    o COG direto do Garage, sem passar byte por esta API. Nunca a chave de escrita — essa só existe
    dentro do
    processo da API e do worker (ADR 20260908T1255 seção 4). Só sob sessão e com `org.integracoes`: um
    token de serviço
    não troca a si mesmo por uma credencial de armazenamento.

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
    """Chave Leitura

     A chave S3 SÓ-LEITURA do balde do inquilino: é o que a conexão S3 do ArcGIS Pro (`Create Cloud
    Storage
    Connection File`, provedor S3 compatível, endereçamento por caminho) e o TiTiler (`/vsis3`) precisam
    para ler
    o COG direto do Garage, sem passar byte por esta API. Nunca a chave de escrita — essa só existe
    dentro do
    processo da API e do worker (ADR 20260908T1255 seção 4). Só sob sessão e com `org.integracoes`: um
    token de serviço
    não troca a si mesmo por uma credencial de armazenamento.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
