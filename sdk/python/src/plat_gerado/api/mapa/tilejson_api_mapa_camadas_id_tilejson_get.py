from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    agrupar: float | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_agrupar: float | None | Unset
    if isinstance(agrupar, Unset):
        json_agrupar = UNSET
    else:
        json_agrupar = agrupar
    params["agrupar"] = json_agrupar

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/mapa/camadas/{id}/tilejson".format(
            id=quote(str(id), safe=""),
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
    agrupar: float | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Tilejson

     `agrupar=<raio_px>` (item L2-02-c) troca a função de tile pela variante agrupada `t_<hex>_ag`,
    criada
    sob demanda (plat.camada_tile_agrupado_garantir) — clusters por célula calculados no tile, nunca no
    navegador. O raio viaja na URL do tile (`raio=`), lido pela função a cada pedido.

    Args:
        id (str):
        agrupar (float | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        agrupar=agrupar,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    agrupar: float | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Tilejson

     `agrupar=<raio_px>` (item L2-02-c) troca a função de tile pela variante agrupada `t_<hex>_ag`,
    criada
    sob demanda (plat.camada_tile_agrupado_garantir) — clusters por célula calculados no tile, nunca no
    navegador. O raio viaja na URL do tile (`raio=`), lido pela função a cada pedido.

    Args:
        id (str):
        agrupar (float | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        agrupar=agrupar,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    agrupar: float | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Tilejson

     `agrupar=<raio_px>` (item L2-02-c) troca a função de tile pela variante agrupada `t_<hex>_ag`,
    criada
    sob demanda (plat.camada_tile_agrupado_garantir) — clusters por célula calculados no tile, nunca no
    navegador. O raio viaja na URL do tile (`raio=`), lido pela função a cada pedido.

    Args:
        id (str):
        agrupar (float | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        agrupar=agrupar,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    agrupar: float | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Tilejson

     `agrupar=<raio_px>` (item L2-02-c) troca a função de tile pela variante agrupada `t_<hex>_ag`,
    criada
    sob demanda (plat.camada_tile_agrupado_garantir) — clusters por célula calculados no tile, nunca no
    navegador. O raio viaja na URL do tile (`raio=`), lido pela função a cada pedido.

    Args:
        id (str):
        agrupar (float | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            agrupar=agrupar,
        )
    ).parsed
