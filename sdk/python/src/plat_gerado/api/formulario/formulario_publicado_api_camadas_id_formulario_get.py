from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.formulario_publicado_api_camadas_id_formulario_get_response_formulario_publicado_api_camadas_id_formulario_get import (
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/formulario".format(
            id=quote(str(id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = (
            FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet.from_dict(
                response.json()
            )
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
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
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
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
    | HTTPValidationError
]:
    """Formulario Publicado

     Formulário PUBLICADO da camada — o que a edição web e o PWA de campo renderizam. `desenho: null`
    quando a camada não tem formulário publicado ainda (a tela cai para o formulário genérico de sempre,
    campo a campo sem grupo/condicional/cálculo).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
    | HTTPValidationError
    | None
):
    """Formulario Publicado

     Formulário PUBLICADO da camada — o que a edição web e o PWA de campo renderizam. `desenho: null`
    quando a camada não tem formulário publicado ainda (a tela cai para o formulário genérico de sempre,
    campo a campo sem grupo/condicional/cálculo).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
    | HTTPValidationError
]:
    """Formulario Publicado

     Formulário PUBLICADO da camada — o que a edição web e o PWA de campo renderizam. `desenho: null`
    quando a camada não tem formulário publicado ainda (a tela cai para o formulário genérico de sempre,
    campo a campo sem grupo/condicional/cálculo).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet
    | HTTPValidationError
    | None
):
    """Formulario Publicado

     Formulário PUBLICADO da camada — o que a edição web e o PWA de campo renderizam. `desenho: null`
    quando a camada não tem formulário publicado ainda (a tela cai para o formulário genérico de sempre,
    campo a campo sem grupo/condicional/cálculo).

    Args:
        id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioPublicadoApiCamadasIdFormularioGetResponseFormularioPublicadoApiCamadasIdFormularioGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
        )
    ).parsed
