from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.aplicacao_feita import AplicacaoFeita
from ...models.http_validation_error import HTTPValidationError
from ...models.preset_aplicar import PresetAplicar
from ...types import Response


def _get_kwargs(
    id: str,
    *,
    body: PresetAplicar,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/amc/presets/{id}/aplicar".format(
            id=quote(str(id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AplicacaoFeita | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AplicacaoFeita.from_dict(response.json())

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
) -> Response[AplicacaoFeita | HTTPValidationError]:
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
    body: PresetAplicar,
) -> Response[AplicacaoFeita | HTTPValidationError]:
    """Aplicar

     Aplica o preset sobre a matriz enviada e devolve a nota recalculada NA HORA (nenhum job é
    criado; a rota nem toca em plat.job). Preset que declara fator fora da matriz é recusado com a
    lista do que falta.

    Args:
        id (str):
        body (PresetAplicar): Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado)
            na ordem de
            `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do
            PRESET —
            a chamada só traz dado.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AplicacaoFeita | HTTPValidationError]
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
    body: PresetAplicar,
) -> AplicacaoFeita | HTTPValidationError | None:
    """Aplicar

     Aplica o preset sobre a matriz enviada e devolve a nota recalculada NA HORA (nenhum job é
    criado; a rota nem toca em plat.job). Preset que declara fator fora da matriz é recusado com a
    lista do que falta.

    Args:
        id (str):
        body (PresetAplicar): Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado)
            na ordem de
            `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do
            PRESET —
            a chamada só traz dado.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AplicacaoFeita | HTTPValidationError
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
    body: PresetAplicar,
) -> Response[AplicacaoFeita | HTTPValidationError]:
    """Aplicar

     Aplica o preset sobre a matriz enviada e devolve a nota recalculada NA HORA (nenhum job é
    criado; a rota nem toca em plat.job). Preset que declara fator fora da matriz é recusado com a
    lista do que falta.

    Args:
        id (str):
        body (PresetAplicar): Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado)
            na ordem de
            `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do
            PRESET —
            a chamada só traz dado.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AplicacaoFeita | HTTPValidationError]
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
    body: PresetAplicar,
) -> AplicacaoFeita | HTTPValidationError | None:
    """Aplicar

     Aplica o preset sobre a matriz enviada e devolve a nota recalculada NA HORA (nenhum job é
    criado; a rota nem toca em plat.job). Preset que declara fator fora da matriz é recusado com a
    lista do que falta.

    Args:
        id (str):
        body (PresetAplicar): Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado)
            na ordem de
            `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do
            PRESET —
            a chamada só traz dado.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AplicacaoFeita | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            id=id,
            client=client,
            body=body,
        )
    ).parsed
