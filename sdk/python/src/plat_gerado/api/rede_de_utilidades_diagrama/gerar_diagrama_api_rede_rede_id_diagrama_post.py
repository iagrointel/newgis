from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.diagrama_entrada import DiagramaEntrada
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    *,
    body: DiagramaEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/diagrama".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
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
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DiagramaEntrada,
) -> Response[Any | HTTPValidationError]:
    """Gerar Diagrama

     Gera o diagrama. `origem` é um objeto com `tipo`:

      * `{"tipo": "subrede", "subrede": "<nome>", "tier": "<codigo>"}` — a subrede tem de estar
    atualizada
        (o diagrama é feito do que a atualização gravou, não de um traçado novo escondido dentro da
    chamada);
      * `{"tipo": "tracado", "tracado": "subrede|conectado", "pontos_partida": [...], "barreiras":
    [...]}`;
      * `{"tipo": "selecao", "feicoes": ["<uuid>", ...]}`.

    Gerar de novo com o MESMO nome substitui o desenho e devolve o diagrama a `consistente`, mantendo o
    identificador — o link que alguém guardou continua valendo.

    Args:
        rede_id (str):
        body (DiagramaEntrada): Pedido de geração de diagrama. `origem` é validada em
            `diagrama._elementos_da_origem`, não aqui: as
            três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro
            precisa dizer qual
            subrede/feição não existe NESTA rede — coisa que pydantic não sabe.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DiagramaEntrada,
) -> Any | HTTPValidationError | None:
    """Gerar Diagrama

     Gera o diagrama. `origem` é um objeto com `tipo`:

      * `{"tipo": "subrede", "subrede": "<nome>", "tier": "<codigo>"}` — a subrede tem de estar
    atualizada
        (o diagrama é feito do que a atualização gravou, não de um traçado novo escondido dentro da
    chamada);
      * `{"tipo": "tracado", "tracado": "subrede|conectado", "pontos_partida": [...], "barreiras":
    [...]}`;
      * `{"tipo": "selecao", "feicoes": ["<uuid>", ...]}`.

    Gerar de novo com o MESMO nome substitui o desenho e devolve o diagrama a `consistente`, mantendo o
    identificador — o link que alguém guardou continua valendo.

    Args:
        rede_id (str):
        body (DiagramaEntrada): Pedido de geração de diagrama. `origem` é validada em
            `diagrama._elementos_da_origem`, não aqui: as
            três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro
            precisa dizer qual
            subrede/feição não existe NESTA rede — coisa que pydantic não sabe.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DiagramaEntrada,
) -> Response[Any | HTTPValidationError]:
    """Gerar Diagrama

     Gera o diagrama. `origem` é um objeto com `tipo`:

      * `{"tipo": "subrede", "subrede": "<nome>", "tier": "<codigo>"}` — a subrede tem de estar
    atualizada
        (o diagrama é feito do que a atualização gravou, não de um traçado novo escondido dentro da
    chamada);
      * `{"tipo": "tracado", "tracado": "subrede|conectado", "pontos_partida": [...], "barreiras":
    [...]}`;
      * `{"tipo": "selecao", "feicoes": ["<uuid>", ...]}`.

    Gerar de novo com o MESMO nome substitui o desenho e devolve o diagrama a `consistente`, mantendo o
    identificador — o link que alguém guardou continua valendo.

    Args:
        rede_id (str):
        body (DiagramaEntrada): Pedido de geração de diagrama. `origem` é validada em
            `diagrama._elementos_da_origem`, não aqui: as
            três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro
            precisa dizer qual
            subrede/feição não existe NESTA rede — coisa que pydantic não sabe.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: DiagramaEntrada,
) -> Any | HTTPValidationError | None:
    """Gerar Diagrama

     Gera o diagrama. `origem` é um objeto com `tipo`:

      * `{"tipo": "subrede", "subrede": "<nome>", "tier": "<codigo>"}` — a subrede tem de estar
    atualizada
        (o diagrama é feito do que a atualização gravou, não de um traçado novo escondido dentro da
    chamada);
      * `{"tipo": "tracado", "tracado": "subrede|conectado", "pontos_partida": [...], "barreiras":
    [...]}`;
      * `{"tipo": "selecao", "feicoes": ["<uuid>", ...]}`.

    Gerar de novo com o MESMO nome substitui o desenho e devolve o diagrama a `consistente`, mantendo o
    identificador — o link que alguém guardou continua valendo.

    Args:
        rede_id (str):
        body (DiagramaEntrada): Pedido de geração de diagrama. `origem` é validada em
            `diagrama._elementos_da_origem`, não aqui: as
            três formas (subrede, traçado, seleção) têm campos diferentes, e a mensagem de erro
            precisa dizer qual
            subrede/feição não existe NESTA rede — coisa que pydantic não sabe.

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
            body=body,
        )
    ).parsed
