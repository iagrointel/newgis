from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    camada: str,
    z: int,
    x: int,
    y: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt".format(
            camada=quote(str(camada), safe=""),
            z=quote(str(z), safe=""),
            x=quote(str(x), safe=""),
            y=quote(str(y), safe=""),
        ),
    }

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
    camada: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Tile

     Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem
    assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela).

    Args:
        camada (str):
        z (int):
        x (int):
        y (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        z=z,
        x=x,
        y=y,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    camada: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Tile

     Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem
    assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela).

    Args:
        camada (str):
        z (int):
        x (int):
        y (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        camada=camada,
        z=z,
        x=x,
        y=y,
        client=client,
    ).parsed


async def asyncio_detailed(
    camada: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Tile

     Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem
    assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela).

    Args:
        camada (str):
        z (int):
        x (int):
        y (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        camada=camada,
        z=z,
        x=x,
        y=y,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    camada: str,
    z: int,
    x: int,
    y: int,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Tile

     Tile vetorial (MVT) da MESMA view — é este o SQL que o Martin publicaria como função. Sem
    assinatura,
    403; e mesmo que alguém chegue ao SQL por fora, a view devolve zero feição (o porteiro está nela).

    Args:
        camada (str):
        z (int):
        x (int):
        y (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            camada=camada,
            z=z,
            x=x,
            y=y,
            client=client,
        )
    ).parsed
