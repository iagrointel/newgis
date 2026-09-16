from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.propagadores_entrada import PropagadoresEntrada
from ...types import Response


def _get_kwargs(
    rede_id: str,
    codigo: str,
    *,
    body: PropagadoresEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/rede/{rede_id}/tier/{codigo}/propagadores".format(
            rede_id=quote(str(rede_id), safe=""),
            codigo=quote(str(codigo), safe=""),
        ),
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
    rede_id: str,
    codigo: str,
    *,
    client: AuthenticatedClient | Client,
    body: PropagadoresEntrada,
) -> Response[Any | HTTPValidationError]:
    """Definir Propagadores

     Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede.

    Args:
        rede_id (str):
        codigo (str):
        body (PropagadoresEntrada): Atributos que um tier propaga do controlador para os elementos
            da subrede (item L4-04-b). Lista vazia
            é legítima: significa "este tier não propaga nada".

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        codigo=codigo,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    codigo: str,
    *,
    client: AuthenticatedClient | Client,
    body: PropagadoresEntrada,
) -> Any | HTTPValidationError | None:
    """Definir Propagadores

     Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede.

    Args:
        rede_id (str):
        codigo (str):
        body (PropagadoresEntrada): Atributos que um tier propaga do controlador para os elementos
            da subrede (item L4-04-b). Lista vazia
            é legítima: significa "este tier não propaga nada".

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        codigo=codigo,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    codigo: str,
    *,
    client: AuthenticatedClient | Client,
    body: PropagadoresEntrada,
) -> Response[Any | HTTPValidationError]:
    """Definir Propagadores

     Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede.

    Args:
        rede_id (str):
        codigo (str):
        body (PropagadoresEntrada): Atributos que um tier propaga do controlador para os elementos
            da subrede (item L4-04-b). Lista vazia
            é legítima: significa "este tier não propaga nada".

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        codigo=codigo,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    codigo: str,
    *,
    client: AuthenticatedClient | Client,
    body: PropagadoresEntrada,
) -> Any | HTTPValidationError | None:
    """Definir Propagadores

     Os atributos que este tier propaga do controlador para os elementos da subrede (a lista pode ser
    vazia). Cada código tem de existir no pacote da rede.

    Args:
        rede_id (str):
        codigo (str):
        body (PropagadoresEntrada): Atributos que um tier propaga do controlador para os elementos
            da subrede (item L4-04-b). Lista vazia
            é legítima: significa "este tier não propaga nada".

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            codigo=codigo,
            client=client,
            body=body,
        )
    ).parsed
