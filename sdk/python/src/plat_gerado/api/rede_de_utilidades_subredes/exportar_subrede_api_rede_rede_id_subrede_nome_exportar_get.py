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
    tier: None | str | Unset = UNSET,
    formato: str | Unset = "json",
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tier: None | str | Unset
    if isinstance(tier, Unset):
        json_tier = UNSET
    else:
        json_tier = tier
    params["tier"] = json_tier

    params["formato"] = formato

    json_ano: int | None | Unset
    if isinstance(ano, Unset):
        json_ano = UNSET
    else:
        json_ano = ano
    params["ano"] = json_ano

    params["jusante"] = jusante

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/subrede/{nome}/exportar".format(
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
    tier: None | str | Unset = UNSET,
    formato: str | Unset = "json",
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Exportar Subrede

     `formato=json` (padrão): rede, subrede (com a linha agregada), controladores, elementos,
    conectividade e resumo, validado contra `plat.rede.subrede_exportada` antes de sair.

    `formato=dss`: a pasta OpenDSS da subrede, num zip. `ano` escolhe o calendário da curva de 864
    pontos
    (24 h x 3 tipos de dia x 12 meses); o padrão é o ano corrente. `jusante=true` inclui as subredes de
    tier
    inferior que penduram nesta — é o alimentador inteiro, com transformador e carga, em vez de só o
    tier
    pedido.

    `formato=pandapower`: `rede.json`, que `pandapower.from_json` lê, mais `resumo.json` e `NAO_FAZ.md`,
    num zip. `formato=matpower`: o `.m` do caseformat 2, com os mesmos dois arquivos ao lado. Os dois
    são
    modelos de rede EQUILIBRADA (sequência positiva): as fases declaradas por trecho não são
    representadas, e onde o desequilíbrio importa o formato certo é o `dss`. O `ano` não muda nada
    nesses
    dois formatos — a curva de carga só existe no OpenDSS; cada carga sai com a potência média do ano.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        formato (str | Unset):  Default: 'json'.
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        tier=tier,
        formato=formato,
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
    tier: None | str | Unset = UNSET,
    formato: str | Unset = "json",
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Exportar Subrede

     `formato=json` (padrão): rede, subrede (com a linha agregada), controladores, elementos,
    conectividade e resumo, validado contra `plat.rede.subrede_exportada` antes de sair.

    `formato=dss`: a pasta OpenDSS da subrede, num zip. `ano` escolhe o calendário da curva de 864
    pontos
    (24 h x 3 tipos de dia x 12 meses); o padrão é o ano corrente. `jusante=true` inclui as subredes de
    tier
    inferior que penduram nesta — é o alimentador inteiro, com transformador e carga, em vez de só o
    tier
    pedido.

    `formato=pandapower`: `rede.json`, que `pandapower.from_json` lê, mais `resumo.json` e `NAO_FAZ.md`,
    num zip. `formato=matpower`: o `.m` do caseformat 2, com os mesmos dois arquivos ao lado. Os dois
    são
    modelos de rede EQUILIBRADA (sequência positiva): as fases declaradas por trecho não são
    representadas, e onde o desequilíbrio importa o formato certo é o `dss`. O `ano` não muda nada
    nesses
    dois formatos — a curva de carga só existe no OpenDSS; cada carga sai com a potência média do ano.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        formato (str | Unset):  Default: 'json'.
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.

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
        tier=tier,
        formato=formato,
        ano=ano,
        jusante=jusante,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    tier: None | str | Unset = UNSET,
    formato: str | Unset = "json",
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Response[Any | HTTPValidationError]:
    """Exportar Subrede

     `formato=json` (padrão): rede, subrede (com a linha agregada), controladores, elementos,
    conectividade e resumo, validado contra `plat.rede.subrede_exportada` antes de sair.

    `formato=dss`: a pasta OpenDSS da subrede, num zip. `ano` escolhe o calendário da curva de 864
    pontos
    (24 h x 3 tipos de dia x 12 meses); o padrão é o ano corrente. `jusante=true` inclui as subredes de
    tier
    inferior que penduram nesta — é o alimentador inteiro, com transformador e carga, em vez de só o
    tier
    pedido.

    `formato=pandapower`: `rede.json`, que `pandapower.from_json` lê, mais `resumo.json` e `NAO_FAZ.md`,
    num zip. `formato=matpower`: o `.m` do caseformat 2, com os mesmos dois arquivos ao lado. Os dois
    são
    modelos de rede EQUILIBRADA (sequência positiva): as fases declaradas por trecho não são
    representadas, e onde o desequilíbrio importa o formato certo é o `dss`. O `ano` não muda nada
    nesses
    dois formatos — a curva de carga só existe no OpenDSS; cada carga sai com a potência média do ano.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        formato (str | Unset):  Default: 'json'.
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        tier=tier,
        formato=formato,
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
    tier: None | str | Unset = UNSET,
    formato: str | Unset = "json",
    ano: int | None | Unset = UNSET,
    jusante: bool | Unset = False,
) -> Any | HTTPValidationError | None:
    """Exportar Subrede

     `formato=json` (padrão): rede, subrede (com a linha agregada), controladores, elementos,
    conectividade e resumo, validado contra `plat.rede.subrede_exportada` antes de sair.

    `formato=dss`: a pasta OpenDSS da subrede, num zip. `ano` escolhe o calendário da curva de 864
    pontos
    (24 h x 3 tipos de dia x 12 meses); o padrão é o ano corrente. `jusante=true` inclui as subredes de
    tier
    inferior que penduram nesta — é o alimentador inteiro, com transformador e carga, em vez de só o
    tier
    pedido.

    `formato=pandapower`: `rede.json`, que `pandapower.from_json` lê, mais `resumo.json` e `NAO_FAZ.md`,
    num zip. `formato=matpower`: o `.m` do caseformat 2, com os mesmos dois arquivos ao lado. Os dois
    são
    modelos de rede EQUILIBRADA (sequência positiva): as fases declaradas por trecho não são
    representadas, e onde o desequilíbrio importa o formato certo é o `dss`. O `ano` não muda nada
    nesses
    dois formatos — a curva de carga só existe no OpenDSS; cada carga sai com a potência média do ano.

    Args:
        rede_id (str):
        nome (str):
        tier (None | str | Unset):
        formato (str | Unset):  Default: 'json'.
        ano (int | None | Unset):
        jusante (bool | Unset):  Default: False.

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
            tier=tier,
            formato=formato,
            ano=ano,
            jusante=jusante,
        )
    ).parsed
