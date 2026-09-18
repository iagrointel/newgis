from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.importar_entrada_dominios import ImportarEntradaDominios
from ...models.importar_saida import ImportarSaida
from ...types import Response


def _get_kwargs(
    *,
    body: ImportarEntradaDominios,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/dominios/importar",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ImportarSaida | None:
    if response.status_code == 200:
        response_200 = ImportarSaida.from_dict(response.json())

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
) -> Response[HTTPValidationError | ImportarSaida]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportarEntradaDominios,
) -> Response[HTTPValidationError | ImportarSaida]:
    """Importar De Servico

     Importa os domínios de um `fields`/`types` de FeatureServer ou FGDB (o mesmo objeto que a Esri
    publica em `/FeatureServer/0?f=json`). Domínio com nome já existente no inquilino é REAPROVEITADO,
    nunca
    duplicado nem sobrescrito — o que ele já vale continua valendo. Com `item_id`, as ligações campo ->
    domínio (e o subtipo, se o objeto trouxer `types`) são criadas na camada.

    Args:
        body (ImportarEntradaDominios): Recorte do JSON de uma camada de FeatureServer/FGDB:
            `fields` com `domain`, e `types` com
            `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportarSaida]
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
    body: ImportarEntradaDominios,
) -> HTTPValidationError | ImportarSaida | None:
    """Importar De Servico

     Importa os domínios de um `fields`/`types` de FeatureServer ou FGDB (o mesmo objeto que a Esri
    publica em `/FeatureServer/0?f=json`). Domínio com nome já existente no inquilino é REAPROVEITADO,
    nunca
    duplicado nem sobrescrito — o que ele já vale continua valendo. Com `item_id`, as ligações campo ->
    domínio (e o subtipo, se o objeto trouxer `types`) são criadas na camada.

    Args:
        body (ImportarEntradaDominios): Recorte do JSON de uma camada de FeatureServer/FGDB:
            `fields` com `domain`, e `types` com
            `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportarSaida
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportarEntradaDominios,
) -> Response[HTTPValidationError | ImportarSaida]:
    """Importar De Servico

     Importa os domínios de um `fields`/`types` de FeatureServer ou FGDB (o mesmo objeto que a Esri
    publica em `/FeatureServer/0?f=json`). Domínio com nome já existente no inquilino é REAPROVEITADO,
    nunca
    duplicado nem sobrescrito — o que ele já vale continua valendo. Com `item_id`, as ligações campo ->
    domínio (e o subtipo, se o objeto trouxer `types`) são criadas na camada.

    Args:
        body (ImportarEntradaDominios): Recorte do JSON de uma camada de FeatureServer/FGDB:
            `fields` com `domain`, e `types` com
            `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ImportarSaida]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ImportarEntradaDominios,
) -> HTTPValidationError | ImportarSaida | None:
    """Importar De Servico

     Importa os domínios de um `fields`/`types` de FeatureServer ou FGDB (o mesmo objeto que a Esri
    publica em `/FeatureServer/0?f=json`). Domínio com nome já existente no inquilino é REAPROVEITADO,
    nunca
    duplicado nem sobrescrito — o que ele já vale continua valendo. Com `item_id`, as ligações campo ->
    domínio (e o subtipo, se o objeto trouxer `types`) são criadas na camada.

    Args:
        body (ImportarEntradaDominios): Recorte do JSON de uma camada de FeatureServer/FGDB:
            `fields` com `domain`, e `types` com
            `domains`/`templates`. É o mesmo objeto que a Esri publica em `/FeatureServer/0?f=json`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ImportarSaida
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
