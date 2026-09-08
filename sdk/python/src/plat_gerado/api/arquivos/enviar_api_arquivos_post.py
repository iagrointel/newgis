from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    classe: str | Unset = "objeto",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["classe"] = classe

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/arquivos",
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
    *,
    client: AuthenticatedClient | Client,
    classe: str | Unset = "objeto",
) -> Response[Any | HTTPValidationError]:
    """Enviar

     Corpo cru (não multipart/form-data: o corpo INTEIRO é o arquivo). Streaming com teto de tamanho;
    acima de
    `limites.ARQUIVO_BUFFER_UNICO_BYTES` abre multipart real no Garage (contrato `objetos.parte_*`, ADR
    0005).
    Só token de serviço (`Authorization: Bearer`), nunca cookie de sessão: o CSRF sob cookie (ADR 0002
    seção 5.3)
    exige `application/json` em todo verbo de escrita, e o corpo aqui é o arquivo cru — a mesma razão
    que já fez
    a miniatura entrar em base64 (`app/catalogo/rotas_miniatura.py`). Um cliente de navegador troca a
    sessão por
    um token de escopo restrito antes de enviar (rota `POST /api/tokens`, JSON, essa sim sob cookie).

    Args:
        classe (str | Unset):  Default: 'objeto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        classe=classe,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    classe: str | Unset = "objeto",
) -> Any | HTTPValidationError | None:
    """Enviar

     Corpo cru (não multipart/form-data: o corpo INTEIRO é o arquivo). Streaming com teto de tamanho;
    acima de
    `limites.ARQUIVO_BUFFER_UNICO_BYTES` abre multipart real no Garage (contrato `objetos.parte_*`, ADR
    0005).
    Só token de serviço (`Authorization: Bearer`), nunca cookie de sessão: o CSRF sob cookie (ADR 0002
    seção 5.3)
    exige `application/json` em todo verbo de escrita, e o corpo aqui é o arquivo cru — a mesma razão
    que já fez
    a miniatura entrar em base64 (`app/catalogo/rotas_miniatura.py`). Um cliente de navegador troca a
    sessão por
    um token de escopo restrito antes de enviar (rota `POST /api/tokens`, JSON, essa sim sob cookie).

    Args:
        classe (str | Unset):  Default: 'objeto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        classe=classe,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    classe: str | Unset = "objeto",
) -> Response[Any | HTTPValidationError]:
    """Enviar

     Corpo cru (não multipart/form-data: o corpo INTEIRO é o arquivo). Streaming com teto de tamanho;
    acima de
    `limites.ARQUIVO_BUFFER_UNICO_BYTES` abre multipart real no Garage (contrato `objetos.parte_*`, ADR
    0005).
    Só token de serviço (`Authorization: Bearer`), nunca cookie de sessão: o CSRF sob cookie (ADR 0002
    seção 5.3)
    exige `application/json` em todo verbo de escrita, e o corpo aqui é o arquivo cru — a mesma razão
    que já fez
    a miniatura entrar em base64 (`app/catalogo/rotas_miniatura.py`). Um cliente de navegador troca a
    sessão por
    um token de escopo restrito antes de enviar (rota `POST /api/tokens`, JSON, essa sim sob cookie).

    Args:
        classe (str | Unset):  Default: 'objeto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        classe=classe,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    classe: str | Unset = "objeto",
) -> Any | HTTPValidationError | None:
    """Enviar

     Corpo cru (não multipart/form-data: o corpo INTEIRO é o arquivo). Streaming com teto de tamanho;
    acima de
    `limites.ARQUIVO_BUFFER_UNICO_BYTES` abre multipart real no Garage (contrato `objetos.parte_*`, ADR
    0005).
    Só token de serviço (`Authorization: Bearer`), nunca cookie de sessão: o CSRF sob cookie (ADR 0002
    seção 5.3)
    exige `application/json` em todo verbo de escrita, e o corpo aqui é o arquivo cru — a mesma razão
    que já fez
    a miniatura entrar em base64 (`app/catalogo/rotas_miniatura.py`). Um cliente de navegador troca a
    sessão por
    um token de escopo restrito antes de enviar (rota `POST /api/tokens`, JSON, essa sim sob cookie).

    Args:
        classe (str | Unset):  Default: 'objeto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            classe=classe,
        )
    ).parsed
