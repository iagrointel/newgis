from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.arquivo_url_entrada import ArquivoUrlEntrada
from ...models.arquivo_url_estado import ArquivoUrlEstado
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: ArquivoUrlEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/conexoes/{id}/arquivo".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ArquivoUrlEstado | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ArquivoUrlEstado.from_dict(response.json())

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
) -> Response[ArquivoUrlEstado | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ArquivoUrlEntrada,
) -> Response[ArquivoUrlEstado | HTTPValidationError]:
    """Arquivo Configurar

     Marca a conexão como fonte de arquivo por URL e define o intervalo da atualização agendada (item
    L6-02-h). Só faz sentido em conexão `http` no modo `copiada`: `referenciada` significa que o dado
    FICA no
    serviço de origem, e este item copia o arquivo para dentro da plataforma.

    Args:
        id (str):
        body (ArquivoUrlEntrada): Configuração da conexão como fonte de ARQUIVO por URL.
            `intervalo_s` só é usado quando `agendado`;
            os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ArquivoUrlEstado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ArquivoUrlEntrada,
) -> ArquivoUrlEstado | HTTPValidationError | None:
    """Arquivo Configurar

     Marca a conexão como fonte de arquivo por URL e define o intervalo da atualização agendada (item
    L6-02-h). Só faz sentido em conexão `http` no modo `copiada`: `referenciada` significa que o dado
    FICA no
    serviço de origem, e este item copia o arquivo para dentro da plataforma.

    Args:
        id (str):
        body (ArquivoUrlEntrada): Configuração da conexão como fonte de ARQUIVO por URL.
            `intervalo_s` só é usado quando `agendado`;
            os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ArquivoUrlEstado | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ArquivoUrlEntrada,
) -> Response[ArquivoUrlEstado | HTTPValidationError]:
    """Arquivo Configurar

     Marca a conexão como fonte de arquivo por URL e define o intervalo da atualização agendada (item
    L6-02-h). Só faz sentido em conexão `http` no modo `copiada`: `referenciada` significa que o dado
    FICA no
    serviço de origem, e este item copia o arquivo para dentro da plataforma.

    Args:
        id (str):
        body (ArquivoUrlEntrada): Configuração da conexão como fonte de ARQUIVO por URL.
            `intervalo_s` só é usado quando `agendado`;
            os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ArquivoUrlEstado | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: ArquivoUrlEntrada,
) -> ArquivoUrlEstado | HTTPValidationError | None:
    """Arquivo Configurar

     Marca a conexão como fonte de arquivo por URL e define o intervalo da atualização agendada (item
    L6-02-h). Só faz sentido em conexão `http` no modo `copiada`: `referenciada` significa que o dado
    FICA no
    serviço de origem, e este item copia o arquivo para dentro da plataforma.

    Args:
        id (str):
        body (ArquivoUrlEntrada): Configuração da conexão como fonte de ARQUIVO por URL.
            `intervalo_s` só é usado quando `agendado`;
            os limites vêm de `app/limites.py` (mínimo 15 min, o mesmo mínimo do agendador do L0-05).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ArquivoUrlEstado | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
