from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    incluir_documento: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["incluir_documento"] = incluir_documento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/mapas/{id}/completo".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
    incluir_documento: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Mapa Completo

     Documento com as camadas resolvidas em UMA chamada. Referência que o ator não pode ler é 404 aqui
    também:
    o mapa não vira meio-mapa silencioso quando alguém perde acesso a uma camada.

    Args:
        id (str):
        incluir_documento (bool | Unset): devolve também o documento como está gravado Default:
            False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        incluir_documento=incluir_documento,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    incluir_documento: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Mapa Completo

     Documento com as camadas resolvidas em UMA chamada. Referência que o ator não pode ler é 404 aqui
    também:
    o mapa não vira meio-mapa silencioso quando alguém perde acesso a uma camada.

    Args:
        id (str):
        incluir_documento (bool | Unset): devolve também o documento como está gravado Default:
            False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        incluir_documento=incluir_documento,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    incluir_documento: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Mapa Completo

     Documento com as camadas resolvidas em UMA chamada. Referência que o ator não pode ler é 404 aqui
    também:
    o mapa não vira meio-mapa silencioso quando alguém perde acesso a uma camada.

    Args:
        id (str):
        incluir_documento (bool | Unset): devolve também o documento como está gravado Default:
            False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        incluir_documento=incluir_documento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    incluir_documento: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Mapa Completo

     Documento com as camadas resolvidas em UMA chamada. Referência que o ator não pode ler é 404 aqui
    também:
    o mapa não vira meio-mapa silencioso quando alguém perde acesso a uma camada.

    Args:
        id (str):
        incluir_documento (bool | Unset): devolve também o documento como está gravado Default:
            False.

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
            incluir_documento=incluir_documento,
        )
    ).parsed
