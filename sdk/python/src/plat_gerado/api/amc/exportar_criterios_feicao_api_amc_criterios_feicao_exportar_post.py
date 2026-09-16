from http import HTTPStatus
from typing import Any, Literal

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pedido_criterios_feicao import PedidoCriteriosFeicao
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: PedidoCriteriosFeicao,
    formato: Literal["csv"] | Unset = "csv",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/amc/criterios-feicao/exportar",
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
    body: PedidoCriteriosFeicao,
    formato: Literal["csv"] | Unset = "csv",
) -> Response[Any | HTTPValidationError]:
    """Exportar Criterios Feicao

     Mesmo cálculo de `/api/amc/criterios-feicao`, em CSV: uma linha por feição, na ordem do ranque, com
    valor
    bruto e favorabilidade de cada critério. As feições filtradas saem no fim, com o motivo do filtro.

    Args:
        formato (Literal['csv'] | Unset):  Default: 'csv'.
        body (PedidoCriteriosFeicao):

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
    body: PedidoCriteriosFeicao,
    formato: Literal["csv"] | Unset = "csv",
) -> Any | HTTPValidationError | None:
    """Exportar Criterios Feicao

     Mesmo cálculo de `/api/amc/criterios-feicao`, em CSV: uma linha por feição, na ordem do ranque, com
    valor
    bruto e favorabilidade de cada critério. As feições filtradas saem no fim, com o motivo do filtro.

    Args:
        formato (Literal['csv'] | Unset):  Default: 'csv'.
        body (PedidoCriteriosFeicao):

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
    body: PedidoCriteriosFeicao,
    formato: Literal["csv"] | Unset = "csv",
) -> Response[Any | HTTPValidationError]:
    """Exportar Criterios Feicao

     Mesmo cálculo de `/api/amc/criterios-feicao`, em CSV: uma linha por feição, na ordem do ranque, com
    valor
    bruto e favorabilidade de cada critério. As feições filtradas saem no fim, com o motivo do filtro.

    Args:
        formato (Literal['csv'] | Unset):  Default: 'csv'.
        body (PedidoCriteriosFeicao):

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
    body: PedidoCriteriosFeicao,
    formato: Literal["csv"] | Unset = "csv",
) -> Any | HTTPValidationError | None:
    """Exportar Criterios Feicao

     Mesmo cálculo de `/api/amc/criterios-feicao`, em CSV: uma linha por feição, na ordem do ranque, com
    valor
    bruto e favorabilidade de cada critério. As feições filtradas saem no fim, com o motivo do filtro.

    Args:
        formato (Literal['csv'] | Unset):  Default: 'csv'.
        body (PedidoCriteriosFeicao):

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
