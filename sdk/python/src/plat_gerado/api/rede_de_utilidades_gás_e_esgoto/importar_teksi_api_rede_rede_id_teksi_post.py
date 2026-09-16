from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.teksi_importacao_resultado import TeksiImportacaoResultado
from ...types import Response


def _get_kwargs(
    rede_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/teksi".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TeksiImportacaoResultado | None:
    if response.status_code == 201:
        response_201 = TeksiImportacaoResultado.from_dict(response.json())

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
) -> Response[HTTPValidationError | TeksiImportacaoResultado]:
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
) -> Response[HTTPValidationError | TeksiImportacaoResultado]:
    """Importar Teksi

     Importa um GeoPackage no esquema TEKSI para as feições da rede. O de-para coluna → atributo é o do
    pacote de ativos já importado nesta rede (`origem.camada`/`origem.coluna` de cada atributo).

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TeksiImportacaoResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | TeksiImportacaoResultado | None:
    """Importar Teksi

     Importa um GeoPackage no esquema TEKSI para as feições da rede. O de-para coluna → atributo é o do
    pacote de ativos já importado nesta rede (`origem.camada`/`origem.coluna` de cada atributo).

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TeksiImportacaoResultado
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | TeksiImportacaoResultado]:
    """Importar Teksi

     Importa um GeoPackage no esquema TEKSI para as feições da rede. O de-para coluna → atributo é o do
    pacote de ativos já importado nesta rede (`origem.camada`/`origem.coluna` de cada atributo).

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TeksiImportacaoResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | TeksiImportacaoResultado | None:
    """Importar Teksi

     Importa um GeoPackage no esquema TEKSI para as feições da rede. O de-para coluna → atributo é o do
    pacote de ativos já importado nesta rede (`origem.camada`/`origem.coluna` de cada atributo).

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TeksiImportacaoResultado
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
        )
    ).parsed
