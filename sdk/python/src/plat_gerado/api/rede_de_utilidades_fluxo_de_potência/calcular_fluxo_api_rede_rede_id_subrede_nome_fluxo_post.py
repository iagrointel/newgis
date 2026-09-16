from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.calcular_fluxo_api_rede_rede_id_subrede_nome_fluxo_post_parametros import (
    CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    nome: str,
    *,
    body: CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset = UNSET,
    tier: None | str | Unset = UNSET,
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

    params["jusante"] = jusante

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/subrede/{nome}/fluxo".format(
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
    body: CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Calcular Fluxo

     Fluxo de potência trifásico desequilibrado do alimentador, no OpenDSS, sobre o MESMO modelo em
    memória que os exportadores usam.

    O corpo são os PARÂMETROS: `modo` (`anual`, os 864 pontos da curva, ou `hora`), `ponto`, `ano`,
    `fator_de_carga`, `modelo_de_carga` (com `zipv` obrigatório quando `zip`), `tensao_da_fonte_pu`,
    `corrente_nominal_a` e `com_geracao_distribuida`. Todos saem gravados ao lado do resultado, com a
    versão da topologia e o estado de convergência. É triagem: a impedância de condutor é a padrão do
    OpenDSS, porque o cadastro de distribuição não a traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset):

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
    body: CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Calcular Fluxo

     Fluxo de potência trifásico desequilibrado do alimentador, no OpenDSS, sobre o MESMO modelo em
    memória que os exportadores usam.

    O corpo são os PARÂMETROS: `modo` (`anual`, os 864 pontos da curva, ou `hora`), `ponto`, `ano`,
    `fator_de_carga`, `modelo_de_carga` (com `zipv` obrigatório quando `zip`), `tensao_da_fonte_pu`,
    `corrente_nominal_a` e `com_geracao_distribuida`. Todos saem gravados ao lado do resultado, com a
    versão da topologia e o estado de convergência. É triagem: a impedância de condutor é a padrão do
    OpenDSS, porque o cadastro de distribuição não a traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset):

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
        jusante=jusante,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    body: CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Calcular Fluxo

     Fluxo de potência trifásico desequilibrado do alimentador, no OpenDSS, sobre o MESMO modelo em
    memória que os exportadores usam.

    O corpo são os PARÂMETROS: `modo` (`anual`, os 864 pontos da curva, ou `hora`), `ponto`, `ano`,
    `fator_de_carga`, `modelo_de_carga` (com `zipv` obrigatório quando `zip`), `tensao_da_fonte_pu`,
    `corrente_nominal_a` e `com_geracao_distribuida`. Todos saem gravados ao lado do resultado, com a
    versão da topologia e o estado de convergência. É triagem: a impedância de condutor é a padrão do
    OpenDSS, porque o cadastro de distribuição não a traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset):

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
        jusante=jusante,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    body: CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset = UNSET,
    tier: None | str | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Calcular Fluxo

     Fluxo de potência trifásico desequilibrado do alimentador, no OpenDSS, sobre o MESMO modelo em
    memória que os exportadores usam.

    O corpo são os PARÂMETROS: `modo` (`anual`, os 864 pontos da curva, ou `hora`), `ponto`, `ano`,
    `fator_de_carga`, `modelo_de_carga` (com `zipv` obrigatório quando `zip`), `tensao_da_fonte_pu`,
    `corrente_nominal_a` e `com_geracao_distribuida`. Todos saem gravados ao lado do resultado, com a
    versão da topologia e o estado de convergência. É triagem: a impedância de condutor é a padrão do
    OpenDSS, porque o cadastro de distribuição não a traz.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        jusante (bool | Unset):  Default: False.
        body (CalcularFluxoApiRedeRedeIdSubredeNomeFluxoPostParametros | Unset):

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
            jusante=jusante,
        )
    ).parsed
