from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.preencher_pendentes_entrada import PreencherPendentesEntrada
from ...types import Response


def _get_kwargs(
    *,
    body: PreencherPendentesEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/imagens/proveniencia/preencher-pendentes",
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
    body: PreencherPendentesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Proveniencia Preencher Pendentes

     Rota de administração do preenchimento retroativo (item L1-01-j, cláusula 3): busca até `limite`
    itens do inquilino cujo `plat:cadeia_origem` ainda NÃO existe (`prov.itens_pendentes`, filtro no
    jsonb
    do pgstac — nunca itera item já preenchido) e preenche, SEM reconverter — mesma lógica de
    `imagens.preencher_proveniencia`, mas inline (é leitura+escrita de metadado, nunca GDAL, então cabe
    numa requisição só). Item que precisa da cadeia MEDIDA de verdade (não reconstruída) segue
    precisando
    de `imagens.reexecutar` (fila, pesado). MEDIDO (10/09): sem o filtro de pendência, uma varredura
    repetida numa base com muito item já preenchido custava 165 s para ~217 itens só para descartar
    todos;
    com o filtro, uma base já preenchida volta em milissegundos com 0 pendente.

    Args:
        body (PreencherPendentesEntrada):

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
    body: PreencherPendentesEntrada,
) -> Any | HTTPValidationError | None:
    """Proveniencia Preencher Pendentes

     Rota de administração do preenchimento retroativo (item L1-01-j, cláusula 3): busca até `limite`
    itens do inquilino cujo `plat:cadeia_origem` ainda NÃO existe (`prov.itens_pendentes`, filtro no
    jsonb
    do pgstac — nunca itera item já preenchido) e preenche, SEM reconverter — mesma lógica de
    `imagens.preencher_proveniencia`, mas inline (é leitura+escrita de metadado, nunca GDAL, então cabe
    numa requisição só). Item que precisa da cadeia MEDIDA de verdade (não reconstruída) segue
    precisando
    de `imagens.reexecutar` (fila, pesado). MEDIDO (10/09): sem o filtro de pendência, uma varredura
    repetida numa base com muito item já preenchido custava 165 s para ~217 itens só para descartar
    todos;
    com o filtro, uma base já preenchida volta em milissegundos com 0 pendente.

    Args:
        body (PreencherPendentesEntrada):

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
    body: PreencherPendentesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Proveniencia Preencher Pendentes

     Rota de administração do preenchimento retroativo (item L1-01-j, cláusula 3): busca até `limite`
    itens do inquilino cujo `plat:cadeia_origem` ainda NÃO existe (`prov.itens_pendentes`, filtro no
    jsonb
    do pgstac — nunca itera item já preenchido) e preenche, SEM reconverter — mesma lógica de
    `imagens.preencher_proveniencia`, mas inline (é leitura+escrita de metadado, nunca GDAL, então cabe
    numa requisição só). Item que precisa da cadeia MEDIDA de verdade (não reconstruída) segue
    precisando
    de `imagens.reexecutar` (fila, pesado). MEDIDO (10/09): sem o filtro de pendência, uma varredura
    repetida numa base com muito item já preenchido custava 165 s para ~217 itens só para descartar
    todos;
    com o filtro, uma base já preenchida volta em milissegundos com 0 pendente.

    Args:
        body (PreencherPendentesEntrada):

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
    body: PreencherPendentesEntrada,
) -> Any | HTTPValidationError | None:
    """Proveniencia Preencher Pendentes

     Rota de administração do preenchimento retroativo (item L1-01-j, cláusula 3): busca até `limite`
    itens do inquilino cujo `plat:cadeia_origem` ainda NÃO existe (`prov.itens_pendentes`, filtro no
    jsonb
    do pgstac — nunca itera item já preenchido) e preenche, SEM reconverter — mesma lógica de
    `imagens.preencher_proveniencia`, mas inline (é leitura+escrita de metadado, nunca GDAL, então cabe
    numa requisição só). Item que precisa da cadeia MEDIDA de verdade (não reconstruída) segue
    precisando
    de `imagens.reexecutar` (fila, pesado). MEDIDO (10/09): sem o filtro de pendência, uma varredura
    repetida numa base com muito item já preenchido custava 165 s para ~217 itens só para descartar
    todos;
    com o filtro, uma base já preenchida volta em milissegundos com 0 pendente.

    Args:
        body (PreencherPendentesEntrada):

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
