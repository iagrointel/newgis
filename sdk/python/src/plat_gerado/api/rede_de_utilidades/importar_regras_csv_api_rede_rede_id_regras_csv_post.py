from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.importacao_regras_resultado import ImportacaoRegrasResultado
from ...types import Response


def _get_kwargs(
    rede_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/regras.csv".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ImportacaoRegrasResultado | None:
    if response.status_code == 201:
        response_201 = ImportacaoRegrasResultado.from_dict(response.json())

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
) -> Response[HTTPValidationError | ImportacaoRegrasResultado]:
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
) -> Response[HTTPValidationError | ImportacaoRegrasResultado]:
    """Importar Regras Csv

     Substitui o conjunto INTEIRO de regras pelo do CSV (formato de colunas da Esri), numa transação.
    Ato de admin da rede: a ferramenta Import Rules da Esri ACRESCENTA; aqui substitui — a diferença e o
    motivo estão na paridade do item.

    Corpo NÃO é JSON (é `text/csv`): sob sessão de navegador o CSRF de `checar_escrita_sob_cookie` (ADR
    0002 §5.3, "corpo só JSON") recusa com 415 antes mesmo do privilégio ser checado — a mesma regra que
    já vale para `POST /api/arquivos` (ADR 0006, "upload só por token, nunca cookie"). Na prática, quem
    substitui o conjunto de regras por CSV usa um token de serviço com escopo `admin:inquilino`, nunca a
    sessão do navegador; a tela administrativa faz a chamada por trás com o token do próprio inquilino.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoRegrasResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | ImportacaoRegrasResultado | None:
    """Importar Regras Csv

     Substitui o conjunto INTEIRO de regras pelo do CSV (formato de colunas da Esri), numa transação.
    Ato de admin da rede: a ferramenta Import Rules da Esri ACRESCENTA; aqui substitui — a diferença e o
    motivo estão na paridade do item.

    Corpo NÃO é JSON (é `text/csv`): sob sessão de navegador o CSRF de `checar_escrita_sob_cookie` (ADR
    0002 §5.3, "corpo só JSON") recusa com 415 antes mesmo do privilégio ser checado — a mesma regra que
    já vale para `POST /api/arquivos` (ADR 0006, "upload só por token, nunca cookie"). Na prática, quem
    substitui o conjunto de regras por CSV usa um token de serviço com escopo `admin:inquilino`, nunca a
    sessão do navegador; a tela administrativa faz a chamada por trás com o token do próprio inquilino.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoRegrasResultado
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | ImportacaoRegrasResultado]:
    """Importar Regras Csv

     Substitui o conjunto INTEIRO de regras pelo do CSV (formato de colunas da Esri), numa transação.
    Ato de admin da rede: a ferramenta Import Rules da Esri ACRESCENTA; aqui substitui — a diferença e o
    motivo estão na paridade do item.

    Corpo NÃO é JSON (é `text/csv`): sob sessão de navegador o CSRF de `checar_escrita_sob_cookie` (ADR
    0002 §5.3, "corpo só JSON") recusa com 415 antes mesmo do privilégio ser checado — a mesma regra que
    já vale para `POST /api/arquivos` (ADR 0006, "upload só por token, nunca cookie"). Na prática, quem
    substitui o conjunto de regras por CSV usa um token de serviço com escopo `admin:inquilino`, nunca a
    sessão do navegador; a tela administrativa faz a chamada por trás com o token do próprio inquilino.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportacaoRegrasResultado]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | ImportacaoRegrasResultado | None:
    """Importar Regras Csv

     Substitui o conjunto INTEIRO de regras pelo do CSV (formato de colunas da Esri), numa transação.
    Ato de admin da rede: a ferramenta Import Rules da Esri ACRESCENTA; aqui substitui — a diferença e o
    motivo estão na paridade do item.

    Corpo NÃO é JSON (é `text/csv`): sob sessão de navegador o CSRF de `checar_escrita_sob_cookie` (ADR
    0002 §5.3, "corpo só JSON") recusa com 415 antes mesmo do privilégio ser checado — a mesma regra que
    já vale para `POST /api/arquivos` (ADR 0006, "upload só por token, nunca cookie"). Na prática, quem
    substitui o conjunto de regras por CSV usa um token de serviço com escopo `admin:inquilino`, nunca a
    sessão do navegador; a tela administrativa faz a chamada por trás com o token do próprio inquilino.

    Args:
        rede_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportacaoRegrasResultado
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
        )
    ).parsed
