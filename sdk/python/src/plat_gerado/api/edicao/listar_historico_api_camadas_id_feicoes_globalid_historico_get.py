from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.listar_historico_api_camadas_id_feicoes_globalid_historico_get_response_listar_historico_api_camadas_id_feicoes_globalid_historico_get import (
    ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    globalid: str,
    *,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    dif: bool | Unset = False,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    params["dif"] = dif

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/feicoes/{globalid}/historico".format(
            id=quote(str(id), safe=""),
            globalid=quote(str(globalid), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
    | None
):
    if response.status_code == 200:
        response_200 = ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet.from_dict(
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
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    dif: bool | Unset = False,
) -> Response[
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
]:
    """Listar Historico

    Args:
        id (str):
        globalid (str):
        cursor (None | str | Unset):
        limite (int | None | Unset):
        dif (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        cursor=cursor,
        limite=limite,
        dif=dif,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    dif: bool | Unset = False,
) -> (
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
    | None
):
    """Listar Historico

    Args:
        id (str):
        globalid (str):
        cursor (None | str | Unset):
        limite (int | None | Unset):
        dif (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
    """

    return sync_detailed(
        id=id,
        globalid=globalid,
        client=client,
        cursor=cursor,
        limite=limite,
        dif=dif,
    ).parsed


async def asyncio_detailed(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    dif: bool | Unset = False,
) -> Response[
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
]:
    """Listar Historico

    Args:
        id (str):
        globalid (str):
        cursor (None | str | Unset):
        limite (int | None | Unset):
        dif (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        cursor=cursor,
        limite=limite,
        dif=dif,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    cursor: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    dif: bool | Unset = False,
) -> (
    HTTPValidationError
    | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
    | None
):
    """Listar Historico

    Args:
        id (str):
        globalid (str):
        cursor (None | str | Unset):
        limite (int | None | Unset):
        dif (bool | Unset):  Default: False.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGetResponseListarHistoricoApiCamadasIdFeicoesGlobalidHistoricoGet
    """

    return (
        await asyncio_detailed(
            id=id,
            globalid=globalid,
            client=client,
            cursor=cursor,
            limite=limite,
            dif=dif,
        )
    ).parsed
