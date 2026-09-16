from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    rede_id: str,
    nome: str,
    *,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 5000,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tipo: None | str | Unset
    if isinstance(tipo, Unset):
        json_tipo = UNSET
    else:
        json_tipo = tipo
    params["tipo"] = json_tipo

    params["limite"] = limite

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/rede/{rede_id}/subrede/{nome}/fluxo".format(
            rede_id=quote(str(rede_id), safe=""),
            nome=quote(str(nome), safe=""),
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
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 5000,
) -> Response[Any | HTTPValidationError]:
    """Ler Fluxo

     A tabela do último cálculo deste alimentador: uma linha por elemento (barra e fase, trecho,
    transformador), ordenada pelo que dói primeiro — menor tensão, maior carregamento, maior perda. A
    ficha
    do resultado (parâmetros, versão da topologia, convergência) vem no mesmo corpo, porque o número não
    se
    lê sem a hipótese que o produziu nem sem saber se o cálculo fechou.

    Args:
        rede_id (str):
        nome (str):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 5000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        tipo=tipo,
        limite=limite,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 5000,
) -> Any | HTTPValidationError | None:
    """Ler Fluxo

     A tabela do último cálculo deste alimentador: uma linha por elemento (barra e fase, trecho,
    transformador), ordenada pelo que dói primeiro — menor tensão, maior carregamento, maior perda. A
    ficha
    do resultado (parâmetros, versão da topologia, convergência) vem no mesmo corpo, porque o número não
    se
    lê sem a hipótese que o produziu nem sem saber se o cálculo fechou.

    Args:
        rede_id (str):
        nome (str):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 5000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        nome=nome,
        client=client,
        tipo=tipo,
        limite=limite,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 5000,
) -> Response[Any | HTTPValidationError]:
    """Ler Fluxo

     A tabela do último cálculo deste alimentador: uma linha por elemento (barra e fase, trecho,
    transformador), ordenada pelo que dói primeiro — menor tensão, maior carregamento, maior perda. A
    ficha
    do resultado (parâmetros, versão da topologia, convergência) vem no mesmo corpo, porque o número não
    se
    lê sem a hipótese que o produziu nem sem saber se o cálculo fechou.

    Args:
        rede_id (str):
        nome (str):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 5000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        nome=nome,
        tipo=tipo,
        limite=limite,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    nome: str,
    *,
    client: AuthenticatedClient | Client,
    tipo: None | str | Unset = UNSET,
    limite: int | Unset = 5000,
) -> Any | HTTPValidationError | None:
    """Ler Fluxo

     A tabela do último cálculo deste alimentador: uma linha por elemento (barra e fase, trecho,
    transformador), ordenada pelo que dói primeiro — menor tensão, maior carregamento, maior perda. A
    ficha
    do resultado (parâmetros, versão da topologia, convergência) vem no mesmo corpo, porque o número não
    se
    lê sem a hipótese que o produziu nem sem saber se o cálculo fechou.

    Args:
        rede_id (str):
        nome (str):
        tipo (None | str | Unset):
        limite (int | Unset):  Default: 5000.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            nome=nome,
            client=client,
            tipo=tipo,
            limite=limite,
        )
    ).parsed
