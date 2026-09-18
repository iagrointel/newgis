from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.metadado_iso_entrada import MetadadoIsoEntrada
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    body: MetadadoIsoEntrada,
    estrito: bool | Unset = False,
    aplicar: bool | Unset = True,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["estrito"] = estrito

    params["aplicar"] = aplicar

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/itens/{id}/metadado.xml".format(
            id=quote(str(id), safe=""),
        ),
        "params": params,
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoIsoEntrada,
    estrito: bool | Unset = False,
    aplicar: bool | Unset = True,
) -> Response[Any | HTTPValidationError]:
    """Metadado Iso Importar

     Importa metadado ISO 19139 no item (item L0-09-c-xml-iso-validacao): o mesmo analisador de
    `app.catalogo.metadado.analisar` (tests/unit/test_metadado_iso_importacao.py) preenche os campos do
    perfil (título/resumo/tags/créditos/termos de uso/status/extent), `dados.procedencia` (quando o tipo
    aceita — `_tipo_aceita_procedencia`) e `metadado_iso`; o que a ISO trouxe e a plataforma não guarda
    sai em
    `nao_coube`, com caminho e linha. `estrito=1` transforma o parecer do XSD (avisos) em recusa 422;
    `aplicar=false` devolve o relatório sem gravar nada. `item_ou_404` + RLS garantem que a
    leitura/escrita
    nunca atravessa inquilino.

    Args:
        id (str):
        estrito (bool | Unset):  Default: False.
        aplicar (bool | Unset):  Default: True.
        body (MetadadoIsoEntrada): Corpo de POST /api/itens/{id}/metadado.xml (item L0-09-c): o
            documento ISO 19139 inteiro num campo de
            texto. O teto aqui é de caracteres; o de bytes, que é o que vale para o analisador, está
            em
            `limites.METADADO_XML_BYTES_MAX` e é conferido em `metadado.ler_documento`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
        estrito=estrito,
        aplicar=aplicar,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoIsoEntrada,
    estrito: bool | Unset = False,
    aplicar: bool | Unset = True,
) -> Any | HTTPValidationError | None:
    """Metadado Iso Importar

     Importa metadado ISO 19139 no item (item L0-09-c-xml-iso-validacao): o mesmo analisador de
    `app.catalogo.metadado.analisar` (tests/unit/test_metadado_iso_importacao.py) preenche os campos do
    perfil (título/resumo/tags/créditos/termos de uso/status/extent), `dados.procedencia` (quando o tipo
    aceita — `_tipo_aceita_procedencia`) e `metadado_iso`; o que a ISO trouxe e a plataforma não guarda
    sai em
    `nao_coube`, com caminho e linha. `estrito=1` transforma o parecer do XSD (avisos) em recusa 422;
    `aplicar=false` devolve o relatório sem gravar nada. `item_ou_404` + RLS garantem que a
    leitura/escrita
    nunca atravessa inquilino.

    Args:
        id (str):
        estrito (bool | Unset):  Default: False.
        aplicar (bool | Unset):  Default: True.
        body (MetadadoIsoEntrada): Corpo de POST /api/itens/{id}/metadado.xml (item L0-09-c): o
            documento ISO 19139 inteiro num campo de
            texto. O teto aqui é de caracteres; o de bytes, que é o que vale para o analisador, está
            em
            `limites.METADADO_XML_BYTES_MAX` e é conferido em `metadado.ler_documento`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        body=body,
        estrito=estrito,
        aplicar=aplicar,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoIsoEntrada,
    estrito: bool | Unset = False,
    aplicar: bool | Unset = True,
) -> Response[Any | HTTPValidationError]:
    """Metadado Iso Importar

     Importa metadado ISO 19139 no item (item L0-09-c-xml-iso-validacao): o mesmo analisador de
    `app.catalogo.metadado.analisar` (tests/unit/test_metadado_iso_importacao.py) preenche os campos do
    perfil (título/resumo/tags/créditos/termos de uso/status/extent), `dados.procedencia` (quando o tipo
    aceita — `_tipo_aceita_procedencia`) e `metadado_iso`; o que a ISO trouxe e a plataforma não guarda
    sai em
    `nao_coube`, com caminho e linha. `estrito=1` transforma o parecer do XSD (avisos) em recusa 422;
    `aplicar=false` devolve o relatório sem gravar nada. `item_ou_404` + RLS garantem que a
    leitura/escrita
    nunca atravessa inquilino.

    Args:
        id (str):
        estrito (bool | Unset):  Default: False.
        aplicar (bool | Unset):  Default: True.
        body (MetadadoIsoEntrada): Corpo de POST /api/itens/{id}/metadado.xml (item L0-09-c): o
            documento ISO 19139 inteiro num campo de
            texto. O teto aqui é de caracteres; o de bytes, que é o que vale para o analisador, está
            em
            `limites.METADADO_XML_BYTES_MAX` e é conferido em `metadado.ler_documento`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        body=body,
        estrito=estrito,
        aplicar=aplicar,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    body: MetadadoIsoEntrada,
    estrito: bool | Unset = False,
    aplicar: bool | Unset = True,
) -> Any | HTTPValidationError | None:
    """Metadado Iso Importar

     Importa metadado ISO 19139 no item (item L0-09-c-xml-iso-validacao): o mesmo analisador de
    `app.catalogo.metadado.analisar` (tests/unit/test_metadado_iso_importacao.py) preenche os campos do
    perfil (título/resumo/tags/créditos/termos de uso/status/extent), `dados.procedencia` (quando o tipo
    aceita — `_tipo_aceita_procedencia`) e `metadado_iso`; o que a ISO trouxe e a plataforma não guarda
    sai em
    `nao_coube`, com caminho e linha. `estrito=1` transforma o parecer do XSD (avisos) em recusa 422;
    `aplicar=false` devolve o relatório sem gravar nada. `item_ou_404` + RLS garantem que a
    leitura/escrita
    nunca atravessa inquilino.

    Args:
        id (str):
        estrito (bool | Unset):  Default: False.
        aplicar (bool | Unset):  Default: True.
        body (MetadadoIsoEntrada): Corpo de POST /api/itens/{id}/metadado.xml (item L0-09-c): o
            documento ISO 19139 inteiro num campo de
            texto. O teto aqui é de caracteres; o de bytes, que é o que vale para o analisador, está
            em
            `limites.METADADO_XML_BYTES_MAX` e é conferido em `metadado.ler_documento`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
            estrito=estrito,
            aplicar=aplicar,
        )
    ).parsed
