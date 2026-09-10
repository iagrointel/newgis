"""Ordenação não dominada do motor multicritério (item L3-08-pareto).

Portão, cláusula por cláusula:
  a) "ordenação não dominada conferida contra implementação ingênua O(n²) em 2.000 unidades" ->
     test_2000_unidades_batem_com_o_laco_ingenuo_de_pares (2, 3 e 4 objetivos, com e sem ausência de
     dado, maximizando e minimizando). A referência é escrita aqui do zero, a partir da definição de
     dominância, e não importa nada de `app.amc.pareto` além da porta de entrada `ordenar`.
  b) refutação do item: "objetivos idênticos -> a fronteira é a unidade de valor máximo e seus empates"
     -> test_objetivos_identicos_dao_o_maximo_e_seus_empates.

O resto são casos de borda que a análise tem de recusar ou tratar de forma declarada.
"""

import numpy as np
import pytest

from app.amc.pareto import (
    AVISO_SEM_PESO,
    MOTIVO_ALEM,
    MOTIVO_AUSENTE,
    ErroPareto,
    ordenar,
)

UNIDADES = 2000


def domina(a, b, direcoes) -> bool:
    """Definição, sem numpy e sem o produto: A domina B se é pelo menos igual em tudo e melhor em algo."""
    melhor_em_algum = False
    for x, y, d in zip(a, b, direcoes, strict=True):
        pior = x < y if d == "maximizar" else x > y
        if pior:
            return False
        if x != y:
            melhor_em_algum = True
    return melhor_em_algum


def ingenuo(m, direcoes, ordens):
    """Peneira O(n²) por ordem: quem não é dominado por ninguém que ainda está de pé entra na ordem."""
    n = len(m)
    validos = [i for i in range(n) if not any(v != v for v in m[i])]  # NaN != NaN
    ordem = [0] * n
    restantes = list(validos)
    for k in range(1, ordens + 1):
        frente = [
            i for i in restantes
            if not any(j != i and domina(m[j], m[i], direcoes) for j in restantes)
        ]
        for i in frente:
            ordem[i] = k
        restantes = [i for i in restantes if i not in set(frente)]
        if not restantes:
            break
    return ordem


def caso(semente, n_objetivos, fracao_ausente=0.0, semente_extra=0):
    rng = np.random.default_rng(semente + semente_extra)
    m = rng.uniform(0.0, 100.0, size=(UNIDADES, n_objetivos))
    # valores repetidos de propósito: empate não é dominância, e é onde a peneira rápida costuma errar
    m[: UNIDADES // 10] = np.round(m[: UNIDADES // 10] / 25.0) * 25.0
    if fracao_ausente:
        m[rng.uniform(size=m.shape) < fracao_ausente] = np.nan
    return m


@pytest.mark.parametrize(
    ("n_objetivos", "direcoes", "fracao_ausente"),
    [
        (2, ["maximizar", "maximizar"], 0.0),
        (2, ["maximizar", "minimizar"], 0.0),
        (3, ["maximizar", "minimizar", "maximizar"], 0.0),
        (3, ["minimizar", "minimizar", "minimizar"], 0.08),
        (4, ["maximizar", "maximizar", "minimizar", "maximizar"], 0.05),
    ],
)
def test_2000_unidades_batem_com_o_laco_ingenuo_de_pares(n_objetivos, direcoes, fracao_ausente, medida):
    m = caso(20260908, n_objetivos, fracao_ausente)
    r = ordenar(m, direcoes, ordens=3)
    esperado = ingenuo(m.tolist(), direcoes, ordens=3)
    assert r.ordem.tolist() == esperado, "a peneira rápida divergiu do laço ingênuo O(n²)"
    assert r.aviso == AVISO_SEM_PESO
    gravar = medida("L3-08-pareto")
    gravar(
        f"unidades_conferidas_{n_objetivos}_objetivos",
        UNIDADES,
        "unidades",
        "tests/unit/test_amc_pareto.py::test_2000_unidades_batem_com_o_laco_ingenuo_de_pares",
    )


def test_objetivos_identicos_dao_o_maximo_e_seus_empates():
    """Refutação exigida pelo item: com dois objetivos iguais, a fronteira é o máximo e todos os empates."""
    rng = np.random.default_rng(7)
    coluna = rng.integers(0, 6, size=500).astype(float).reshape(-1, 1)
    r = ordenar(np.hstack([coluna, coluna]), ["maximizar", "maximizar"], ordens=1)
    frente = r.indices_da_ordem(1)
    maximo = coluna.max()
    assert frente, "a fronteira não pode ser vazia"
    assert {coluna[i, 0] for i in frente} == {maximo}
    assert set(frente) == set(np.flatnonzero(coluna[:, 0] == maximo).tolist()), "faltou algum empate"


def test_minimizar_e_o_espelho_de_maximizar():
    m = caso(11, 2)
    a = ordenar(m, ["maximizar", "maximizar"], ordens=3)
    b = ordenar(-m, ["minimizar", "minimizar"], ordens=3)
    assert a.ordem.tolist() == b.ordem.tolist()


def test_unidade_com_objetivo_ausente_fica_fora_e_nao_vira_zero():
    m = np.array([[10.0, 10.0], [1.0, 1.0], [np.nan, 100.0]])
    r = ordenar(m, ["maximizar", "maximizar"], ordens=3)
    assert r.ordem.tolist() == [1, 2, 0]
    assert r.motivo[2] == MOTIVO_AUSENTE
    assert r.sem_dado == 1
    assert r.classificadas == 2


def test_alem_do_limite_de_ordens_fica_sem_classificacao_com_motivo():
    m = np.array([[k, k] for k in range(10)], dtype=float)  # cada unidade domina a anterior: 10 ordens
    r = ordenar(m, ["maximizar", "maximizar"], ordens=3)
    assert sorted(r.ordem.tolist()) == [0] * 7 + [1, 2, 3]
    assert r.motivo[0] == MOTIVO_ALEM
    assert any("além da 3ª ordem" in o for o in r.observacoes)


def test_todas_as_unidades_iguais_ficam_na_primeira_ordem():
    m = np.full((50, 3), 7.0)
    r = ordenar(m, ["maximizar"] * 3, ordens=3)
    assert set(r.ordem.tolist()) == {1}


@pytest.mark.parametrize(
    ("valores", "direcoes", "ordens", "codigo"),
    [
        (np.zeros((5, 1)), ["maximizar"], 3, "objetivos_fora_da_faixa"),
        (np.zeros((5, 5)), ["maximizar"] * 5, 3, "objetivos_fora_da_faixa"),
        (np.zeros((0, 2)), ["maximizar"] * 2, 3, "sem_unidades"),
        (np.zeros((5, 2)), ["maximizar"], 3, "direcoes_incompativeis"),
        (np.zeros((5, 2)), ["maximizar", "aumentar"], 3, "direcao_desconhecida"),
        (np.zeros((5, 2)), ["maximizar"] * 2, 0, "ordens_fora_da_faixa"),
        (np.zeros((5, 2)), ["maximizar"] * 2, 99, "ordens_fora_da_faixa"),
        (np.zeros((5, 2)), ["maximizar"] * 2, True, "ordens_invalidas"),
        (np.array([[np.inf, 1.0], [2.0, 3.0]]), ["maximizar"] * 2, 3, "valor_nao_finito"),
        (np.zeros(5), ["maximizar"] * 2, 3, "forma_invalida"),
    ],
)
def test_contrato_recusa_entrada_invalida(valores, direcoes, ordens, codigo):
    with pytest.raises(ErroPareto) as e:
        ordenar(valores, direcoes, ordens)
    assert e.value.codigo == codigo


def test_dicionario_carrega_o_aviso_e_a_contagem_por_ordem():
    m = caso(3, 2)
    d = ordenar(m, ["maximizar", "maximizar"], ordens=3).como_dicionario()
    assert d["aviso"] == AVISO_SEM_PESO
    assert [c["ordem"] for c in d["contagem_por_ordem"]] == [1, 2, 3]
    assert sum(c["unidades"] for c in d["contagem_por_ordem"]) == d["classificadas"]
