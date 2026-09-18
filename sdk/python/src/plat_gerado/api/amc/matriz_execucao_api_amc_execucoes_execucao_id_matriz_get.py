from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    execucao_id: str,
    *,
    limite: int | Unset = 500,
    deslocamento: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limite"] = limite

    params["deslocamento"] = deslocamento

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/amc/execucoes/{execucao_id}/matriz".format(
            execucao_id=quote(str(execucao_id), safe=""),
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
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 500,
    deslocamento: int | Unset = 0,
) -> Response[Any | HTTPValidationError]:
    """Matriz Execucao

     Item L3-01-g-tela-motor: valor bruto E favorabilidade de CADA fator em CADA unidade, para que a tela
    recombine no navegador quando o usuário move um peso — sem novo job e sem nova extração. É a mesma
    conta
    que `GET .../unidades/{id}/explicacao` faz para uma unidade, feita de uma vez para uma página de
    unidades.

    A favorabilidade por fator sai de `app/amc/transformacoes.py` (item L3-01-d), vetorizada por fator:
    uma
    chamada com todos os valores brutos daquele fator, não uma por unidade. Fator sem dado na unidade
    continua
    NULL — nunca 0. Quem combina os fatores no navegador é `web/js/amc/combinacao.js`, provado
    equivalente ao
    `app/amc/combinacao.py` em tests/unit/test_amc_combinacao_equivalencia.py; esta rota NÃO combina
    nada, para
    não existir uma terceira implementação da mesma conta.

    Args:
        execucao_id (str):
        limite (int | Unset):  Default: 500.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        execucao_id=execucao_id,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 500,
    deslocamento: int | Unset = 0,
) -> Any | HTTPValidationError | None:
    """Matriz Execucao

     Item L3-01-g-tela-motor: valor bruto E favorabilidade de CADA fator em CADA unidade, para que a tela
    recombine no navegador quando o usuário move um peso — sem novo job e sem nova extração. É a mesma
    conta
    que `GET .../unidades/{id}/explicacao` faz para uma unidade, feita de uma vez para uma página de
    unidades.

    A favorabilidade por fator sai de `app/amc/transformacoes.py` (item L3-01-d), vetorizada por fator:
    uma
    chamada com todos os valores brutos daquele fator, não uma por unidade. Fator sem dado na unidade
    continua
    NULL — nunca 0. Quem combina os fatores no navegador é `web/js/amc/combinacao.js`, provado
    equivalente ao
    `app/amc/combinacao.py` em tests/unit/test_amc_combinacao_equivalencia.py; esta rota NÃO combina
    nada, para
    não existir uma terceira implementação da mesma conta.

    Args:
        execucao_id (str):
        limite (int | Unset):  Default: 500.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        execucao_id=execucao_id,
        client=client,
        limite=limite,
        deslocamento=deslocamento,
    ).parsed


async def asyncio_detailed(
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 500,
    deslocamento: int | Unset = 0,
) -> Response[Any | HTTPValidationError]:
    """Matriz Execucao

     Item L3-01-g-tela-motor: valor bruto E favorabilidade de CADA fator em CADA unidade, para que a tela
    recombine no navegador quando o usuário move um peso — sem novo job e sem nova extração. É a mesma
    conta
    que `GET .../unidades/{id}/explicacao` faz para uma unidade, feita de uma vez para uma página de
    unidades.

    A favorabilidade por fator sai de `app/amc/transformacoes.py` (item L3-01-d), vetorizada por fator:
    uma
    chamada com todos os valores brutos daquele fator, não uma por unidade. Fator sem dado na unidade
    continua
    NULL — nunca 0. Quem combina os fatores no navegador é `web/js/amc/combinacao.js`, provado
    equivalente ao
    `app/amc/combinacao.py` em tests/unit/test_amc_combinacao_equivalencia.py; esta rota NÃO combina
    nada, para
    não existir uma terceira implementação da mesma conta.

    Args:
        execucao_id (str):
        limite (int | Unset):  Default: 500.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        execucao_id=execucao_id,
        limite=limite,
        deslocamento=deslocamento,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execucao_id: str,
    *,
    client: AuthenticatedClient | Client,
    limite: int | Unset = 500,
    deslocamento: int | Unset = 0,
) -> Any | HTTPValidationError | None:
    """Matriz Execucao

     Item L3-01-g-tela-motor: valor bruto E favorabilidade de CADA fator em CADA unidade, para que a tela
    recombine no navegador quando o usuário move um peso — sem novo job e sem nova extração. É a mesma
    conta
    que `GET .../unidades/{id}/explicacao` faz para uma unidade, feita de uma vez para uma página de
    unidades.

    A favorabilidade por fator sai de `app/amc/transformacoes.py` (item L3-01-d), vetorizada por fator:
    uma
    chamada com todos os valores brutos daquele fator, não uma por unidade. Fator sem dado na unidade
    continua
    NULL — nunca 0. Quem combina os fatores no navegador é `web/js/amc/combinacao.js`, provado
    equivalente ao
    `app/amc/combinacao.py` em tests/unit/test_amc_combinacao_equivalencia.py; esta rota NÃO combina
    nada, para
    não existir uma terceira implementação da mesma conta.

    Args:
        execucao_id (str):
        limite (int | Unset):  Default: 500.
        deslocamento (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            execucao_id=execucao_id,
            client=client,
            limite=limite,
            deslocamento=deslocamento,
        )
    ).parsed
