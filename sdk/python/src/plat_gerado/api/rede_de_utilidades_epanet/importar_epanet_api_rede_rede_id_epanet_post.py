from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.epanet_importacao_aceita import EpanetImportacaoAceita
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    crs_epsg: int | None | Unset = UNSET,
    nome_arquivo: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_crs_epsg: int | None | Unset
    if isinstance(crs_epsg, Unset):
        json_crs_epsg = UNSET
    else:
        json_crs_epsg = crs_epsg
    params["crs_epsg"] = json_crs_epsg

    json_nome_arquivo: None | str | Unset
    if isinstance(nome_arquivo, Unset):
        json_nome_arquivo = UNSET
    else:
        json_nome_arquivo = nome_arquivo
    params["nome_arquivo"] = json_nome_arquivo

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/epanet".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EpanetImportacaoAceita | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = EpanetImportacaoAceita.from_dict(response.json())

        return response_202

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[EpanetImportacaoAceita | HTTPValidationError]:
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
    crs_epsg: int | None | Unset = UNSET,
    nome_arquivo: None | str | Unset = UNSET,
) -> Response[EpanetImportacaoAceita | HTTPValidationError]:
    """Importar Epanet

     Enfileira a importação do `.inp` recebido no corpo. `crs_epsg` é obrigatório quando as coordenadas
    do
    arquivo não são WGS84 (faixa -180..180/-90..90) — o job recusa sem adivinhar a projeção.

    Args:
        rede_id (str):
        crs_epsg (int | None | Unset):
        nome_arquivo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpanetImportacaoAceita | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        crs_epsg=crs_epsg,
        nome_arquivo=nome_arquivo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    crs_epsg: int | None | Unset = UNSET,
    nome_arquivo: None | str | Unset = UNSET,
) -> EpanetImportacaoAceita | HTTPValidationError | None:
    """Importar Epanet

     Enfileira a importação do `.inp` recebido no corpo. `crs_epsg` é obrigatório quando as coordenadas
    do
    arquivo não são WGS84 (faixa -180..180/-90..90) — o job recusa sem adivinhar a projeção.

    Args:
        rede_id (str):
        crs_epsg (int | None | Unset):
        nome_arquivo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpanetImportacaoAceita | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        crs_epsg=crs_epsg,
        nome_arquivo=nome_arquivo,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    crs_epsg: int | None | Unset = UNSET,
    nome_arquivo: None | str | Unset = UNSET,
) -> Response[EpanetImportacaoAceita | HTTPValidationError]:
    """Importar Epanet

     Enfileira a importação do `.inp` recebido no corpo. `crs_epsg` é obrigatório quando as coordenadas
    do
    arquivo não são WGS84 (faixa -180..180/-90..90) — o job recusa sem adivinhar a projeção.

    Args:
        rede_id (str):
        crs_epsg (int | None | Unset):
        nome_arquivo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EpanetImportacaoAceita | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        crs_epsg=crs_epsg,
        nome_arquivo=nome_arquivo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    crs_epsg: int | None | Unset = UNSET,
    nome_arquivo: None | str | Unset = UNSET,
) -> EpanetImportacaoAceita | HTTPValidationError | None:
    """Importar Epanet

     Enfileira a importação do `.inp` recebido no corpo. `crs_epsg` é obrigatório quando as coordenadas
    do
    arquivo não são WGS84 (faixa -180..180/-90..90) — o job recusa sem adivinhar a projeção.

    Args:
        rede_id (str):
        crs_epsg (int | None | Unset):
        nome_arquivo (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EpanetImportacaoAceita | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            crs_epsg=crs_epsg,
            nome_arquivo=nome_arquivo,
        )
    ).parsed
