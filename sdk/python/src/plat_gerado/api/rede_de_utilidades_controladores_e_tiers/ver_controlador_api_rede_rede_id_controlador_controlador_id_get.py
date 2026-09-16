from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.controlador import Controlador
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    rede_id: str,
    controlador_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/controlador/{controlador_id}".format(
            rede_id=quote(str(rede_id), safe=""),
            controlador_id=quote(str(controlador_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Controlador | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = Controlador.from_dict(response.json())

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
) -> Response[Controlador | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    rede_id: str,
    controlador_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Controlador | HTTPValidationError]:
    """Ver Controlador

     A ficha do controlador: qual dispositivo, qual terminal, em que tier, de que subrede, e o nó que ele
    ocupa na topologia CORRENTE (`no_id` nulo = a topologia foi reconstruída e não há nó nessa âncora).

    Args:
        rede_id (str):
        controlador_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Controlador | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        controlador_id=controlador_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    controlador_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Controlador | HTTPValidationError | None:
    """Ver Controlador

     A ficha do controlador: qual dispositivo, qual terminal, em que tier, de que subrede, e o nó que ele
    ocupa na topologia CORRENTE (`no_id` nulo = a topologia foi reconstruída e não há nó nessa âncora).

    Args:
        rede_id (str):
        controlador_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Controlador | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        controlador_id=controlador_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    controlador_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Controlador | HTTPValidationError]:
    """Ver Controlador

     A ficha do controlador: qual dispositivo, qual terminal, em que tier, de que subrede, e o nó que ele
    ocupa na topologia CORRENTE (`no_id` nulo = a topologia foi reconstruída e não há nó nessa âncora).

    Args:
        rede_id (str):
        controlador_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Controlador | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        controlador_id=controlador_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    controlador_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Controlador | HTTPValidationError | None:
    """Ver Controlador

     A ficha do controlador: qual dispositivo, qual terminal, em que tier, de que subrede, e o nó que ele
    ocupa na topologia CORRENTE (`no_id` nulo = a topologia foi reconstruída e não há nó nessa âncora).

    Args:
        rede_id (str):
        controlador_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Controlador | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            controlador_id=controlador_id,
            client=client,
        )
    ).parsed
