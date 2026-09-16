from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.formulario_criar import FormularioCriar
from ...models.formulario_criar_ou_renomear_api_camadas_id_formulario_post_response_formulario_criar_ou_renomear_api_camadas_id_formulario_post import (
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: FormularioCriar,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/camadas/{id}/formulario".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
    | HTTPValidationError
    | None
):
    if response.status_code == 201:
        response_201 = FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost.from_dict(
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
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
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
    body: FormularioCriar,
) -> Response[
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
    | HTTPValidationError
]:
    """Formulario Criar Ou Renomear

    Args:
        id (str):
        body (FormularioCriar):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: FormularioCriar,
) -> (
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
    | HTTPValidationError
    | None
):
    """Formulario Criar Ou Renomear

    Args:
        id (str):
        body (FormularioCriar):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: FormularioCriar,
) -> Response[
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
    | HTTPValidationError
]:
    """Formulario Criar Ou Renomear

    Args:
        id (str):
        body (FormularioCriar):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: FormularioCriar,
) -> (
    FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost
    | HTTPValidationError
    | None
):
    """Formulario Criar Ou Renomear

    Args:
        id (str):
        body (FormularioCriar):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FormularioCriarOuRenomearApiCamadasIdFormularioPostResponseFormularioCriarOuRenomearApiCamadasIdFormularioPost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
