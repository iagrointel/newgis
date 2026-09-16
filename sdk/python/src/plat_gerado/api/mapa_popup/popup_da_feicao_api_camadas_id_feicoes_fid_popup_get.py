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
    fid: int,
    *,
    fuso: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_fuso: None | str | Unset
    if isinstance(fuso, Unset):
        json_fuso = UNSET
    else:
        json_fuso = fuso
    params["fuso"] = json_fuso

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/camadas/{id}/feicoes/{fid}/popup".format(
            id=quote(str(id), safe=""),
            fid=quote(str(fid), safe=""),
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
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    fuso: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Popup Da Feicao

     Só o que o cliente NÃO tem: campos `servidor` (tabela companheira) e expressões (avaliadas
    aqui). `fuso`, se dado na query, sobrepõe o do inquilino só nesta chamada (é assim que o e2e prova
    a mesma data em dois fusos sem precisar reconfigurar o inquilino a cada teste; o padrão de produto
    é o fuso do inquilino, lido de `tenant.config.fuso`).

    Args:
        id (str):
        fid (int):
        fuso (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        fid=fid,
        fuso=fuso,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    fuso: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Popup Da Feicao

     Só o que o cliente NÃO tem: campos `servidor` (tabela companheira) e expressões (avaliadas
    aqui). `fuso`, se dado na query, sobrepõe o do inquilino só nesta chamada (é assim que o e2e prova
    a mesma data em dois fusos sem precisar reconfigurar o inquilino a cada teste; o padrão de produto
    é o fuso do inquilino, lido de `tenant.config.fuso`).

    Args:
        id (str):
        fid (int):
        fuso (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        id=id,
        fid=fid,
        client=client,
        fuso=fuso,
    ).parsed


async def asyncio_detailed(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    fuso: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Popup Da Feicao

     Só o que o cliente NÃO tem: campos `servidor` (tabela companheira) e expressões (avaliadas
    aqui). `fuso`, se dado na query, sobrepõe o do inquilino só nesta chamada (é assim que o e2e prova
    a mesma data em dois fusos sem precisar reconfigurar o inquilino a cada teste; o padrão de produto
    é o fuso do inquilino, lido de `tenant.config.fuso`).

    Args:
        id (str):
        fid (int):
        fuso (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        id=id,
        fid=fid,
        fuso=fuso,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    id: str,
    fid: int,
    *,
    client: AuthenticatedClient | Client,
    fuso: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Popup Da Feicao

     Só o que o cliente NÃO tem: campos `servidor` (tabela companheira) e expressões (avaliadas
    aqui). `fuso`, se dado na query, sobrepõe o do inquilino só nesta chamada (é assim que o e2e prova
    a mesma data em dois fusos sem precisar reconfigurar o inquilino a cada teste; o padrão de produto
    é o fuso do inquilino, lido de `tenant.config.fuso`).

    Args:
        id (str):
        fid (int):
        fuso (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            fid=fid,
            client=client,
            fuso=fuso,
        )
    ).parsed
