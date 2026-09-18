from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.campos_saida import CamposSaida
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    colecao: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/conexoes/{id}/colecoes/{colecao}/campos".format(
            id=quote(str(id), safe=""),
            colecao=quote(str(colecao), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CamposSaida | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CamposSaida.from_dict(response.json())

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
) -> Response[CamposSaida | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[CamposSaida | HTTPValidationError]:
    """Campos Da Colecao

     Atributos e o tipo que o SERVIÇO declara (`DescribeFeatureType` no WFS, `/queryables` no OGC API).
    Quando
    o serviço não declara nada, os tipos vêm de uma amostra de uma feição e `origem_do_tipo` diz
    `amostra` —
    inferido nunca é apresentado como declarado.

    Args:
        id (str):
        colecao (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamposSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        colecao=colecao,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
) -> CamposSaida | HTTPValidationError | None:
    """Campos Da Colecao

     Atributos e o tipo que o SERVIÇO declara (`DescribeFeatureType` no WFS, `/queryables` no OGC API).
    Quando
    o serviço não declara nada, os tipos vêm de uma amostra de uma feição e `origem_do_tipo` diz
    `amostra` —
    inferido nunca é apresentado como declarado.

    Args:
        id (str):
        colecao (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamposSaida | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        colecao=colecao,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[CamposSaida | HTTPValidationError]:
    """Campos Da Colecao

     Atributos e o tipo que o SERVIÇO declara (`DescribeFeatureType` no WFS, `/queryables` no OGC API).
    Quando
    o serviço não declara nada, os tipos vêm de uma amostra de uma feição e `origem_do_tipo` diz
    `amostra` —
    inferido nunca é apresentado como declarado.

    Args:
        id (str):
        colecao (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CamposSaida | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        colecao=colecao,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    colecao: str,
    *,
    client: AuthenticatedClient | Client,
) -> CamposSaida | HTTPValidationError | None:
    """Campos Da Colecao

     Atributos e o tipo que o SERVIÇO declara (`DescribeFeatureType` no WFS, `/queryables` no OGC API).
    Quando
    o serviço não declara nada, os tipos vêm de uma amostra de uma feição e `origem_do_tipo` diz
    `amostra` —
    inferido nunca é apresentado como declarado.

    Args:
        id (str):
        colecao (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CamposSaida | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            colecao=colecao,
            client=client,
        )
    ).parsed
