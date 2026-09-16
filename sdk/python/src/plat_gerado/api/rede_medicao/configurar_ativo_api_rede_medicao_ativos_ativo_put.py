from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ativo_config_entrada import AtivoConfigEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    ativo: str,
    *,
    body: AtivoConfigEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/rede/medicao/ativos/{ativo}".format(
            ativo=quote(str(ativo), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivoConfigEntrada,
) -> Response[Any | HTTPValidationError]:
    """Configurar Ativo

     Placa do ativo (kVA/tensão nominal): sem ela o motor de alarme não calcula carregamento — não é erro
    (nem todo ativo tem placa cadastrada ainda), só fica sem essa leitura derivada.

    Args:
        ativo (str):
        body (AtivoConfigEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivoConfigEntrada,
) -> Any | HTTPValidationError | None:
    """Configurar Ativo

     Placa do ativo (kVA/tensão nominal): sem ela o motor de alarme não calcula carregamento — não é erro
    (nem todo ativo tem placa cadastrada ainda), só fica sem essa leitura derivada.

    Args:
        ativo (str):
        body (AtivoConfigEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        ativo=ativo,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivoConfigEntrada,
) -> Response[Any | HTTPValidationError]:
    """Configurar Ativo

     Placa do ativo (kVA/tensão nominal): sem ela o motor de alarme não calcula carregamento — não é erro
    (nem todo ativo tem placa cadastrada ainda), só fica sem essa leitura derivada.

    Args:
        ativo (str):
        body (AtivoConfigEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    body: AtivoConfigEntrada,
) -> Any | HTTPValidationError | None:
    """Configurar Ativo

     Placa do ativo (kVA/tensão nominal): sem ela o motor de alarme não calcula carregamento — não é erro
    (nem todo ativo tem placa cadastrada ainda), só fica sem essa leitura derivada.

    Args:
        ativo (str):
        body (AtivoConfigEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            ativo=ativo,
            client=client,
            body=body,
        )
    ).parsed
