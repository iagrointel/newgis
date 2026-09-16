from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_uso_mensal import AcervoUsoMensal
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    ano: int | None | Unset = UNSET,
    mes: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_ano: int | None | Unset
    if isinstance(ano, Unset):
        json_ano = UNSET
    else:
        json_ano = ano
    params["ano"] = json_ano

    json_mes: int | None | Unset
    if isinstance(mes, Unset):
        json_mes = UNSET
    else:
        json_mes = mes
    params["mes"] = json_mes

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/uso/mensal",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoUsoMensal | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoUsoMensal.from_dict(response.json())

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
) -> Response[AcervoUsoMensal | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    ano: int | None | Unset = UNSET,
    mes: int | None | Unset = UNSET,
) -> Response[AcervoUsoMensal | HTTPValidationError]:
    """Uso Mensal

     Relatório mensal de uso do acervo pelo inquilino (item L6-01-e): consultas, feições servidas e em
    quantos dias do mês houve leitura, por camada. É a entrada do item L7-09 (cobrança/relatório).

    Args:
        ano (int | None | Unset):
        mes (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoUsoMensal | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        ano=ano,
        mes=mes,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    ano: int | None | Unset = UNSET,
    mes: int | None | Unset = UNSET,
) -> AcervoUsoMensal | HTTPValidationError | None:
    """Uso Mensal

     Relatório mensal de uso do acervo pelo inquilino (item L6-01-e): consultas, feições servidas e em
    quantos dias do mês houve leitura, por camada. É a entrada do item L7-09 (cobrança/relatório).

    Args:
        ano (int | None | Unset):
        mes (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoUsoMensal | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        ano=ano,
        mes=mes,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    ano: int | None | Unset = UNSET,
    mes: int | None | Unset = UNSET,
) -> Response[AcervoUsoMensal | HTTPValidationError]:
    """Uso Mensal

     Relatório mensal de uso do acervo pelo inquilino (item L6-01-e): consultas, feições servidas e em
    quantos dias do mês houve leitura, por camada. É a entrada do item L7-09 (cobrança/relatório).

    Args:
        ano (int | None | Unset):
        mes (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoUsoMensal | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        ano=ano,
        mes=mes,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    ano: int | None | Unset = UNSET,
    mes: int | None | Unset = UNSET,
) -> AcervoUsoMensal | HTTPValidationError | None:
    """Uso Mensal

     Relatório mensal de uso do acervo pelo inquilino (item L6-01-e): consultas, feições servidas e em
    quantos dias do mês houve leitura, por camada. É a entrada do item L7-09 (cobrança/relatório).

    Args:
        ano (int | None | Unset):
        mes (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoUsoMensal | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            ano=ano,
            mes=mes,
        )
    ).parsed
