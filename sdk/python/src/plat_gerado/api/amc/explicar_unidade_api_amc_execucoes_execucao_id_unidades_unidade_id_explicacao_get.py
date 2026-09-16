from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    execucao_id: str,
    unidade_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao".format(
            execucao_id=quote(str(execucao_id), safe=""),
            unidade_id=quote(str(unidade_id), safe=""),
        ),
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
    unidade_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Explicar Unidade

     Item L3-01-f-explicacao: "por que esta unidade tem nota N". Recalcula fator → valor bruto →
    transformação →
    favorabilidade → peso → contribuição a partir de `plat.amc_fator_bruto` NA HORA (não lê nenhuma
    tabela de
    explicação gravada), e compara com `plat.amc_resultado` quando a execução já tiver resultado. O
    cálculo é o
    mesmo de `app/amc/explicacao.py`; a rota só busca as três peças (definição do modelo, pesos e
    fatores brutos).

    Args:
        execucao_id (str):
        unidade_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        execucao_id=execucao_id,
        unidade_id=unidade_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    execucao_id: str,
    unidade_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Explicar Unidade

     Item L3-01-f-explicacao: "por que esta unidade tem nota N". Recalcula fator → valor bruto →
    transformação →
    favorabilidade → peso → contribuição a partir de `plat.amc_fator_bruto` NA HORA (não lê nenhuma
    tabela de
    explicação gravada), e compara com `plat.amc_resultado` quando a execução já tiver resultado. O
    cálculo é o
    mesmo de `app/amc/explicacao.py`; a rota só busca as três peças (definição do modelo, pesos e
    fatores brutos).

    Args:
        execucao_id (str):
        unidade_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        execucao_id=execucao_id,
        unidade_id=unidade_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    execucao_id: str,
    unidade_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | HTTPValidationError]:
    """Explicar Unidade

     Item L3-01-f-explicacao: "por que esta unidade tem nota N". Recalcula fator → valor bruto →
    transformação →
    favorabilidade → peso → contribuição a partir de `plat.amc_fator_bruto` NA HORA (não lê nenhuma
    tabela de
    explicação gravada), e compara com `plat.amc_resultado` quando a execução já tiver resultado. O
    cálculo é o
    mesmo de `app/amc/explicacao.py`; a rota só busca as três peças (definição do modelo, pesos e
    fatores brutos).

    Args:
        execucao_id (str):
        unidade_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        execucao_id=execucao_id,
        unidade_id=unidade_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    execucao_id: str,
    unidade_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Any | HTTPValidationError | None:
    """Explicar Unidade

     Item L3-01-f-explicacao: "por que esta unidade tem nota N". Recalcula fator → valor bruto →
    transformação →
    favorabilidade → peso → contribuição a partir de `plat.amc_fator_bruto` NA HORA (não lê nenhuma
    tabela de
    explicação gravada), e compara com `plat.amc_resultado` quando a execução já tiver resultado. O
    cálculo é o
    mesmo de `app/amc/explicacao.py`; a rota só busca as três peças (definição do modelo, pesos e
    fatores brutos).

    Args:
        execucao_id (str):
        unidade_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            execucao_id=execucao_id,
            unidade_id=unidade_id,
            client=client,
        )
    ).parsed
