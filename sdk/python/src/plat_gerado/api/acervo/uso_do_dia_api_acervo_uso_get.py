import datetime
from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_uso_dia import AcervoUsoDia
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    dia: datetime.date | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_dia: None | str | Unset
    if isinstance(dia, Unset):
        json_dia = UNSET
    elif isinstance(dia, datetime.date):
        json_dia = dia.isoformat()
    else:
        json_dia = dia
    params["dia"] = json_dia

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/uso",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoUsoDia | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoUsoDia.from_dict(response.json())

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
) -> Response[AcervoUsoDia | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    dia: datetime.date | None | Unset = UNSET,
) -> Response[AcervoUsoDia | HTTPValidationError]:
    """Uso Do Dia

     Registro de leitura do acervo do inquilino num dia (item L6-01-e): consultas e feições servidas por
    camada. A RLS de plat.acervo_uso recorta pelo inquilino da sessão — ninguém lê o uso de outro.

    Args:
        dia (datetime.date | None | Unset): dia no formato AAAA-MM-DD; padrão é hoje

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoUsoDia | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dia=dia,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    dia: datetime.date | None | Unset = UNSET,
) -> AcervoUsoDia | HTTPValidationError | None:
    """Uso Do Dia

     Registro de leitura do acervo do inquilino num dia (item L6-01-e): consultas e feições servidas por
    camada. A RLS de plat.acervo_uso recorta pelo inquilino da sessão — ninguém lê o uso de outro.

    Args:
        dia (datetime.date | None | Unset): dia no formato AAAA-MM-DD; padrão é hoje

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoUsoDia | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        dia=dia,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    dia: datetime.date | None | Unset = UNSET,
) -> Response[AcervoUsoDia | HTTPValidationError]:
    """Uso Do Dia

     Registro de leitura do acervo do inquilino num dia (item L6-01-e): consultas e feições servidas por
    camada. A RLS de plat.acervo_uso recorta pelo inquilino da sessão — ninguém lê o uso de outro.

    Args:
        dia (datetime.date | None | Unset): dia no formato AAAA-MM-DD; padrão é hoje

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoUsoDia | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dia=dia,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    dia: datetime.date | None | Unset = UNSET,
) -> AcervoUsoDia | HTTPValidationError | None:
    """Uso Do Dia

     Registro de leitura do acervo do inquilino num dia (item L6-01-e): consultas e feições servidas por
    camada. A RLS de plat.acervo_uso recorta pelo inquilino da sessão — ninguém lê o uso de outro.

    Args:
        dia (datetime.date | None | Unset): dia no formato AAAA-MM-DD; padrão é hoje

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoUsoDia | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            dia=dia,
        )
    ).parsed
