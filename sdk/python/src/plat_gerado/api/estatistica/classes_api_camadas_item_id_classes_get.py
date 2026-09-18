from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    *,
    campo: str | Unset = UNSET,
    metodo: str | Unset = UNSET,
    n: int | Unset = 5,
    filtro: None | str | Unset = UNSET,
    cortes: None | str | Unset = UNSET,
    fracao_desvio: float | None | Unset = UNSET,
    histograma_faixas: int | Unset = 10,
    classification_def: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["campo"] = campo

    params["metodo"] = metodo

    params["n"] = n

    json_filtro: None | str | Unset
    if isinstance(filtro, Unset):
        json_filtro = UNSET
    else:
        json_filtro = filtro
    params["filtro"] = json_filtro

    json_cortes: None | str | Unset
    if isinstance(cortes, Unset):
        json_cortes = UNSET
    else:
        json_cortes = cortes
    params["cortes"] = json_cortes

    json_fracao_desvio: float | None | Unset
    if isinstance(fracao_desvio, Unset):
        json_fracao_desvio = UNSET
    else:
        json_fracao_desvio = fracao_desvio
    params["fracao_desvio"] = json_fracao_desvio

    params["histograma_faixas"] = histograma_faixas

    json_classification_def: None | str | Unset
    if isinstance(classification_def, Unset):
        json_classification_def = UNSET
    else:
        json_classification_def = classification_def
    params["classificationDef"] = json_classification_def

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{item_id}/classes".format(
            item_id=quote(str(item_id), safe=""),
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
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    campo: str | Unset = UNSET,
    metodo: str | Unset = UNSET,
    n: int | Unset = 5,
    filtro: None | str | Unset = UNSET,
    cortes: None | str | Unset = UNSET,
    fracao_desvio: float | None | Unset = UNSET,
    histograma_faixas: int | Unset = 10,
    classification_def: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Classes

    Args:
        item_id (str):
        campo (str | Unset):
        metodo (str | Unset):
        n (int | Unset):  Default: 5.
        filtro (None | str | Unset):
        cortes (None | str | Unset):
        fracao_desvio (float | None | Unset):
        histograma_faixas (int | Unset):  Default: 10.
        classification_def (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        campo=campo,
        metodo=metodo,
        n=n,
        filtro=filtro,
        cortes=cortes,
        fracao_desvio=fracao_desvio,
        histograma_faixas=histograma_faixas,
        classification_def=classification_def,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    campo: str | Unset = UNSET,
    metodo: str | Unset = UNSET,
    n: int | Unset = 5,
    filtro: None | str | Unset = UNSET,
    cortes: None | str | Unset = UNSET,
    fracao_desvio: float | None | Unset = UNSET,
    histograma_faixas: int | Unset = 10,
    classification_def: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Classes

    Args:
        item_id (str):
        campo (str | Unset):
        metodo (str | Unset):
        n (int | Unset):  Default: 5.
        filtro (None | str | Unset):
        cortes (None | str | Unset):
        fracao_desvio (float | None | Unset):
        histograma_faixas (int | Unset):  Default: 10.
        classification_def (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        client=client,
        campo=campo,
        metodo=metodo,
        n=n,
        filtro=filtro,
        cortes=cortes,
        fracao_desvio=fracao_desvio,
        histograma_faixas=histograma_faixas,
        classification_def=classification_def,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    campo: str | Unset = UNSET,
    metodo: str | Unset = UNSET,
    n: int | Unset = 5,
    filtro: None | str | Unset = UNSET,
    cortes: None | str | Unset = UNSET,
    fracao_desvio: float | None | Unset = UNSET,
    histograma_faixas: int | Unset = 10,
    classification_def: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Classes

    Args:
        item_id (str):
        campo (str | Unset):
        metodo (str | Unset):
        n (int | Unset):  Default: 5.
        filtro (None | str | Unset):
        cortes (None | str | Unset):
        fracao_desvio (float | None | Unset):
        histograma_faixas (int | Unset):  Default: 10.
        classification_def (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        campo=campo,
        metodo=metodo,
        n=n,
        filtro=filtro,
        cortes=cortes,
        fracao_desvio=fracao_desvio,
        histograma_faixas=histograma_faixas,
        classification_def=classification_def,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    campo: str | Unset = UNSET,
    metodo: str | Unset = UNSET,
    n: int | Unset = 5,
    filtro: None | str | Unset = UNSET,
    cortes: None | str | Unset = UNSET,
    fracao_desvio: float | None | Unset = UNSET,
    histograma_faixas: int | Unset = 10,
    classification_def: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Classes

    Args:
        item_id (str):
        campo (str | Unset):
        metodo (str | Unset):
        n (int | Unset):  Default: 5.
        filtro (None | str | Unset):
        cortes (None | str | Unset):
        fracao_desvio (float | None | Unset):
        histograma_faixas (int | Unset):  Default: 10.
        classification_def (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
            campo=campo,
            metodo=metodo,
            n=n,
            filtro=filtro,
            cortes=cortes,
            fracao_desvio=fracao_desvio,
            histograma_faixas=histograma_faixas,
            classification_def=classification_def,
        )
    ).parsed
