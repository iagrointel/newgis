from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_assinatura_entrada import AcervoAssinaturaEntrada
from ...models.acervo_assinatura_saida import AcervoAssinaturaSaida
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    camada: str,
    *,
    body: AcervoAssinaturaEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/acervo/camadas/{camada}/assinatura".format(
            camada=quote(str(camada), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoAssinaturaSaida | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = AcervoAssinaturaSaida.from_dict(response.json())

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
) -> Response[AcervoAssinaturaSaida | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAssinaturaEntrada,
) -> Response[AcervoAssinaturaSaida | HTTPValidationError]:
    """Assinar

     Item L6-01-e: assinar exige o clique no texto da licença, gravado. O clique chega como
    `aceite_licenca=true` + o sha256 do texto que a tela mostrou; o servidor grava QUEM (assinado_por),
    QUANDO (assinado_em) e O TEXTO aceito na hora (licenca_texto, cópia byte a byte, não referência).
    Sem aceite ou com sha defasado nada é gravado — e a recusa acontece ANTES do INSERT.

    Args:
        camada (str):
        body (AcervoAssinaturaEntrada): Corpo OBRIGATÓRIO de POST
            /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
            licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o
            servidor só grava se
            o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto
            novo).
            Default False/"": nunca se aceita sozinho.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoAssinaturaSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAssinaturaEntrada,
) -> AcervoAssinaturaSaida | HTTPValidationError | None:
    """Assinar

     Item L6-01-e: assinar exige o clique no texto da licença, gravado. O clique chega como
    `aceite_licenca=true` + o sha256 do texto que a tela mostrou; o servidor grava QUEM (assinado_por),
    QUANDO (assinado_em) e O TEXTO aceito na hora (licenca_texto, cópia byte a byte, não referência).
    Sem aceite ou com sha defasado nada é gravado — e a recusa acontece ANTES do INSERT.

    Args:
        camada (str):
        body (AcervoAssinaturaEntrada): Corpo OBRIGATÓRIO de POST
            /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
            licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o
            servidor só grava se
            o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto
            novo).
            Default False/"": nunca se aceita sozinho.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoAssinaturaSaida | HTTPValidationError
    """

    return sync_detailed(
        camada=camada,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAssinaturaEntrada,
) -> Response[AcervoAssinaturaSaida | HTTPValidationError]:
    """Assinar

     Item L6-01-e: assinar exige o clique no texto da licença, gravado. O clique chega como
    `aceite_licenca=true` + o sha256 do texto que a tela mostrou; o servidor grava QUEM (assinado_por),
    QUANDO (assinado_em) e O TEXTO aceito na hora (licenca_texto, cópia byte a byte, não referência).
    Sem aceite ou com sha defasado nada é gravado — e a recusa acontece ANTES do INSERT.

    Args:
        camada (str):
        body (AcervoAssinaturaEntrada): Corpo OBRIGATÓRIO de POST
            /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
            licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o
            servidor só grava se
            o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto
            novo).
            Default False/"": nunca se aceita sozinho.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoAssinaturaSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    camada: str,
    *,
    client: AuthenticatedClient | Client,
    body: AcervoAssinaturaEntrada,
) -> AcervoAssinaturaSaida | HTTPValidationError | None:
    """Assinar

     Item L6-01-e: assinar exige o clique no texto da licença, gravado. O clique chega como
    `aceite_licenca=true` + o sha256 do texto que a tela mostrou; o servidor grava QUEM (assinado_por),
    QUANDO (assinado_em) e O TEXTO aceito na hora (licenca_texto, cópia byte a byte, não referência).
    Sem aceite ou com sha defasado nada é gravado — e a recusa acontece ANTES do INSERT.

    Args:
        camada (str):
        body (AcervoAssinaturaEntrada): Corpo OBRIGATÓRIO de POST
            /api/acervo/camadas/{camada}/assinatura (item L6-01-e). O clique na
            licença chega como `aceite_licenca=true` + o sha256 do texto que estava na tela: o
            servidor só grava se
            o sha bater com o texto atual da fonte — sha defasado é 409 (a tela relê e mostra o texto
            novo).
            Default False/"": nunca se aceita sozinho.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoAssinaturaSaida | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            camada=camada,
            client=client,
            body=body,
        )
    ).parsed
