from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.formulario_versao_ver_api_camadas_id_formulario_versoes_versao_get_response_formulario_versao_ver_api_camadas_id_formulario_versoes_versao_get import (
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    versao: int,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/formulario/versoes/{versao}".format(
            id=quote(str(id), safe=""),
            versao=quote(str(versao), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet.from_dict(
            response.json()
        )

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
) -> Response[
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
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
    versao: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
    | HTTPValidationError
]:
    """Formulario Versao Ver

    Args:
        id (str):
        versao (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        versao=versao,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    versao: int,
    *,
    client: AuthenticatedClient | Client,
) -> (
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
    | HTTPValidationError
    | None
):
    """Formulario Versao Ver

    Args:
        id (str):
        versao (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        versao=versao,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    versao: int,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
    | HTTPValidationError
]:
    """Formulario Versao Ver

    Args:
        id (str):
        versao (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        versao=versao,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    versao: int,
    *,
    client: AuthenticatedClient | Client,
) -> (
    FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet
    | HTTPValidationError
    | None
):
    """Formulario Versao Ver

    Args:
        id (str):
        versao (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGetResponseFormularioVersaoVerApiCamadasIdFormularioVersoesVersaoGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            versao=versao,
            client=client,
        )
    ).parsed
