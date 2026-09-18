from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.feicoes_saida_conexao import FeicoesSaidaConexao
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    colecao: str,
    *,
    bbox: None | str | Unset = UNSET,
    datahora: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_bbox: None | str | Unset
    if isinstance(bbox, Unset):
        json_bbox = UNSET
    else:
        json_bbox = bbox
    params["bbox"] = json_bbox

    json_datahora: None | str | Unset
    if isinstance(datahora, Unset):
        json_datahora = UNSET
    else:
        json_datahora = datahora
    params["datahora"] = json_datahora

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/colecoes/{colecao}/feicoes".format(
            id=quote(str(id), safe=""),
            colecao=quote(str(colecao), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FeicoesSaidaConexao | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FeicoesSaidaConexao.from_dict(response.json())

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
) -> Response[FeicoesSaidaConexao | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    datahora: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> Response[FeicoesSaidaConexao | HTTPValidationError]:
    """Feicoes Da Colecao

     Feições ao vivo (modo referenciado), no máximo `CONEXAO_VETOR_PREVIA_MAX` por chamada. `bbox` é
    `minx,miny,maxx,maxy` em graus (CRS84) e `datahora` é o `datetime` do OGC API (instante ou
    intervalo).
    A resposta traz `numberMatched` (o total que o serviço declara) ao lado de `numberReturned` — sem os
    dois
    não dá para saber se a página é a coleção inteira.

    Args:
        id (str):
        colecao (str):
        bbox (None | str | Unset):
        datahora (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeicoesSaidaConexao | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        colecao=colecao,
        bbox=bbox,
        datahora=datahora,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    datahora: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> FeicoesSaidaConexao | HTTPValidationError | None:
    """Feicoes Da Colecao

     Feições ao vivo (modo referenciado), no máximo `CONEXAO_VETOR_PREVIA_MAX` por chamada. `bbox` é
    `minx,miny,maxx,maxy` em graus (CRS84) e `datahora` é o `datetime` do OGC API (instante ou
    intervalo).
    A resposta traz `numberMatched` (o total que o serviço declara) ao lado de `numberReturned` — sem os
    dois
    não dá para saber se a página é a coleção inteira.

    Args:
        id (str):
        colecao (str):
        bbox (None | str | Unset):
        datahora (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeicoesSaidaConexao | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        colecao=colecao,
        client=client,
        bbox=bbox,
        datahora=datahora,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    datahora: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> Response[FeicoesSaidaConexao | HTTPValidationError]:
    """Feicoes Da Colecao

     Feições ao vivo (modo referenciado), no máximo `CONEXAO_VETOR_PREVIA_MAX` por chamada. `bbox` é
    `minx,miny,maxx,maxy` em graus (CRS84) e `datahora` é o `datetime` do OGC API (instante ou
    intervalo).
    A resposta traz `numberMatched` (o total que o serviço declara) ao lado de `numberReturned` — sem os
    dois
    não dá para saber se a página é a coleção inteira.

    Args:
        id (str):
        colecao (str):
        bbox (None | str | Unset):
        datahora (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeicoesSaidaConexao | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        colecao=colecao,
        bbox=bbox,
        datahora=datahora,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
    bbox: None | str | Unset = UNSET,
    datahora: None | str | Unset = UNSET,
    limite: int | Unset = 1000,
) -> FeicoesSaidaConexao | HTTPValidationError | None:
    """Feicoes Da Colecao

     Feições ao vivo (modo referenciado), no máximo `CONEXAO_VETOR_PREVIA_MAX` por chamada. `bbox` é
    `minx,miny,maxx,maxy` em graus (CRS84) e `datahora` é o `datetime` do OGC API (instante ou
    intervalo).
    A resposta traz `numberMatched` (o total que o serviço declara) ao lado de `numberReturned` — sem os
    dois
    não dá para saber se a página é a coleção inteira.

    Args:
        id (str):
        colecao (str):
        bbox (None | str | Unset):
        datahora (None | str | Unset):
        limite (int | Unset):  Default: 1000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeicoesSaidaConexao | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            colecao=colecao,
            client=client,
            bbox=bbox,
            datahora=datahora,
            limite=limite,
        )
    ).parsed
