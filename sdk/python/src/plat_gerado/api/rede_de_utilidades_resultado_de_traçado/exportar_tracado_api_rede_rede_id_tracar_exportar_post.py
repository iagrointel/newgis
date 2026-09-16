from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tracado_entrada import TracadoEntrada
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    body: TracadoEntrada,
    formato: str | Unset = "csv",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/tracar/exportar".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
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
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
    formato: str | Unset = "csv",
) -> Response[Any | HTTPValidationError]:
    """Exportar Tracado

     O mesmo pedido de `POST .../tracar`, devolvido como arquivo. `formato=csv` (padrão), `geojson` ou
    `gpkg`. Nenhum elemento se perde entre os três: os três saem da MESMA lista de linhas.

    Args:
        rede_id (str):
        formato (str | Unset):  Default: 'csv'.
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
    formato: str | Unset = "csv",
) -> Any | HTTPValidationError | None:
    """Exportar Tracado

     O mesmo pedido de `POST .../tracar`, devolvido como arquivo. `formato=csv` (padrão), `geojson` ou
    `gpkg`. Nenhum elemento se perde entre os três: os três saem da MESMA lista de linhas.

    Args:
        rede_id (str):
        formato (str | Unset):  Default: 'csv'.
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        body=body,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
    formato: str | Unset = "csv",
) -> Response[Any | HTTPValidationError]:
    """Exportar Tracado

     O mesmo pedido de `POST .../tracar`, devolvido como arquivo. `formato=csv` (padrão), `geojson` ou
    `gpkg`. Nenhum elemento se perde entre os três: os três saem da MESMA lista de linhas.

    Args:
        rede_id (str):
        formato (str | Unset):  Default: 'csv'.
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
    formato: str | Unset = "csv",
) -> Any | HTTPValidationError | None:
    """Exportar Tracado

     O mesmo pedido de `POST .../tracar`, devolvido como arquivo. `formato=csv` (padrão), `geojson` ou
    `gpkg`. Nenhum elemento se perde entre os três: os três saem da MESMA lista de linhas.

    Args:
        rede_id (str):
        formato (str | Unset):  Default: 'csv'.
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            body=body,
            formato=formato,
        )
    ).parsed
