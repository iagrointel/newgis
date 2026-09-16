from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.serie_api_rede_medicao_ativos_ativo_serie_get_response_serie_api_rede_medicao_ativos_ativo_serie_get import (
    SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    ativo: str,
    *,
    grandeza: str,
    dias: int | Unset = 7,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["grandeza"] = grandeza

    params["dias"] = dias

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/medicao/ativos/{ativo}/serie".format(
            ativo=quote(str(ativo), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet | None:
    if response.status_code == 200:
        response_200 = SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet.from_dict(
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
    HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet
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
    grandeza: str,
    dias: int | Unset = 7,
) -> Response[
    HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet
]:
    """Serie

     Série de `grandeza` nos últimos `dias` dias (padrão 7 — o gráfico da ficha do ativo).

    Args:
        ativo (str):
        grandeza (str):
        dias (int | Unset):  Default: 7.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
        grandeza=grandeza,
        dias=dias,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str,
    dias: int | Unset = 7,
) -> HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet | None:
    """Serie

     Série de `grandeza` nos últimos `dias` dias (padrão 7 — o gráfico da ficha do ativo).

    Args:
        ativo (str):
        grandeza (str):
        dias (int | Unset):  Default: 7.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet
    """

    return sync_detailed(
        ativo=ativo,
        client=client,
        grandeza=grandeza,
        dias=dias,
    ).parsed


async def asyncio_detailed(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str,
    dias: int | Unset = 7,
) -> Response[
    HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet
]:
    """Serie

     Série de `grandeza` nos últimos `dias` dias (padrão 7 — o gráfico da ficha do ativo).

    Args:
        ativo (str):
        grandeza (str):
        dias (int | Unset):  Default: 7.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet]
    """

    kwargs = _get_kwargs(
        ativo=ativo,
        grandeza=grandeza,
        dias=dias,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    ativo: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str,
    dias: int | Unset = 7,
) -> HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet | None:
    """Serie

     Série de `grandeza` nos últimos `dias` dias (padrão 7 — o gráfico da ficha do ativo).

    Args:
        ativo (str):
        grandeza (str):
        dias (int | Unset):  Default: 7.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SerieApiRedeMedicaoAtivosAtivoSerieGetResponseSerieApiRedeMedicaoAtivosAtivoSerieGet
    """

    return (
        await asyncio_detailed(
            ativo=ativo,
            client=client,
            grandeza=grandeza,
            dias=dias,
        )
    ).parsed
