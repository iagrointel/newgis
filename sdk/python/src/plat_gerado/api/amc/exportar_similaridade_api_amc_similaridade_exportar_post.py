from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.exportar_similaridade_api_amc_similaridade_exportar_post_formato import (
    ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.pedido_similaridade import PedidoSimilaridade
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: PedidoSimilaridade,
    formato: ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato
    | Unset = ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    json_formato: str | Unset = UNSET
    if not isinstance(formato, Unset):
        json_formato = formato.value

    params["formato"] = json_formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/amc/similaridade/exportar",
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
    *,
    client: AuthenticatedClient | Client,
    body: PedidoSimilaridade,
    formato: ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato
    | Unset = ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV,
) -> Response[Any | HTTPValidationError]:
    """Exportar Similaridade

     Mesmo cálculo de `/api/amc/similaridade`, exportado (item L3-17, cláusula 'export'). `formato=csv`
    (default) devolve texto CSV (posição, unidade, índice); `formato=geojson` devolve FeatureCollection
    sem
    geometria (o item não guarda geometria própria — quem tiver, sobrepõe no cliente pelo `unidade_id`).

    Args:
        formato (ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato | Unset):  Default:
            ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV.
        body (PedidoSimilaridade):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: PedidoSimilaridade,
    formato: ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato
    | Unset = ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV,
) -> Any | HTTPValidationError | None:
    """Exportar Similaridade

     Mesmo cálculo de `/api/amc/similaridade`, exportado (item L3-17, cláusula 'export'). `formato=csv`
    (default) devolve texto CSV (posição, unidade, índice); `formato=geojson` devolve FeatureCollection
    sem
    geometria (o item não guarda geometria própria — quem tiver, sobrepõe no cliente pelo `unidade_id`).

    Args:
        formato (ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato | Unset):  Default:
            ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV.
        body (PedidoSimilaridade):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PedidoSimilaridade,
    formato: ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato
    | Unset = ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV,
) -> Response[Any | HTTPValidationError]:
    """Exportar Similaridade

     Mesmo cálculo de `/api/amc/similaridade`, exportado (item L3-17, cláusula 'export'). `formato=csv`
    (default) devolve texto CSV (posição, unidade, índice); `formato=geojson` devolve FeatureCollection
    sem
    geometria (o item não guarda geometria própria — quem tiver, sobrepõe no cliente pelo `unidade_id`).

    Args:
        formato (ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato | Unset):  Default:
            ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV.
        body (PedidoSimilaridade):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: PedidoSimilaridade,
    formato: ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato
    | Unset = ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV,
) -> Any | HTTPValidationError | None:
    """Exportar Similaridade

     Mesmo cálculo de `/api/amc/similaridade`, exportado (item L3-17, cláusula 'export'). `formato=csv`
    (default) devolve texto CSV (posição, unidade, índice); `formato=geojson` devolve FeatureCollection
    sem
    geometria (o item não guarda geometria própria — quem tiver, sobrepõe no cliente pelo `unidade_id`).

    Args:
        formato (ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato | Unset):  Default:
            ExportarSimilaridadeApiAmcSimilaridadeExportarPostFormato.CSV.
        body (PedidoSimilaridade):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            formato=formato,
        )
    ).parsed
