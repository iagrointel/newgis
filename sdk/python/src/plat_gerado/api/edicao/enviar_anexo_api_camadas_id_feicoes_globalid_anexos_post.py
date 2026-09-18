from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.anexo_entrada import AnexoEntrada
from ...models.enviar_anexo_api_camadas_id_feicoes_globalid_anexos_post_response_enviar_anexo_api_camadas_id_feicoes_globalid_anexos_post import (
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    globalid: str,
    *,
    body: AnexoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/feicoes/{globalid}/anexos".format(
            id=quote(str(id), safe=""),
            globalid=quote(str(globalid), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
    | None
):
    if response.status_code == 201:
        response_201 = EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost.from_dict(
            response.json()
        )

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
) -> Response[
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: AnexoEntrada,
) -> Response[
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
]:
    """Enviar Anexo

    Args:
        id (str):
        globalid (str):
        body (AnexoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: AnexoEntrada,
) -> (
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
    | None
):
    """Enviar Anexo

    Args:
        id (str):
        globalid (str):
        body (AnexoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        globalid=globalid,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: AnexoEntrada,
) -> Response[
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
]:
    """Enviar Anexo

    Args:
        id (str):
        globalid (str):
        body (AnexoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        globalid=globalid,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    globalid: str,
    *,
    client: AuthenticatedClient | Client,
    body: AnexoEntrada,
) -> (
    EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost
    | HTTPValidationError
    | None
):
    """Enviar Anexo

    Args:
        id (str):
        globalid (str):
        body (AnexoEntrada):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPostResponseEnviarAnexoApiCamadasIdFeicoesGlobalidAnexosPost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            globalid=globalid,
            client=client,
            body=body,
        )
    ).parsed
