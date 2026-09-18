from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    id: str,
    *,
    formato: None | str | Unset = UNSET,
    perfil: str | Unset = "auto",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_formato: None | str | Unset
    if isinstance(formato, Unset):
        json_formato = UNSET
    else:
        json_formato = formato
    params["formato"] = json_formato

    params["perfil"] = perfil

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/itens/{id}/metadado.xml".format(
            id=quote(str(id), safe=""),
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
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: None | str | Unset = UNSET,
    perfil: str | Unset = "auto",
) -> Response[Any | HTTPValidationError]:
    """Metadado Iso

     Metadado ISO do item (itens L0-09-metadado-catalogo e L1-27). Padrão = ISO 19139/GMD (o que o Perfil
    MGB/INDE consome); `?formato=19115-3` pede `mdb:MD_Metadata` (ISO 19115-1/19115-3, L0-09 cláusula
    2/D42);
    item raster COM ficha de imagem sai por padrão em ISO 19115-2/gmi, o perfil de imagem (item L1-27),
    que
    acrescenta aquisição, plataforma, instrumento, nuvem, ângulos do sol e a licença como restrição
    legal, e
    `?perfil=generico` força o GMD de volta. Os três são validados contra o XSD oficial ANTES de sair
    (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py --perfil iso19139|iso19115-3);
    `item_ou_404` +
    RLS de `plat.item` garantem que o token/sessão de um inquilino nunca gera o XML de item de outro.
    `formato=19115-3` e `perfil=imagem` são exclusivos: o 19115-3 é outro esquema, não outro perfil.

    Args:
        id (str):
        formato (None | str | Unset):
        perfil (str | Unset):  Default: 'auto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        formato=formato,
        perfil=perfil,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: None | str | Unset = UNSET,
    perfil: str | Unset = "auto",
) -> Any | HTTPValidationError | None:
    """Metadado Iso

     Metadado ISO do item (itens L0-09-metadado-catalogo e L1-27). Padrão = ISO 19139/GMD (o que o Perfil
    MGB/INDE consome); `?formato=19115-3` pede `mdb:MD_Metadata` (ISO 19115-1/19115-3, L0-09 cláusula
    2/D42);
    item raster COM ficha de imagem sai por padrão em ISO 19115-2/gmi, o perfil de imagem (item L1-27),
    que
    acrescenta aquisição, plataforma, instrumento, nuvem, ângulos do sol e a licença como restrição
    legal, e
    `?perfil=generico` força o GMD de volta. Os três são validados contra o XSD oficial ANTES de sair
    (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py --perfil iso19139|iso19115-3);
    `item_ou_404` +
    RLS de `plat.item` garantem que o token/sessão de um inquilino nunca gera o XML de item de outro.
    `formato=19115-3` e `perfil=imagem` são exclusivos: o 19115-3 é outro esquema, não outro perfil.

    Args:
        id (str):
        formato (None | str | Unset):
        perfil (str | Unset):  Default: 'auto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        client=client,
        formato=formato,
        perfil=perfil,
    ).parsed


async def asyncio_detailed(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: None | str | Unset = UNSET,
    perfil: str | Unset = "auto",
) -> Response[Any | HTTPValidationError]:
    """Metadado Iso

     Metadado ISO do item (itens L0-09-metadado-catalogo e L1-27). Padrão = ISO 19139/GMD (o que o Perfil
    MGB/INDE consome); `?formato=19115-3` pede `mdb:MD_Metadata` (ISO 19115-1/19115-3, L0-09 cláusula
    2/D42);
    item raster COM ficha de imagem sai por padrão em ISO 19115-2/gmi, o perfil de imagem (item L1-27),
    que
    acrescenta aquisição, plataforma, instrumento, nuvem, ângulos do sol e a licença como restrição
    legal, e
    `?perfil=generico` força o GMD de volta. Os três são validados contra o XSD oficial ANTES de sair
    (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py --perfil iso19139|iso19115-3);
    `item_ou_404` +
    RLS de `plat.item` garantem que o token/sessão de um inquilino nunca gera o XML de item de outro.
    `formato=19115-3` e `perfil=imagem` são exclusivos: o 19115-3 é outro esquema, não outro perfil.

    Args:
        id (str):
        formato (None | str | Unset):
        perfil (str | Unset):  Default: 'auto'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        formato=formato,
        perfil=perfil,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    *,
    client: AuthenticatedClient | Client,
    formato: None | str | Unset = UNSET,
    perfil: str | Unset = "auto",
) -> Any | HTTPValidationError | None:
    """Metadado Iso

     Metadado ISO do item (itens L0-09-metadado-catalogo e L1-27). Padrão = ISO 19139/GMD (o que o Perfil
    MGB/INDE consome); `?formato=19115-3` pede `mdb:MD_Metadata` (ISO 19115-1/19115-3, L0-09 cláusula
    2/D42);
    item raster COM ficha de imagem sai por padrão em ISO 19115-2/gmi, o perfil de imagem (item L1-27),
    que
    acrescenta aquisição, plataforma, instrumento, nuvem, ângulos do sol e a licença como restrição
    legal, e
    `?perfil=generico` força o GMD de volta. Os três são validados contra o XSD oficial ANTES de sair
    (docs/xsd/cache/, baixado por docs/xsd/baixar_iso19139.py --perfil iso19139|iso19115-3);
    `item_ou_404` +
    RLS de `plat.item` garantem que o token/sessão de um inquilino nunca gera o XML de item de outro.
    `formato=19115-3` e `perfil=imagem` são exclusivos: o 19115-3 é outro esquema, não outro perfil.

    Args:
        id (str):
        formato (None | str | Unset):
        perfil (str | Unset):  Default: 'auto'.

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
            formato=formato,
            perfil=perfil,
        )
    ).parsed
