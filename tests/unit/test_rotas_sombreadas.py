"""Nenhuma rota é engolida por outra declarada antes dela.

O roteador do Starlette percorre as rotas na ORDEM DE DECLARAÇÃO e para na primeira que casa. Uma rota de
caminho literal declarada DEPOIS de uma rota com parâmetro do mesmo prefixo nunca é alcançada: foi assim que
`GET /api/importacoes/formatos`, declarada depois de `GET /api/importacoes/{id}`, respondeu 404
"importação inexistente" durante todo o turno 3 (achado do adversário do grupo G3).

Este teste vale para TODA rota do repositório, presente e futura: quem acrescentar uma rota literal depois da
rota com parâmetro do mesmo prefixo é reprovado aqui, com o nome das duas funções na mensagem. Não precisa de
banco: só importa a aplicação."""

from __future__ import annotations

import re

from fastapi.routing import APIRoute

from app.main import app

def _achatar(rotas) -> list[APIRoute]:
    """Ordem REAL de resolução. Esta versão do FastAPI embrulha cada `include_router` num `_IncludedRouter`
    com as rotas dentro; o roteador desce nele na ordem em que foi incluído, então a lista achatada em
    pré-ordem é exatamente a ordem em que o Starlette tenta casar."""
    saida: list[APIRoute] = []
    for r in rotas:
        if isinstance(r, APIRoute):
            saida.append(r)
        elif getattr(r, "original_router", None) is not None:   # _IncludedRouter desta versão do FastAPI
            saida.extend(_achatar(r.original_router.routes))
        elif hasattr(r, "routes"):
            saida.extend(_achatar(r.routes))
    return saida


ROTAS = _achatar(app.router.routes)


def _casa(rota: APIRoute, caminho: str, metodos: set[str]) -> bool:
    return bool(rota.path_regex.match(caminho)) and bool((rota.methods or set()) & metodos)


def _concreto(caminho: str) -> str:
    """Troca cada `{param}` por um valor sintético que nenhum caminho literal do repositório usa."""
    return re.sub(r"\{[^}]+\}", "zzparamzz", caminho)


def test_rota_literal_nunca_e_engolida_por_rota_com_parametro():
    culpadas = []
    for i, rota in enumerate(ROTAS):
        if "{" in rota.path:
            continue
        for anterior in ROTAS[:i]:
            if anterior.path is not rota.path and _casa(anterior, rota.path, rota.methods or set()):
                culpadas.append(
                    f"{sorted(rota.methods or [])} {rota.path} ({rota.endpoint.__name__}) é engolida por "
                    f"{anterior.path} ({anterior.endpoint.__name__}), declarada antes"
                )
                break
    assert not culpadas, "rotas inalcançáveis (declare a rota literal ANTES da rota com parâmetro):\n" + \
                         "\n".join(culpadas)


def test_rota_com_parametro_resolve_para_ela_mesma():
    """A recíproca: uma rota com parâmetro também pode ser engolida por outra com parâmetro declarada antes
    (mesmo número de segmentos, conversor diferente). Com um valor sintético no lugar de cada parâmetro, a
    primeira rota que casa tem de ser ela própria."""
    culpadas = []
    for rota in ROTAS:
        if "{" not in rota.path:
            continue
        alvo = _concreto(rota.path)
        metodos = rota.methods or set()
        primeira = next((r for r in ROTAS if _casa(r, alvo, metodos)), None)
        if primeira is not None and primeira.path != rota.path:
            culpadas.append(
                f"{sorted(metodos)} {rota.path} ({rota.endpoint.__name__}) nunca é alcançada: "
                f"{primeira.path} ({primeira.endpoint.__name__}) casa antes"
            )
    assert not culpadas, "rotas inalcançáveis:\n" + "\n".join(culpadas)


def test_a_rota_de_formatos_da_ingestao_esta_antes_da_rota_com_parametro():
    """Cláusula literal do achado do adversário, presa por nome: se alguém reordenar o arquivo de rotas da
    ingestão outra vez, este teste diz exatamente o que quebrou."""
    caminhos = [r.path for r in ROTAS if r.path.startswith("/api/importacoes")]
    assert "/api/importacoes/formatos" in caminhos, caminhos
    assert caminhos.index("/api/importacoes/formatos") < caminhos.index("/api/importacoes/{id}"), caminhos
