from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.calcular_curto_api_rede_rede_id_subrede_nome_curto_post_premissas import (
    CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    nome: str,
    *,
    body: CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    json_tier: None | str | Unset
    if isinstance(tier, Unset):
        json_tier = UNSET
    else:
        json_tier = tier
    params["tier"] = json_tier

    json_ano: int | None | Unset
    if isinstance(ano, Unset):
        json_ano = UNSET
    else:
        json_ano = ano
    params["ano"] = json_ano

    params["jusante"] = jusante

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/subrede/{nome}/curto".format(
            rede_id=quote(str(rede_id), safe=""),
            nome=quote(str(nome), safe=""),
        ),
        "params": params,
    }

    if not isinstance(body, Unset):
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
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    body: CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Calcular Curto

     Corrente de curto-circuito por barra (trifásica e fase-terra) e verificação de coordenação simples
    do dispositivo a montante de cada barra, sobre o mesmo modelo em memória que os exportadores usam.

    O corpo são as PREMISSAS: `potencia_de_curto_mva` (obrigatória — sem ela a impedância da fonte é
    nula
    e a corrente seria infinita), `relacao_x_r_fonte`, `fator_tensao_c`, `fator_sequencia_zero_linha`,
    `fator_sequencia_zero_fonte` e `base_mva`. Todas saem gravadas ao lado do resultado. É triagem:
    a impedância de condutor e a do transformador são valores de REFERÊNCIA declarados, porque o
    cadastro
    de distribuição não os traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        body=body,
        tier=tier,
        ano=ano,
        jusante=jusante,
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
    body: CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Calcular Curto

     Corrente de curto-circuito por barra (trifásica e fase-terra) e verificação de coordenação simples
    do dispositivo a montante de cada barra, sobre o mesmo modelo em memória que os exportadores usam.

    O corpo são as PREMISSAS: `potencia_de_curto_mva` (obrigatória — sem ela a impedância da fonte é
    nula
    e a corrente seria infinita), `relacao_x_r_fonte`, `fator_tensao_c`, `fator_sequencia_zero_linha`,
    `fator_sequencia_zero_fonte` e `base_mva`. Todas saem gravadas ao lado do resultado. É triagem:
    a impedância de condutor e a do transformador são valores de REFERÊNCIA declarados, porque o
    cadastro
    de distribuição não os traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset):

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
        body=body,
        tier=tier,
        ano=ano,
        jusante=jusante,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    body: CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Calcular Curto

     Corrente de curto-circuito por barra (trifásica e fase-terra) e verificação de coordenação simples
    do dispositivo a montante de cada barra, sobre o mesmo modelo em memória que os exportadores usam.

    O corpo são as PREMISSAS: `potencia_de_curto_mva` (obrigatória — sem ela a impedância da fonte é
    nula
    e a corrente seria infinita), `relacao_x_r_fonte`, `fator_tensao_c`, `fator_sequencia_zero_linha`,
    `fator_sequencia_zero_fonte` e `base_mva`. Todas saem gravadas ao lado do resultado. É triagem:
    a impedância de condutor e a do transformador são valores de REFERÊNCIA declarados, porque o
    cadastro
    de distribuição não os traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        body=body,
        tier=tier,
        ano=ano,
        jusante=jusante,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    body: CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Calcular Curto

     Corrente de curto-circuito por barra (trifásica e fase-terra) e verificação de coordenação simples
    do dispositivo a montante de cada barra, sobre o mesmo modelo em memória que os exportadores usam.

    O corpo são as PREMISSAS: `potencia_de_curto_mva` (obrigatória — sem ela a impedância da fonte é
    nula
    e a corrente seria infinita), `relacao_x_r_fonte`, `fator_tensao_c`, `fator_sequencia_zero_linha`,
    `fator_sequencia_zero_fonte` e `base_mva`. Todas saem gravadas ao lado do resultado. É triagem:
    a impedância de condutor e a do transformador são valores de REFERÊNCIA declarados, porque o
    cadastro
    de distribuição não os traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularCurtoApiRedeRedeIdSubredeNomeCurtoPostPremissas | Unset):

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
            body=body,
            tier=tier,
            ano=ano,
            jusante=jusante,
        )
    ).parsed
