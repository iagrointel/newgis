from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.preset_importado import PresetImportado
from ...models.preset_importar import PresetImportar
from ...types import Response


def _get_kwargs(
    *,
    body: PresetImportar,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/amc/presets/importar",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PresetImportado | None:
    if response.status_code == 201:
        response_201 = PresetImportado.from_dict(response.json())

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
) -> Response[HTTPValidationError | PresetImportado]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PresetImportar,
) -> Response[HTTPValidationError | PresetImportado]:
    """Importar

     Importa o documento de exportação. Com `fatores_modelo` informado, preset que declara fator
    fora do modelo é recusado com a LISTA do que falta (refutação do item).

    Args:
        body (PresetImportar): Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL:
            quando informado, preset
            que declara fator fora dessa lista é recusado com a lista do que falta (refutação do
            item).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PresetImportado]
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
    body: PresetImportar,
) -> HTTPValidationError | PresetImportado | None:
    """Importar

     Importa o documento de exportação. Com `fatores_modelo` informado, preset que declara fator
    fora do modelo é recusado com a LISTA do que falta (refutação do item).

    Args:
        body (PresetImportar): Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL:
            quando informado, preset
            que declara fator fora dessa lista é recusado com a lista do que falta (refutação do
            item).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PresetImportado
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: PresetImportar,
) -> Response[HTTPValidationError | PresetImportado]:
    """Importar

     Importa o documento de exportação. Com `fatores_modelo` informado, preset que declara fator
    fora do modelo é recusado com a LISTA do que falta (refutação do item).

    Args:
        body (PresetImportar): Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL:
            quando informado, preset
            que declara fator fora dessa lista é recusado com a lista do que falta (refutação do
            item).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PresetImportado]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: PresetImportar,
) -> HTTPValidationError | PresetImportado | None:
    """Importar

     Importa o documento de exportação. Com `fatores_modelo` informado, preset que declara fator
    fora do modelo é recusado com a LISTA do que falta (refutação do item).

    Args:
        body (PresetImportar): Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL:
            quando informado, preset
            que declara fator fora dessa lista é recusado com a lista do que falta (refutação do
            item).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PresetImportado
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
