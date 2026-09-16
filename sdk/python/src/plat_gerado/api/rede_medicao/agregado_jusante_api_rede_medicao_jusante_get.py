from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.agregado_jusante_api_rede_medicao_jusante_get_response_agregado_jusante_api_rede_medicao_jusante_get import (
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    rede_id: str,
    ativo: str,
    grandeza: str | Unset = "corrente_a",
    janela_min: int | Unset = 15,
    terminal: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["rede_id"] = rede_id

    params["ativo"] = ativo

    params["grandeza"] = grandeza

    params["janela_min"] = janela_min

    json_terminal: int | None | Unset
    if isinstance(terminal, Unset):
        json_terminal = UNSET
    else:
        json_terminal = terminal
    params["terminal"] = json_terminal

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/medicao/jusante",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError | None
):
    if response.status_code == 200:
        response_200 = AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet.from_dict(
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
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    rede_id: str,
    ativo: str,
    grandeza: str | Unset = "corrente_a",
    janela_min: int | Unset = 15,
    terminal: int | None | Unset = UNSET,
) -> Response[
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError
]:
    """Agregado Jusante

     Soma a leitura mais recente (até `janela_min` min) de `grandeza` entre os transformadores de
    distribuição alcançados a JUSANTE de `ativo` pela topologia derivada da rede — exemplo do portão:
    soma
    das correntes dos trafos de um alimentador. `terminal` desambigua um dispositivo com mais de um
    terminal (ex.: um trafo tem alta=1/baixa=2; partir do lado de baixa é o normal para "o que ele
    alimenta").

    Args:
        rede_id (str):
        ativo (str):
        grandeza (str | Unset):  Default: 'corrente_a'.
        janela_min (int | Unset):  Default: 15.
        terminal (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        ativo=ativo,
        grandeza=grandeza,
        janela_min=janela_min,
        terminal=terminal,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    rede_id: str,
    ativo: str,
    grandeza: str | Unset = "corrente_a",
    janela_min: int | Unset = 15,
    terminal: int | None | Unset = UNSET,
) -> (
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError | None
):
    """Agregado Jusante

     Soma a leitura mais recente (até `janela_min` min) de `grandeza` entre os transformadores de
    distribuição alcançados a JUSANTE de `ativo` pela topologia derivada da rede — exemplo do portão:
    soma
    das correntes dos trafos de um alimentador. `terminal` desambigua um dispositivo com mais de um
    terminal (ex.: um trafo tem alta=1/baixa=2; partir do lado de baixa é o normal para "o que ele
    alimenta").

    Args:
        rede_id (str):
        ativo (str):
        grandeza (str | Unset):  Default: 'corrente_a'.
        janela_min (int | Unset):  Default: 15.
        terminal (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        rede_id=rede_id,
        ativo=ativo,
        grandeza=grandeza,
        janela_min=janela_min,
        terminal=terminal,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    rede_id: str,
    ativo: str,
    grandeza: str | Unset = "corrente_a",
    janela_min: int | Unset = 15,
    terminal: int | None | Unset = UNSET,
) -> Response[
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError
]:
    """Agregado Jusante

     Soma a leitura mais recente (até `janela_min` min) de `grandeza` entre os transformadores de
    distribuição alcançados a JUSANTE de `ativo` pela topologia derivada da rede — exemplo do portão:
    soma
    das correntes dos trafos de um alimentador. `terminal` desambigua um dispositivo com mais de um
    terminal (ex.: um trafo tem alta=1/baixa=2; partir do lado de baixa é o normal para "o que ele
    alimenta").

    Args:
        rede_id (str):
        ativo (str):
        grandeza (str | Unset):  Default: 'corrente_a'.
        janela_min (int | Unset):  Default: 15.
        terminal (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        ativo=ativo,
        grandeza=grandeza,
        janela_min=janela_min,
        terminal=terminal,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    rede_id: str,
    ativo: str,
    grandeza: str | Unset = "corrente_a",
    janela_min: int | Unset = 15,
    terminal: int | None | Unset = UNSET,
) -> (
    AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError | None
):
    """Agregado Jusante

     Soma a leitura mais recente (até `janela_min` min) de `grandeza` entre os transformadores de
    distribuição alcançados a JUSANTE de `ativo` pela topologia derivada da rede — exemplo do portão:
    soma
    das correntes dos trafos de um alimentador. `terminal` desambigua um dispositivo com mais de um
    terminal (ex.: um trafo tem alta=1/baixa=2; partir do lado de baixa é o normal para "o que ele
    alimenta").

    Args:
        rede_id (str):
        ativo (str):
        grandeza (str | Unset):  Default: 'corrente_a'.
        janela_min (int | Unset):  Default: 15.
        terminal (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgregadoJusanteApiRedeMedicaoJusanteGetResponseAgregadoJusanteApiRedeMedicaoJusanteGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            rede_id=rede_id,
            ativo=ativo,
            grandeza=grandeza,
            janela_min=janela_min,
            terminal=terminal,
        )
    ).parsed
