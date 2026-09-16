from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    catalogo_item_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/geoparquet/{catalogo_item_id}/arquivos".format(
            catalogo_item_id=quote(str(catalogo_item_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    catalogo_item_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Arquivos

     Um `{chave, sha256, bytes, linhas, bbox, particao, url}` por arquivo do item `parquet`, com URL
    assinada de curta duração (`limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS`) — o mesmo
    `/api/objetos/{chave}`
    anônimo que qualquer outro arquivo da plataforma usa (ADR 0004 seção 11.2): DuckDB, QGIS e Pro leem
    `https://.../api/objetos/<chave>?ate=...&assinatura=...` como se fosse um Parquet estático.

    Args:
        catalogo_item_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        catalogo_item_id=catalogo_item_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    catalogo_item_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Arquivos

     Um `{chave, sha256, bytes, linhas, bbox, particao, url}` por arquivo do item `parquet`, com URL
    assinada de curta duração (`limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS`) — o mesmo
    `/api/objetos/{chave}`
    anônimo que qualquer outro arquivo da plataforma usa (ADR 0004 seção 11.2): DuckDB, QGIS e Pro leem
    `https://.../api/objetos/<chave>?ate=...&assinatura=...` como se fosse um Parquet estático.

    Args:
        catalogo_item_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        catalogo_item_id=catalogo_item_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    catalogo_item_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Arquivos

     Um `{chave, sha256, bytes, linhas, bbox, particao, url}` por arquivo do item `parquet`, com URL
    assinada de curta duração (`limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS`) — o mesmo
    `/api/objetos/{chave}`
    anônimo que qualquer outro arquivo da plataforma usa (ADR 0004 seção 11.2): DuckDB, QGIS e Pro leem
    `https://.../api/objetos/<chave>?ate=...&assinatura=...` como se fosse um Parquet estático.

    Args:
        catalogo_item_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        catalogo_item_id=catalogo_item_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    catalogo_item_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Arquivos

     Um `{chave, sha256, bytes, linhas, bbox, particao, url}` por arquivo do item `parquet`, com URL
    assinada de curta duração (`limites.GEOPARQUET_URL_ASSINADA_SEGUNDOS`) — o mesmo
    `/api/objetos/{chave}`
    anônimo que qualquer outro arquivo da plataforma usa (ADR 0004 seção 11.2): DuckDB, QGIS e Pro leem
    `https://.../api/objetos/<chave>?ate=...&assinatura=...` como se fosse um Parquet estático.

    Args:
        catalogo_item_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            catalogo_item_id=catalogo_item_id,
            client=client,
        )
    ).parsed
