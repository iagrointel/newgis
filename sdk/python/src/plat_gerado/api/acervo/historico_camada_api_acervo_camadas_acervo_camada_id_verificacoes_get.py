from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.acervo_verificacao_historico import AcervoVerificacaoHistorico
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    acervo_camada_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/camadas/{acervo_camada_id}/verificacoes".format(
            acervo_camada_id=quote(str(acervo_camada_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AcervoVerificacaoHistorico | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AcervoVerificacaoHistorico.from_dict(response.json())

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
) -> Response[AcervoVerificacaoHistorico | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    acervo_camada_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[AcervoVerificacaoHistorico | HTTPValidationError]:
    """Historico Camada

     O identificador de camada é o slug `<fonte_id>/<schema>.<tabela>` (decisão B2 do L6-01-a) e tem
    barra
    dentro, por isso `:path`. A camada tem de estar na visão de frescor (que já herda o filtro de
    licença);
    fora dela é 404, indistinguível de inexistente.

    Args:
        acervo_camada_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoVerificacaoHistorico | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        acervo_camada_id=acervo_camada_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    acervo_camada_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> AcervoVerificacaoHistorico | HTTPValidationError | None:
    """Historico Camada

     O identificador de camada é o slug `<fonte_id>/<schema>.<tabela>` (decisão B2 do L6-01-a) e tem
    barra
    dentro, por isso `:path`. A camada tem de estar na visão de frescor (que já herda o filtro de
    licença);
    fora dela é 404, indistinguível de inexistente.

    Args:
        acervo_camada_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoVerificacaoHistorico | HTTPValidationError
    """

    return sync_detailed(
        acervo_camada_id=acervo_camada_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    acervo_camada_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[AcervoVerificacaoHistorico | HTTPValidationError]:
    """Historico Camada

     O identificador de camada é o slug `<fonte_id>/<schema>.<tabela>` (decisão B2 do L6-01-a) e tem
    barra
    dentro, por isso `:path`. A camada tem de estar na visão de frescor (que já herda o filtro de
    licença);
    fora dela é 404, indistinguível de inexistente.

    Args:
        acervo_camada_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AcervoVerificacaoHistorico | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        acervo_camada_id=acervo_camada_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    acervo_camada_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> AcervoVerificacaoHistorico | HTTPValidationError | None:
    """Historico Camada

     O identificador de camada é o slug `<fonte_id>/<schema>.<tabela>` (decisão B2 do L6-01-a) e tem
    barra
    dentro, por isso `:path`. A camada tem de estar na visão de frescor (que já herda o filtro de
    licença);
    fora dela é 404, indistinguível de inexistente.

    Args:
        acervo_camada_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AcervoVerificacaoHistorico | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            acervo_camada_id=acervo_camada_id,
            client=client,
        )
    ).parsed
