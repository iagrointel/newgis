from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rede_simples_entrada import RedeSimplesEntrada
from ...types import Response


def _get_kwargs(
    *,
    body: RedeSimplesEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/simples",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    body: RedeSimplesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Criar Rede Simples

     Cria uma rede simples a partir de duas camadas do inquilino numa chamada só: rede + catálogo mínimo
    +
    feições copiadas + configuração de direção de fluxo + topologia construída. Tudo numa transação: se
    algo
    falhar, nenhuma rede pela metade fica no banco. Trabalho pesado (cópia e topologia) vai para o
    threadpool, para não segurar o laço de eventos da API inteira.

    Args:
        body (RedeSimplesEntrada): Criação de uma rede simples a partir de duas camadas do
            inquilino. `camada_ponto_id` é opcional: uma
            rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo).
            `campo_direcao` é o
            NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz
            os valores
            desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
            digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como
            digitalizada.

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
    body: RedeSimplesEntrada,
) -> Any | HTTPValidationError | None:
    """Criar Rede Simples

     Cria uma rede simples a partir de duas camadas do inquilino numa chamada só: rede + catálogo mínimo
    +
    feições copiadas + configuração de direção de fluxo + topologia construída. Tudo numa transação: se
    algo
    falhar, nenhuma rede pela metade fica no banco. Trabalho pesado (cópia e topologia) vai para o
    threadpool, para não segurar o laço de eventos da API inteira.

    Args:
        body (RedeSimplesEntrada): Criação de uma rede simples a partir de duas camadas do
            inquilino. `camada_ponto_id` é opcional: uma
            rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo).
            `campo_direcao` é o
            NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz
            os valores
            desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
            digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como
            digitalizada.

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
    body: RedeSimplesEntrada,
) -> Response[Any | HTTPValidationError]:
    """Criar Rede Simples

     Cria uma rede simples a partir de duas camadas do inquilino numa chamada só: rede + catálogo mínimo
    +
    feições copiadas + configuração de direção de fluxo + topologia construída. Tudo numa transação: se
    algo
    falhar, nenhuma rede pela metade fica no banco. Trabalho pesado (cópia e topologia) vai para o
    threadpool, para não segurar o laço de eventos da API inteira.

    Args:
        body (RedeSimplesEntrada): Criação de uma rede simples a partir de duas camadas do
            inquilino. `camada_ponto_id` é opcional: uma
            rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo).
            `campo_direcao` é o
            NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz
            os valores
            desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
            digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como
            digitalizada.

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
    body: RedeSimplesEntrada,
) -> Any | HTTPValidationError | None:
    """Criar Rede Simples

     Cria uma rede simples a partir de duas camadas do inquilino numa chamada só: rede + catálogo mínimo
    +
    feições copiadas + configuração de direção de fluxo + topologia construída. Tudo numa transação: se
    algo
    falhar, nenhuma rede pela metade fica no banco. Trabalho pesado (cópia e topologia) vai para o
    threadpool, para não segurar o laço de eventos da API inteira.

    Args:
        body (RedeSimplesEntrada): Criação de uma rede simples a partir de duas camadas do
            inquilino. `camada_ponto_id` é opcional: uma
            rede simples pode ser só de trechos (hidrografia sem camada de nó, por exemplo).
            `campo_direcao` é o
            NOME do campo da camada de linhas que carrega a direção de fluxo, e `mapa_direcao` traduz
            os valores
            desse campo (em minúsculas, sem espaço nas pontas) para o vocabulário fechado
            digitalizada/contra/indeterminada; sem `campo_direcao`, toda a rede é lida como
            digitalizada.

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
