from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.feicoes_saida_regras import FeicoesSaidaRegras
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    limite: int | Unset = 100,
    deslocamento: int | Unset = 0,
    fid: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    json_fid: int | None | Unset
    if isinstance(fid, Unset):
        json_fid = UNSET
    else:
        json_fid = fid
    params["fid"] = json_fid

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/feicoes".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FeicoesSaidaRegras | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FeicoesSaidaRegras.from_dict(response.json())

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
) -> Response[FeicoesSaidaRegras | HTTPValidationError]:
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
    limite: int | Unset = 100,
    deslocamento: int | Unset = 0,
    fid: int | None | Unset = UNSET,
) -> Response[FeicoesSaidaRegras | HTTPValidationError]:
    """Feicoes Ler

     Feições com atributos, geometria (GeoJSON) e os CAMPOS VIRTUAIS avaliados na leitura (só leitura;
    nunca
    gravados). É a leitura que popup e tabela usam até o FeatureServer (L2-04) entrar.

    Args:
        id (str):
        limite (int | Unset):  Default: 100.
        deslocamento (int | Unset):  Default: 0.
        fid (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeicoesSaidaRegras | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
        deslocamento=deslocamento,
        fid=fid,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 100,
    deslocamento: int | Unset = 0,
    fid: int | None | Unset = UNSET,
) -> FeicoesSaidaRegras | HTTPValidationError | None:
    """Feicoes Ler

     Feições com atributos, geometria (GeoJSON) e os CAMPOS VIRTUAIS avaliados na leitura (só leitura;
    nunca
    gravados). É a leitura que popup e tabela usam até o FeatureServer (L2-04) entrar.

    Args:
        id (str):
        limite (int | Unset):  Default: 100.
        deslocamento (int | Unset):  Default: 0.
        fid (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeicoesSaidaRegras | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        limite=limite,
        deslocamento=deslocamento,
        fid=fid,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 100,
    deslocamento: int | Unset = 0,
    fid: int | None | Unset = UNSET,
) -> Response[FeicoesSaidaRegras | HTTPValidationError]:
    """Feicoes Ler

     Feições com atributos, geometria (GeoJSON) e os CAMPOS VIRTUAIS avaliados na leitura (só leitura;
    nunca
    gravados). É a leitura que popup e tabela usam até o FeatureServer (L2-04) entrar.

    Args:
        id (str):
        limite (int | Unset):  Default: 100.
        deslocamento (int | Unset):  Default: 0.
        fid (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeicoesSaidaRegras | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        limite=limite,
        deslocamento=deslocamento,
        fid=fid,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 100,
    deslocamento: int | Unset = 0,
    fid: int | None | Unset = UNSET,
) -> FeicoesSaidaRegras | HTTPValidationError | None:
    """Feicoes Ler

     Feições com atributos, geometria (GeoJSON) e os CAMPOS VIRTUAIS avaliados na leitura (só leitura;
    nunca
    gravados). É a leitura que popup e tabela usam até o FeatureServer (L2-04) entrar.

    Args:
        id (str):
        limite (int | Unset):  Default: 100.
        deslocamento (int | Unset):  Default: 0.
        fid (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeicoesSaidaRegras | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            limite=limite,
            deslocamento=deslocamento,
            fid=fid,
        )
    ).parsed
