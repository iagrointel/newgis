from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.csv_entrada import CsvEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CsvEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/dominios/csv",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: CsvEntrada,
) -> Response[Any | HTTPValidationError]:
    """Importar Csv

     Edição em massa: o campo `csv` traz o arquivo inteiro. Cada domínio do arquivo é criado ou
    substituído
    por completo — o arquivo é a lista final de valores, não um delta. Domínio ausente do arquivo não é
    tocado (remover é `DELETE /api/dominios/{id}`, que confere uso).

    Por que o CSV vem dentro de um JSON e não como `text/csv` no corpo: escrita sob cookie exige
    `Content-Type: application/json` (ADR 0002 seção 5.3, defesa de CSRF) — um corpo `text/csv` é
    recusado
    com 415 antes de chegar aqui, e a tela não tem como mudar isso.

    Args:
        body (CsvEntrada): O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só
            aceita application/json.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: CsvEntrada,
) -> Any | HTTPValidationError | None:
    """Importar Csv

     Edição em massa: o campo `csv` traz o arquivo inteiro. Cada domínio do arquivo é criado ou
    substituído
    por completo — o arquivo é a lista final de valores, não um delta. Domínio ausente do arquivo não é
    tocado (remover é `DELETE /api/dominios/{id}`, que confere uso).

    Por que o CSV vem dentro de um JSON e não como `text/csv` no corpo: escrita sob cookie exige
    `Content-Type: application/json` (ADR 0002 seção 5.3, defesa de CSRF) — um corpo `text/csv` é
    recusado
    com 415 antes de chegar aqui, e a tela não tem como mudar isso.

    Args:
        body (CsvEntrada): O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só
            aceita application/json.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CsvEntrada,
) -> Response[Any | HTTPValidationError]:
    """Importar Csv

     Edição em massa: o campo `csv` traz o arquivo inteiro. Cada domínio do arquivo é criado ou
    substituído
    por completo — o arquivo é a lista final de valores, não um delta. Domínio ausente do arquivo não é
    tocado (remover é `DELETE /api/dominios/{id}`, que confere uso).

    Por que o CSV vem dentro de um JSON e não como `text/csv` no corpo: escrita sob cookie exige
    `Content-Type: application/json` (ADR 0002 seção 5.3, defesa de CSRF) — um corpo `text/csv` é
    recusado
    com 415 antes de chegar aqui, e a tela não tem como mudar isso.

    Args:
        body (CsvEntrada): O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só
            aceita application/json.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CsvEntrada,
) -> Any | HTTPValidationError | None:
    """Importar Csv

     Edição em massa: o campo `csv` traz o arquivo inteiro. Cada domínio do arquivo é criado ou
    substituído
    por completo — o arquivo é a lista final de valores, não um delta. Domínio ausente do arquivo não é
    tocado (remover é `DELETE /api/dominios/{id}`, que confere uso).

    Por que o CSV vem dentro de um JSON e não como `text/csv` no corpo: escrita sob cookie exige
    `Content-Type: application/json` (ADR 0002 seção 5.3, defesa de CSRF) — um corpo `text/csv` é
    recusado
    com 415 antes de chegar aqui, e a tela não tem como mudar isso.

    Args:
        body (CsvEntrada): O CSV inteiro num campo de texto (até 4 MiB): escrita sob cookie só
            aceita application/json.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
