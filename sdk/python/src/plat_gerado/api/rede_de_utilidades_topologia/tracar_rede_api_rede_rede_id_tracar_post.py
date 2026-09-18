from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tracado_entrada import TracadoEntrada
from ...types import Response


def _get_kwargs(
    rede_id: str,
    *,
    body: TracadoEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/rede/{rede_id}/tracar".format(
            rede_id=quote(str(rede_id), safe=""),
        ),
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
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
) -> Response[Any | HTTPValidationError]:
    """Tracar Rede

     Traça `tipo=conectado` (tudo que se alcança do(s) ponto(s) de partida, respeitando a
    traversabilidade
    de cada dispositivo e as barreiras) ou `tipo=subrede` (o mesmo, mas parando em qualquer controlador
    de
    outra subrede — hoje, categoria `transformacao` do pacote); ou, item L4-02-d-lacos-e-caminho-curto:
    `tipo=lacos` (ciclos por componente biconexo, `pgr_biconnectedComponents`), `tipo=isolados`
    (elementos sem
    caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`,
    `pgr_connectedComponents`)
    ou `tipo=caminho_curto` (origem em `pontos_partida[0]`, `destino`, custo = `atributo_custo` ou o
    comprimento geodésico por padrão; `k` alternativas por `pgr_ksp` quando `k>1`); ou, item
    itens L4-18-rede-simples-trace-network e L4-02-b-montante-jusante, `tipo=montante`/`tipo=jusante`:
    numa
    rede com controlador de subrede em tier hierárquico o sentido vem da DISTÂNCIA AO CONTROLADOR
    (jusante de
    um ponto = o que só chega ao controlador passando por ele); sem controlador, vem da DIREÇÃO DE FLUXO
    declarada no atributo `direcao_fluxo` de cada trecho (digitalizada/contra/indeterminada), que para,
    com
    aviso por trecho, em toda aresta indeterminada. `origem_direcao` no pedido impõe um dos dois, e a
    resposta sempre diz qual valeu; em malha (tier particionado) sem atributo, e em laço, a resposta é
    `direcao='indeterminado'` com o motivo e os nós do laço, nunca um sentido arbitrado. Ponto de
    partida, destino
    e barreira são a mesma forma: feição+terminal ou coordenada com tolerância. Não exige `rede.editar`:
    é
    leitura sobre o índice já construído (mesmo privilégio de `topologia/alcance`), nunca grava nada na
    rede.
    Sem `response_model` fixo porque cada `tipo` devolve um formato diferente (ver `docs/openapi.json`
    para o
    formato de cada um, e os testes de cada item para exemplo).

    Args:
        rede_id (str):
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
) -> Any | HTTPValidationError | None:
    """Tracar Rede

     Traça `tipo=conectado` (tudo que se alcança do(s) ponto(s) de partida, respeitando a
    traversabilidade
    de cada dispositivo e as barreiras) ou `tipo=subrede` (o mesmo, mas parando em qualquer controlador
    de
    outra subrede — hoje, categoria `transformacao` do pacote); ou, item L4-02-d-lacos-e-caminho-curto:
    `tipo=lacos` (ciclos por componente biconexo, `pgr_biconnectedComponents`), `tipo=isolados`
    (elementos sem
    caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`,
    `pgr_connectedComponents`)
    ou `tipo=caminho_curto` (origem em `pontos_partida[0]`, `destino`, custo = `atributo_custo` ou o
    comprimento geodésico por padrão; `k` alternativas por `pgr_ksp` quando `k>1`); ou, item
    itens L4-18-rede-simples-trace-network e L4-02-b-montante-jusante, `tipo=montante`/`tipo=jusante`:
    numa
    rede com controlador de subrede em tier hierárquico o sentido vem da DISTÂNCIA AO CONTROLADOR
    (jusante de
    um ponto = o que só chega ao controlador passando por ele); sem controlador, vem da DIREÇÃO DE FLUXO
    declarada no atributo `direcao_fluxo` de cada trecho (digitalizada/contra/indeterminada), que para,
    com
    aviso por trecho, em toda aresta indeterminada. `origem_direcao` no pedido impõe um dos dois, e a
    resposta sempre diz qual valeu; em malha (tier particionado) sem atributo, e em laço, a resposta é
    `direcao='indeterminado'` com o motivo e os nós do laço, nunca um sentido arbitrado. Ponto de
    partida, destino
    e barreira são a mesma forma: feição+terminal ou coordenada com tolerância. Não exige `rede.editar`:
    é
    leitura sobre o índice já construído (mesmo privilégio de `topologia/alcance`), nunca grava nada na
    rede.
    Sem `response_model` fixo porque cada `tipo` devolve um formato diferente (ver `docs/openapi.json`
    para o
    formato de cada um, e os testes de cada item para exemplo).

    Args:
        rede_id (str):
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        rede_id=rede_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
) -> Response[Any | HTTPValidationError]:
    """Tracar Rede

     Traça `tipo=conectado` (tudo que se alcança do(s) ponto(s) de partida, respeitando a
    traversabilidade
    de cada dispositivo e as barreiras) ou `tipo=subrede` (o mesmo, mas parando em qualquer controlador
    de
    outra subrede — hoje, categoria `transformacao` do pacote); ou, item L4-02-d-lacos-e-caminho-curto:
    `tipo=lacos` (ciclos por componente biconexo, `pgr_biconnectedComponents`), `tipo=isolados`
    (elementos sem
    caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`,
    `pgr_connectedComponents`)
    ou `tipo=caminho_curto` (origem em `pontos_partida[0]`, `destino`, custo = `atributo_custo` ou o
    comprimento geodésico por padrão; `k` alternativas por `pgr_ksp` quando `k>1`); ou, item
    itens L4-18-rede-simples-trace-network e L4-02-b-montante-jusante, `tipo=montante`/`tipo=jusante`:
    numa
    rede com controlador de subrede em tier hierárquico o sentido vem da DISTÂNCIA AO CONTROLADOR
    (jusante de
    um ponto = o que só chega ao controlador passando por ele); sem controlador, vem da DIREÇÃO DE FLUXO
    declarada no atributo `direcao_fluxo` de cada trecho (digitalizada/contra/indeterminada), que para,
    com
    aviso por trecho, em toda aresta indeterminada. `origem_direcao` no pedido impõe um dos dois, e a
    resposta sempre diz qual valeu; em malha (tier particionado) sem atributo, e em laço, a resposta é
    `direcao='indeterminado'` com o motivo e os nós do laço, nunca um sentido arbitrado. Ponto de
    partida, destino
    e barreira são a mesma forma: feição+terminal ou coordenada com tolerância. Não exige `rede.editar`:
    é
    leitura sobre o índice já construído (mesmo privilégio de `topologia/alcance`), nunca grava nada na
    rede.
    Sem `response_model` fixo porque cada `tipo` devolve um formato diferente (ver `docs/openapi.json`
    para o
    formato de cada um, e os testes de cada item para exemplo).

    Args:
        rede_id (str):
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        rede_id=rede_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    rede_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: TracadoEntrada,
) -> Any | HTTPValidationError | None:
    """Tracar Rede

     Traça `tipo=conectado` (tudo que se alcança do(s) ponto(s) de partida, respeitando a
    traversabilidade
    de cada dispositivo e as barreiras) ou `tipo=subrede` (o mesmo, mas parando em qualquer controlador
    de
    outra subrede — hoje, categoria `transformacao` do pacote); ou, item L4-02-d-lacos-e-caminho-curto:
    `tipo=lacos` (ciclos por componente biconexo, `pgr_biconnectedComponents`), `tipo=isolados`
    (elementos sem
    caminho a nenhuma feição da categoria `categoria_controlador`, padrão `fonte`,
    `pgr_connectedComponents`)
    ou `tipo=caminho_curto` (origem em `pontos_partida[0]`, `destino`, custo = `atributo_custo` ou o
    comprimento geodésico por padrão; `k` alternativas por `pgr_ksp` quando `k>1`); ou, item
    itens L4-18-rede-simples-trace-network e L4-02-b-montante-jusante, `tipo=montante`/`tipo=jusante`:
    numa
    rede com controlador de subrede em tier hierárquico o sentido vem da DISTÂNCIA AO CONTROLADOR
    (jusante de
    um ponto = o que só chega ao controlador passando por ele); sem controlador, vem da DIREÇÃO DE FLUXO
    declarada no atributo `direcao_fluxo` de cada trecho (digitalizada/contra/indeterminada), que para,
    com
    aviso por trecho, em toda aresta indeterminada. `origem_direcao` no pedido impõe um dos dois, e a
    resposta sempre diz qual valeu; em malha (tier particionado) sem atributo, e em laço, a resposta é
    `direcao='indeterminado'` com o motivo e os nós do laço, nunca um sentido arbitrado. Ponto de
    partida, destino
    e barreira são a mesma forma: feição+terminal ou coordenada com tolerância. Não exige `rede.editar`:
    é
    leitura sobre o índice já construído (mesmo privilégio de `topologia/alcance`), nunca grava nada na
    rede.
    Sem `response_model` fixo porque cada `tipo` devolve um formato diferente (ver `docs/openapi.json`
    para o
    formato de cada um, e os testes de cada item para exemplo).

    Args:
        rede_id (str):
        body (TracadoEntrada): `tipo=montante|jusante` (item L4-18) exige `pontos_partida` e anda
            pela direção de fluxo declarada em
            atributo; `tipo=conectado|subrede` (item L4-02-a) exige `pontos_partida`;
            `tipo=caminho_curto` (item L4-02-d)
            exige um único ponto em `pontos_partida` (a origem) e `destino`; `tipo=lacos` e
            `tipo=isolados` não
            exigem `pontos_partida` (operam sobre a rede inteira) — a validação por tipo é feita na
            rota, não aqui,
            porque cada tipo tem uma exigência diferente sobre a MESMA lista.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            rede_id=rede_id,
            client=client,
            body=body,
        )
    ).parsed
