from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    endereco: None | str | Unset = UNSET,
    logradouro: None | str | Unset = UNSET,
    numero: int | None | Unset = UNSET,
    bairro: None | str | Unset = UNSET,
    municipio: None | str | Unset = UNSET,
    uf: None | str | Unset = UNSET,
    cep: None | str | Unset = UNSET,
    max_locations: int | Unset = 10,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_endereco: None | str | Unset
    if isinstance(endereco, Unset):
        json_endereco = UNSET
    else:
        json_endereco = endereco
    params["endereco"] = json_endereco

    json_logradouro: None | str | Unset
    if isinstance(logradouro, Unset):
        json_logradouro = UNSET
    else:
        json_logradouro = logradouro
    params["logradouro"] = json_logradouro

    json_numero: int | None | Unset
    if isinstance(numero, Unset):
        json_numero = UNSET
    else:
        json_numero = numero
    params["numero"] = json_numero

    json_bairro: None | str | Unset
    if isinstance(bairro, Unset):
        json_bairro = UNSET
    else:
        json_bairro = bairro
    params["bairro"] = json_bairro

    json_municipio: None | str | Unset
    if isinstance(municipio, Unset):
        json_municipio = UNSET
    else:
        json_municipio = municipio
    params["municipio"] = json_municipio

    json_uf: None | str | Unset
    if isinstance(uf, Unset):
        json_uf = UNSET
    else:
        json_uf = uf
    params["uf"] = json_uf

    json_cep: None | str | Unset
    if isinstance(cep, Unset):
        json_cep = UNSET
    else:
        json_cep = cep
    params["cep"] = json_cep

    params["max_locations"] = max_locations

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/geocodificar",
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
    *,
    client: AuthenticatedClient | Client,
    endereco: None | str | Unset = UNSET,
    logradouro: None | str | Unset = UNSET,
    numero: int | None | Unset = UNSET,
    bairro: None | str | Unset = UNSET,
    municipio: None | str | Unset = UNSET,
    uf: None | str | Unset = UNSET,
    cep: None | str | Unset = UNSET,
    max_locations: int | Unset = 10,
) -> Response[Any | HTTPValidationError]:
    """Geocodificar Get

     Mesma busca do POST, por parâmetro de consulta.

    Existe porque geocodificar é LEITURA e o verbo certo para leitura é GET: a caixa de pesquisa do
    visualizador de mapa (item L2-01-mapa-web) não deve passar pela porta de escrita sob cookie, que
    exige a checagem de origem do ADR 0002 seção 5.3 (e falha, corretamente, em qualquer ambiente cuja
    URL pública não seja a mesma do navegador). O POST continua valendo, com o mesmo contrato.

    Args:
        endereco (None | str | Unset):
        logradouro (None | str | Unset):
        numero (int | None | Unset):
        bairro (None | str | Unset):
        municipio (None | str | Unset):
        uf (None | str | Unset):
        cep (None | str | Unset):
        max_locations (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        endereco=endereco,
        logradouro=logradouro,
        numero=numero,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
        max_locations=max_locations,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    endereco: None | str | Unset = UNSET,
    logradouro: None | str | Unset = UNSET,
    numero: int | None | Unset = UNSET,
    bairro: None | str | Unset = UNSET,
    municipio: None | str | Unset = UNSET,
    uf: None | str | Unset = UNSET,
    cep: None | str | Unset = UNSET,
    max_locations: int | Unset = 10,
) -> Any | HTTPValidationError | None:
    """Geocodificar Get

     Mesma busca do POST, por parâmetro de consulta.

    Existe porque geocodificar é LEITURA e o verbo certo para leitura é GET: a caixa de pesquisa do
    visualizador de mapa (item L2-01-mapa-web) não deve passar pela porta de escrita sob cookie, que
    exige a checagem de origem do ADR 0002 seção 5.3 (e falha, corretamente, em qualquer ambiente cuja
    URL pública não seja a mesma do navegador). O POST continua valendo, com o mesmo contrato.

    Args:
        endereco (None | str | Unset):
        logradouro (None | str | Unset):
        numero (int | None | Unset):
        bairro (None | str | Unset):
        municipio (None | str | Unset):
        uf (None | str | Unset):
        cep (None | str | Unset):
        max_locations (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        endereco=endereco,
        logradouro=logradouro,
        numero=numero,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
        max_locations=max_locations,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    endereco: None | str | Unset = UNSET,
    logradouro: None | str | Unset = UNSET,
    numero: int | None | Unset = UNSET,
    bairro: None | str | Unset = UNSET,
    municipio: None | str | Unset = UNSET,
    uf: None | str | Unset = UNSET,
    cep: None | str | Unset = UNSET,
    max_locations: int | Unset = 10,
) -> Response[Any | HTTPValidationError]:
    """Geocodificar Get

     Mesma busca do POST, por parâmetro de consulta.

    Existe porque geocodificar é LEITURA e o verbo certo para leitura é GET: a caixa de pesquisa do
    visualizador de mapa (item L2-01-mapa-web) não deve passar pela porta de escrita sob cookie, que
    exige a checagem de origem do ADR 0002 seção 5.3 (e falha, corretamente, em qualquer ambiente cuja
    URL pública não seja a mesma do navegador). O POST continua valendo, com o mesmo contrato.

    Args:
        endereco (None | str | Unset):
        logradouro (None | str | Unset):
        numero (int | None | Unset):
        bairro (None | str | Unset):
        municipio (None | str | Unset):
        uf (None | str | Unset):
        cep (None | str | Unset):
        max_locations (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        endereco=endereco,
        logradouro=logradouro,
        numero=numero,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
        max_locations=max_locations,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    endereco: None | str | Unset = UNSET,
    logradouro: None | str | Unset = UNSET,
    numero: int | None | Unset = UNSET,
    bairro: None | str | Unset = UNSET,
    municipio: None | str | Unset = UNSET,
    uf: None | str | Unset = UNSET,
    cep: None | str | Unset = UNSET,
    max_locations: int | Unset = 10,
) -> Any | HTTPValidationError | None:
    """Geocodificar Get

     Mesma busca do POST, por parâmetro de consulta.

    Existe porque geocodificar é LEITURA e o verbo certo para leitura é GET: a caixa de pesquisa do
    visualizador de mapa (item L2-01-mapa-web) não deve passar pela porta de escrita sob cookie, que
    exige a checagem de origem do ADR 0002 seção 5.3 (e falha, corretamente, em qualquer ambiente cuja
    URL pública não seja a mesma do navegador). O POST continua valendo, com o mesmo contrato.

    Args:
        endereco (None | str | Unset):
        logradouro (None | str | Unset):
        numero (int | None | Unset):
        bairro (None | str | Unset):
        municipio (None | str | Unset):
        uf (None | str | Unset):
        cep (None | str | Unset):
        max_locations (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            endereco=endereco,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            municipio=municipio,
            uf=uf,
            cep=cep,
            max_locations=max_locations,
        )
    ).parsed
