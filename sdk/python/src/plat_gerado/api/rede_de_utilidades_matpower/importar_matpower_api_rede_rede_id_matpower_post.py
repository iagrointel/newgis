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
    prefixo: str | Unset = "",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["prefixo"] = prefixo

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/matpower".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = response.json()
        return response_201

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
    prefixo: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Importar Matpower

     Importa um caso MATPOWER (caseformat 2) para o grafo da rede. A rede precisa ter o pacote de
    ativos `transmissao-matpower` importado antes. `prefixo` entra no código externo de cada objeto e
    permite mais de um caso na mesma rede. As barras entram SEM geometria: o caseformat não tem
    coordenada, e a plataforma não inventa uma.

    Args:
        rede_id (str):
        prefixo (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        prefixo=prefixo,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    prefixo: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Importar Matpower

     Importa um caso MATPOWER (caseformat 2) para o grafo da rede. A rede precisa ter o pacote de
    ativos `transmissao-matpower` importado antes. `prefixo` entra no código externo de cada objeto e
    permite mais de um caso na mesma rede. As barras entram SEM geometria: o caseformat não tem
    coordenada, e a plataforma não inventa uma.

    Args:
        rede_id (str):
        prefixo (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        prefixo=prefixo,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    prefixo: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Importar Matpower

     Importa um caso MATPOWER (caseformat 2) para o grafo da rede. A rede precisa ter o pacote de
    ativos `transmissao-matpower` importado antes. `prefixo` entra no código externo de cada objeto e
    permite mais de um caso na mesma rede. As barras entram SEM geometria: o caseformat não tem
    coordenada, e a plataforma não inventa uma.

    Args:
        rede_id (str):
        prefixo (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        prefixo=prefixo,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    prefixo: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Importar Matpower

     Importa um caso MATPOWER (caseformat 2) para o grafo da rede. A rede precisa ter o pacote de
    ativos `transmissao-matpower` importado antes. `prefixo` entra no código externo de cada objeto e
    permite mais de um caso na mesma rede. As barras entram SEM geometria: o caseformat não tem
    coordenada, e a plataforma não inventa uma.

    Args:
        rede_id (str):
        prefixo (str | Unset):  Default: ''.

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
            prefixo=prefixo,
        )
    ).parsed
