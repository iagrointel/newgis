from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.documento_publico import DocumentoPublico
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    inquilino: str,
    slug: str,
    *,
    link: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_link: None | str | Unset
    if isinstance(link, Unset):
        json_link = UNSET
    else:
        json_link = link
    params["link"] = json_link

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/p/{inquilino}/{slug}".format(
            inquilino=quote(str(inquilino), safe=""),
            slug=quote(str(slug), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DocumentoPublico | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DocumentoPublico.from_dict(response.json())

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
) -> Response[DocumentoPublico | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    inquilino: str,
    slug: str,
    *,
    client: AuthenticatedClient | Client,
    link: None | str | Unset = UNSET,
) -> Response[DocumentoPublico | HTTPValidationError]:
    """Documento Publico

    Args:
        inquilino (str):
        slug (str):
        link (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DocumentoPublico | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        inquilino=inquilino,
        slug=slug,
        link=link,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    inquilino: str,
    slug: str,
    *,
    client: AuthenticatedClient | Client,
    link: None | str | Unset = UNSET,
) -> DocumentoPublico | HTTPValidationError | None:
    """Documento Publico

    Args:
        inquilino (str):
        slug (str):
        link (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DocumentoPublico | HTTPValidationError
    """

    return sync_detailed(
        inquilino=inquilino,
        slug=slug,
        client=client,
        link=link,
    ).parsed


async def asyncio_detailed(
    inquilino: str,
    slug: str,
    *,
    client: AuthenticatedClient | Client,
    link: None | str | Unset = UNSET,
) -> Response[DocumentoPublico | HTTPValidationError]:
    """Documento Publico

    Args:
        inquilino (str):
        slug (str):
        link (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DocumentoPublico | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        inquilino=inquilino,
        slug=slug,
        link=link,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    inquilino: str,
    slug: str,
    *,
    client: AuthenticatedClient | Client,
    link: None | str | Unset = UNSET,
) -> DocumentoPublico | HTTPValidationError | None:
    """Documento Publico

    Args:
        inquilino (str):
        slug (str):
        link (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DocumentoPublico | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            inquilino=inquilino,
            slug=slug,
            client=client,
            link=link,
        )
    ).parsed
