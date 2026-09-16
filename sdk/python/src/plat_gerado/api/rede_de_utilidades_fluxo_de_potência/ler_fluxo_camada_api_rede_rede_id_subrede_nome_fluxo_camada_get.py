from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    nome: str,
    *,
    grandeza: str | Unset = "tensao",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["grandeza"] = grandeza

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/subrede/{nome}/fluxo/camada".format(
            rede_id=quote(str(rede_id), safe=""),
            nome=quote(str(nome), safe=""),
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
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str | Unset = "tensao",
) -> Response[Any | HTTPValidationError]:
    """Ler Fluxo Camada

     O mesmo resultado como camada para o mapa: `tensao` (um ponto por barra e fase, em por unidade),
    `corrente` (a linha do trecho, em ampere) ou `carregamento` (a mesma linha, em por cento da corrente
    nominal declarada). Elemento sem geometria é contado em `elementos_sem_geometria` e não vira feição.

    Args:
        rede_id (str):
        nome (str):
        grandeza (str | Unset):  Default: 'tensao'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        grandeza=grandeza,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str | Unset = "tensao",
) -> Any | HTTPValidationError | None:
    """Ler Fluxo Camada

     O mesmo resultado como camada para o mapa: `tensao` (um ponto por barra e fase, em por unidade),
    `corrente` (a linha do trecho, em ampere) ou `carregamento` (a mesma linha, em por cento da corrente
    nominal declarada). Elemento sem geometria é contado em `elementos_sem_geometria` e não vira feição.

    Args:
        rede_id (str):
        nome (str):
        grandeza (str | Unset):  Default: 'tensao'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        nome=nome,
        client=client,
        grandeza=grandeza,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str | Unset = "tensao",
) -> Response[Any | HTTPValidationError]:
    """Ler Fluxo Camada

     O mesmo resultado como camada para o mapa: `tensao` (um ponto por barra e fase, em por unidade),
    `corrente` (a linha do trecho, em ampere) ou `carregamento` (a mesma linha, em por cento da corrente
    nominal declarada). Elemento sem geometria é contado em `elementos_sem_geometria` e não vira feição.

    Args:
        rede_id (str):
        nome (str):
        grandeza (str | Unset):  Default: 'tensao'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        grandeza=grandeza,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    grandeza: str | Unset = "tensao",
) -> Any | HTTPValidationError | None:
    """Ler Fluxo Camada

     O mesmo resultado como camada para o mapa: `tensao` (um ponto por barra e fase, em por unidade),
    `corrente` (a linha do trecho, em ampere) ou `carregamento` (a mesma linha, em por cento da corrente
    nominal declarada). Elemento sem geometria é contado em `elementos_sem_geometria` e não vira feição.

    Args:
        rede_id (str):
        nome (str):
        grandeza (str | Unset):  Default: 'tensao'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            nome=nome,
            client=client,
            grandeza=grandeza,
        )
    ).parsed
