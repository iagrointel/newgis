from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    token: str,
    item: str,
    *,
    bandas: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_bandas: None | str | Unset
    if isinstance(bandas, Unset):
        json_bandas = UNSET
    else:
        json_bandas = bandas
    params["bandas"] = json_bandas

    json_expressao: None | str | Unset
    if isinstance(expressao, Unset):
        json_expressao = UNSET
    else:
        json_expressao = expressao
    params["expressao"] = json_expressao

    json_asset: None | str | Unset
    if isinstance(asset, Unset):
        json_asset = UNSET
    else:
        json_asset = asset
    params["asset"] = json_asset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/raster/{item}/estatisticas.json".format(
            token=quote(str(token), safe=""),
            item=quote(str(item), safe=""),
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
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bandas: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """mín/máx/média/desvio-padrão e percentis 2-98 por banda (ou por expressão)

     Base do esticamento por percentil/desvio-padrão do editor de estilo (item L2-02-f) e da legenda
    contínua: o editor chama esta rota, escolhe min/máx pelo método pedido e GRAVA os números no
    `plat_construtor.parametros_raster.rescale` — a legenda nunca recalcula por conta própria, só cita
    o que aqui saiu (mesma disciplina de fonte única do resto do módulo de estilo).

    Args:
        token (str):
        item (str):
        bandas (None | str | Unset): bandas a medir, ex.: 3,2,1
        expressao (None | str | Unset): mede a expressão (ex.: NDVI) em vez das bandas cruas
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        bandas=bandas,
        expressao=expressao,
        asset=asset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bandas: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """mín/máx/média/desvio-padrão e percentis 2-98 por banda (ou por expressão)

     Base do esticamento por percentil/desvio-padrão do editor de estilo (item L2-02-f) e da legenda
    contínua: o editor chama esta rota, escolhe min/máx pelo método pedido e GRAVA os números no
    `plat_construtor.parametros_raster.rescale` — a legenda nunca recalcula por conta própria, só cita
    o que aqui saiu (mesma disciplina de fonte única do resto do módulo de estilo).

    Args:
        token (str):
        item (str):
        bandas (None | str | Unset): bandas a medir, ex.: 3,2,1
        expressao (None | str | Unset): mede a expressão (ex.: NDVI) em vez das bandas cruas
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item=item,
        client=client,
        bandas=bandas,
        expressao=expressao,
        asset=asset,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bandas: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """mín/máx/média/desvio-padrão e percentis 2-98 por banda (ou por expressão)

     Base do esticamento por percentil/desvio-padrão do editor de estilo (item L2-02-f) e da legenda
    contínua: o editor chama esta rota, escolhe min/máx pelo método pedido e GRAVA os números no
    `plat_construtor.parametros_raster.rescale` — a legenda nunca recalcula por conta própria, só cita
    o que aqui saiu (mesma disciplina de fonte única do resto do módulo de estilo).

    Args:
        token (str):
        item (str):
        bandas (None | str | Unset): bandas a medir, ex.: 3,2,1
        expressao (None | str | Unset): mede a expressão (ex.: NDVI) em vez das bandas cruas
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        bandas=bandas,
        expressao=expressao,
        asset=asset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    *,
    client: AuthenticatedClient | Client,
    bandas: None | str | Unset = UNSET,
    expressao: None | str | Unset = UNSET,
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """mín/máx/média/desvio-padrão e percentis 2-98 por banda (ou por expressão)

     Base do esticamento por percentil/desvio-padrão do editor de estilo (item L2-02-f) e da legenda
    contínua: o editor chama esta rota, escolhe min/máx pelo método pedido e GRAVA os números no
    `plat_construtor.parametros_raster.rescale` — a legenda nunca recalcula por conta própria, só cita
    o que aqui saiu (mesma disciplina de fonte única do resto do módulo de estilo).

    Args:
        token (str):
        item (str):
        bandas (None | str | Unset): bandas a medir, ex.: 3,2,1
        expressao (None | str | Unset): mede a expressão (ex.: NDVI) em vez das bandas cruas
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            item=item,
            client=client,
            bandas=bandas,
            expressao=expressao,
            asset=asset,
        )
    ).parsed
