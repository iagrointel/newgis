from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    *,
    ano_de: int | Unset = 2020,
    ano_ate: int | Unset = 2025,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["ano_de"] = ano_de

    params["ano_ate"] = ano_ate

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/continuidade/conjuntos".format(
            rede_id=quote(str(rede_id), safe=""),
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
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    ano_de: int | Unset = 2020,
    ano_ate: int | Unset = 2025,
) -> Response[Any | HTTPValidationError]:
    """Conjuntos

     A ficha de cada conjunto declarado pela rede: DEC e FEC apurados no ano, o limite daquele ano com o
    arquivo de onde veio e a situação.

    Conjunto que a rede declara e o arquivo da ANEEL não tem sai com `apurado` nulo e `situacao` igual a
    "sem dado" — nunca zero.

    Args:
        rede_id (str):
        ano_de (int | Unset):  Default: 2020.
        ano_ate (int | Unset):  Default: 2025.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        ano_de=ano_de,
        ano_ate=ano_ate,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    ano_de: int | Unset = 2020,
    ano_ate: int | Unset = 2025,
) -> Any | HTTPValidationError | None:
    """Conjuntos

     A ficha de cada conjunto declarado pela rede: DEC e FEC apurados no ano, o limite daquele ano com o
    arquivo de onde veio e a situação.

    Conjunto que a rede declara e o arquivo da ANEEL não tem sai com `apurado` nulo e `situacao` igual a
    "sem dado" — nunca zero.

    Args:
        rede_id (str):
        ano_de (int | Unset):  Default: 2020.
        ano_ate (int | Unset):  Default: 2025.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        ano_de=ano_de,
        ano_ate=ano_ate,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    ano_de: int | Unset = 2020,
    ano_ate: int | Unset = 2025,
) -> Response[Any | HTTPValidationError]:
    """Conjuntos

     A ficha de cada conjunto declarado pela rede: DEC e FEC apurados no ano, o limite daquele ano com o
    arquivo de onde veio e a situação.

    Conjunto que a rede declara e o arquivo da ANEEL não tem sai com `apurado` nulo e `situacao` igual a
    "sem dado" — nunca zero.

    Args:
        rede_id (str):
        ano_de (int | Unset):  Default: 2020.
        ano_ate (int | Unset):  Default: 2025.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        ano_de=ano_de,
        ano_ate=ano_ate,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    ano_de: int | Unset = 2020,
    ano_ate: int | Unset = 2025,
) -> Any | HTTPValidationError | None:
    """Conjuntos

     A ficha de cada conjunto declarado pela rede: DEC e FEC apurados no ano, o limite daquele ano com o
    arquivo de onde veio e a situação.

    Conjunto que a rede declara e o arquivo da ANEEL não tem sai com `apurado` nulo e `situacao` igual a
    "sem dado" — nunca zero.

    Args:
        rede_id (str):
        ano_de (int | Unset):  Default: 2020.
        ano_ate (int | Unset):  Default: 2025.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            ano_de=ano_de,
            ano_ate=ano_ate,
        )
    ).parsed
