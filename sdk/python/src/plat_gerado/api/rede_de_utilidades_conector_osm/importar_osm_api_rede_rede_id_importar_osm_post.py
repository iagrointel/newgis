from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.importacao_osm_entrada import ImportacaoOsmEntrada
from ...models.importacao_osm_resultado import ImportacaoOsmResultado
from ...types import Response


def _get_kwargs(
    rede_id: str,
    *,
    body: ImportacaoOsmEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/importar-osm".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ImportacaoOsmResultado | None:
    if response.status_code == 201:
        response_201 = ImportacaoOsmResultado.from_dict(response.json())

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
) -> Response[HTTPValidationError | ImportacaoOsmResultado]:
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
    body: ImportacaoOsmEntrada,
) -> Response[HTTPValidationError | ImportacaoOsmResultado]:
    """Importar Osm

     Importa power=* do município para a rede (que já deve ter o pacote eletrica-br importado).
    Numa transação: ou entra tudo, ou nada. A contagem por etiqueta é conferida contra o extrato e
    o que não entra vira desvio explicado — nunca silêncio.

    Args:
        rede_id (str):
        body (ImportacaoOsmEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoOsmResultado]
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
    body: ImportacaoOsmEntrada,
) -> HTTPValidationError | ImportacaoOsmResultado | None:
    """Importar Osm

     Importa power=* do município para a rede (que já deve ter o pacote eletrica-br importado).
    Numa transação: ou entra tudo, ou nada. A contagem por etiqueta é conferida contra o extrato e
    o que não entra vira desvio explicado — nunca silêncio.

    Args:
        rede_id (str):
        body (ImportacaoOsmEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoOsmResultado
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
    body: ImportacaoOsmEntrada,
) -> Response[HTTPValidationError | ImportacaoOsmResultado]:
    """Importar Osm

     Importa power=* do município para a rede (que já deve ter o pacote eletrica-br importado).
    Numa transação: ou entra tudo, ou nada. A contagem por etiqueta é conferida contra o extrato e
    o que não entra vira desvio explicado — nunca silêncio.

    Args:
        rede_id (str):
        body (ImportacaoOsmEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoOsmResultado]
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
    body: ImportacaoOsmEntrada,
) -> HTTPValidationError | ImportacaoOsmResultado | None:
    """Importar Osm

     Importa power=* do município para a rede (que já deve ter o pacote eletrica-br importado).
    Numa transação: ou entra tudo, ou nada. A contagem por etiqueta é conferida contra o extrato e
    o que não entra vira desvio explicado — nunca silêncio.

    Args:
        rede_id (str):
        body (ImportacaoOsmEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoOsmResultado
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            body=body,
        )
    ).parsed
