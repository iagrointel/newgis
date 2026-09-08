from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.pagina_auth import PaginaAuth
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    usuario_id: int | None | Unset = UNSET,
    token_id: int | None | Unset = UNSET,
    rota: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    formato: str | Unset = "json",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_usuario_id: int | None | Unset
    if isinstance(usuario_id, Unset):
        json_usuario_id = UNSET
    else:
        json_usuario_id = usuario_id
    params["usuario_id"] = json_usuario_id

    json_token_id: int | None | Unset
    if isinstance(token_id, Unset):
        json_token_id = UNSET
    else:
        json_token_id = token_id
    params["token_id"] = json_token_id

    json_rota: None | str | Unset
    if isinstance(rota, Unset):
        json_rota = UNSET
    else:
        json_rota = rota
    params["rota"] = json_rota

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    json_desde: None | str | Unset
    if isinstance(desde, Unset):
        json_desde = UNSET
    else:
        json_desde = desde
    params["desde"] = json_desde

    json_ate: None | str | Unset
    if isinstance(ate, Unset):
        json_ate = UNSET
    else:
        json_ate = ate
    params["ate"] = json_ate

    json_limite: int | None | Unset
    if isinstance(limite, Unset):
        json_limite = UNSET
    else:
        json_limite = limite
    params["limite"] = json_limite

    json_deslocamento: int | None | Unset
    if isinstance(deslocamento, Unset):
        json_deslocamento = UNSET
    else:
        json_deslocamento = deslocamento
    params["deslocamento"] = json_deslocamento

    params["formato"] = formato

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/log",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PaginaAuth | None:
    if response.status_code == 200:
        response_200 = PaginaAuth.from_dict(response.json())

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
) -> Response[HTTPValidationError | PaginaAuth]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    usuario_id: int | None | Unset = UNSET,
    token_id: int | None | Unset = UNSET,
    rota: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    formato: str | Unset = "json",
) -> Response[HTTPValidationError | PaginaAuth]:
    """Log Acesso

    Args:
        usuario_id (int | None | Unset):
        token_id (int | None | Unset):
        rota (None | str | Unset):
        status (None | str | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        formato (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        usuario_id=usuario_id,
        token_id=token_id,
        rota=rota,
        status=status,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
        formato=formato,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    usuario_id: int | None | Unset = UNSET,
    token_id: int | None | Unset = UNSET,
    rota: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    formato: str | Unset = "json",
) -> HTTPValidationError | PaginaAuth | None:
    """Log Acesso

    Args:
        usuario_id (int | None | Unset):
        token_id (int | None | Unset):
        rota (None | str | Unset):
        status (None | str | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        formato (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return sync_detailed(
        client=client,
        usuario_id=usuario_id,
        token_id=token_id,
        rota=rota,
        status=status,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
        formato=formato,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    usuario_id: int | None | Unset = UNSET,
    token_id: int | None | Unset = UNSET,
    rota: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    formato: str | Unset = "json",
) -> Response[HTTPValidationError | PaginaAuth]:
    """Log Acesso

    Args:
        usuario_id (int | None | Unset):
        token_id (int | None | Unset):
        rota (None | str | Unset):
        status (None | str | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        formato (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PaginaAuth]
    """

    kwargs = _get_kwargs(
        usuario_id=usuario_id,
        token_id=token_id,
        rota=rota,
        status=status,
        desde=desde,
        ate=ate,
        limite=limite,
        deslocamento=deslocamento,
        formato=formato,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    usuario_id: int | None | Unset = UNSET,
    token_id: int | None | Unset = UNSET,
    rota: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    desde: None | str | Unset = UNSET,
    ate: None | str | Unset = UNSET,
    limite: int | None | Unset = UNSET,
    deslocamento: int | None | Unset = UNSET,
    formato: str | Unset = "json",
) -> HTTPValidationError | PaginaAuth | None:
    """Log Acesso

    Args:
        usuario_id (int | None | Unset):
        token_id (int | None | Unset):
        rota (None | str | Unset):
        status (None | str | Unset):
        desde (None | str | Unset):
        ate (None | str | Unset):
        limite (int | None | Unset):
        deslocamento (int | None | Unset):
        formato (str | Unset):  Default: 'json'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PaginaAuth
    """

    return (
        await asyncio_detailed(
            client=client,
            usuario_id=usuario_id,
            token_id=token_id,
            rota=rota,
            status=status,
            desde=desde,
            ate=ate,
            limite=limite,
            deslocamento=deslocamento,
            formato=formato,
        )
    ).parsed
