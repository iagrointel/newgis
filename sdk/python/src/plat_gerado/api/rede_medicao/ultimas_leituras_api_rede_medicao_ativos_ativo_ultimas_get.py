from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.ultimas_leituras_api_rede_medicao_ativos_ativo_ultimas_get_response_ultimas_leituras_api_rede_medicao_ativos_ativo_ultimas_get import (
    UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet,
)
from ...types import Response


def _get_kwargs(
    ativo: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/medicao/ativos/{ativo}/ultimas".format(
            ativo=quote(str(ativo), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
    | None
):
    if response.status_code == 200:
        response_200 = UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet.from_dict(
            response.json()
        )

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
) -> Response[
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
]:
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
) -> Response[
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
]:
    """Ultimas Leituras

     Última leitura de cada grandeza publicada para este ativo — o que a ficha do ativo mostra no topo.

    Args:
        ativo (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
    | None
):
    """Ultimas Leituras

     Última leitura de cada grandeza publicada para este ativo — o que a ficha do ativo mostra no topo.

    Args:
        ativo (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
    """

    return sync_detailed(
        ativo=ativo,
        client=client,
    ).parsed


async def asyncio_detailed(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
]:
    """Ultimas Leituras

     Última leitura de cada grandeza publicada para este ativo — o que a ficha do ativo mostra no topo.

    Args:
        ativo (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    HTTPValidationError
    | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
    | None
):
    """Ultimas Leituras

     Última leitura de cada grandeza publicada para este ativo — o que a ficha do ativo mostra no topo.

    Args:
        ativo (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGetResponseUltimasLeiturasApiRedeMedicaoAtivosAtivoUltimasGet
    """

    return (
        await asyncio_detailed(
            ativo=ativo,
            client=client,
        )
    ).parsed
