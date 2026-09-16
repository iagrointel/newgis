from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    token: str,
    item: str,
    level: int,
    row: int,
    col: int,
    *,
    asset: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_asset: None | str | Unset
    if isinstance(asset, Unset):
        json_asset = UNSET
    else:
        json_asset = asset
    params["asset"] = json_asset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/svc/{token}/rest/services/{item}/ImageServer/tile/{level}/{row}/{col}".format(
            token=quote(str(token), safe=""),
            item=quote(str(item), safe=""),
            level=quote(str(level), safe=""),
            row=quote(str(row), safe=""),
            col=quote(str(col), safe=""),
        ),
        "params": params,
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
    token: str,
    item: str,
    level: int,
    row: int,
    col: int,
    *,
    client: AuthenticatedClient | Client,
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """ladrilho no padrão de caminho do ArcGIS (level/row/col == z/y/x)

     Mesmo ladrilho do item L1-02 (`rotas_tiles._servir`, sem reescrever nada) — só o caminho muda
    para o padrão que o Pro usa ao pedir ladrilho de um `ImageServer` (`level/row/col`, sempre PNG,
    sempre grade WebMercatorQuad). `renderingRule` (item L1-02-f) é repassado para `_servir` como
    `predef=` na forma mínima `{"rasterFunction":"<nome>"}` (a MESMA validação de `export_image`, ver
    `_nome_da_rendering_rule`); `bandIds` continua fora (não é o mesmo mecanismo de `bandas=`).

    Args:
        token (str):
        item (str):
        level (int):
        row (int):
        col (int):
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        level=level,
        row=row,
        col=col,
        asset=asset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    token: str,
    item: str,
    level: int,
    row: int,
    col: int,
    *,
    client: AuthenticatedClient | Client,
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """ladrilho no padrão de caminho do ArcGIS (level/row/col == z/y/x)

     Mesmo ladrilho do item L1-02 (`rotas_tiles._servir`, sem reescrever nada) — só o caminho muda
    para o padrão que o Pro usa ao pedir ladrilho de um `ImageServer` (`level/row/col`, sempre PNG,
    sempre grade WebMercatorQuad). `renderingRule` (item L1-02-f) é repassado para `_servir` como
    `predef=` na forma mínima `{"rasterFunction":"<nome>"}` (a MESMA validação de `export_image`, ver
    `_nome_da_rendering_rule`); `bandIds` continua fora (não é o mesmo mecanismo de `bandas=`).

    Args:
        token (str):
        item (str):
        level (int):
        row (int):
        col (int):
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        token=token,
        item=item,
        level=level,
        row=row,
        col=col,
        client=client,
        asset=asset,
    ).parsed


async def asyncio_detailed(
    token: str,
    item: str,
    level: int,
    row: int,
    col: int,
    *,
    client: AuthenticatedClient | Client,
    asset: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """ladrilho no padrão de caminho do ArcGIS (level/row/col == z/y/x)

     Mesmo ladrilho do item L1-02 (`rotas_tiles._servir`, sem reescrever nada) — só o caminho muda
    para o padrão que o Pro usa ao pedir ladrilho de um `ImageServer` (`level/row/col`, sempre PNG,
    sempre grade WebMercatorQuad). `renderingRule` (item L1-02-f) é repassado para `_servir` como
    `predef=` na forma mínima `{"rasterFunction":"<nome>"}` (a MESMA validação de `export_image`, ver
    `_nome_da_rendering_rule`); `bandIds` continua fora (não é o mesmo mecanismo de `bandas=`).

    Args:
        token (str):
        item (str):
        level (int):
        row (int):
        col (int):
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        token=token,
        item=item,
        level=level,
        row=row,
        col=col,
        asset=asset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    token: str,
    item: str,
    level: int,
    row: int,
    col: int,
    *,
    client: AuthenticatedClient | Client,
    asset: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """ladrilho no padrão de caminho do ArcGIS (level/row/col == z/y/x)

     Mesmo ladrilho do item L1-02 (`rotas_tiles._servir`, sem reescrever nada) — só o caminho muda
    para o padrão que o Pro usa ao pedir ladrilho de um `ImageServer` (`level/row/col`, sempre PNG,
    sempre grade WebMercatorQuad). `renderingRule` (item L1-02-f) é repassado para `_servir` como
    `predef=` na forma mínima `{"rasterFunction":"<nome>"}` (a MESMA validação de `export_image`, ver
    `_nome_da_rendering_rule`); `bandIds` continua fora (não é o mesmo mecanismo de `bandas=`).

    Args:
        token (str):
        item (str):
        level (int):
        row (int):
        col (int):
        asset (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            token=token,
            item=item,
            level=level,
            row=row,
            col=col,
            client=client,
            asset=asset,
        )
    ).parsed
