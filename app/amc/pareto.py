"""Análise sem agregação do motor multicritério: fronteira de Pareto por ordens (item L3-08-pareto).

O combinador (`app/amc/combinacao.py`) responde "qual é a melhor" DEPOIS de o usuário escolher pesos.
Este módulo responde a pergunta anterior, sem peso nenhum: quais unidades não são piores que nenhuma
outra em todos os objetivos ao mesmo tempo. Uma unidade A domina B quando A é pelo menos igual a B em
todos os objetivos e estritamente melhor em pelo menos um. A fronteira de 1ª ordem é o conjunto das
unidades não dominadas; a de 2ª ordem é a fronteira do que sobra depois de retirar a 1ª, e assim por
diante. Qualquer unidade da 1ª ordem pode ser "a melhor": qual delas depende do peso que o usuário der.

Decisões que este módulo executa:

- 2 a 4 objetivos (hipótese do item). Objetivo é um valor por unidade, na direção declarada
  ("maximizar" ou "minimizar"); a escala não precisa ser 0-100, porque a dominância só compara
  valores do MESMO objetivo entre unidades;
- ausência de dado é NULL (``nan``) e nunca zero: unidade com qualquer objetivo ausente fica FORA da
  ordenação (ordem 0, motivo declarado). Tratar ausência como zero colocaria a unidade sem dado na
  fronteira, que é o erro clássico desta análise;
- empate não é dominância: duas unidades com valores idênticos ficam ambas na mesma ordem. É por isso
  que, com dois objetivos iguais, a fronteira é a unidade de valor máximo E todos os seus empates.

O módulo é PURO: não abre banco, não lê arquivo, não usa relógio. Trabalha vetorizado em numpy.

Custo: a peneira de cada ordem ordena as unidades em ordem lexicográfica decrescente e compara cada
candidata só com as que já entraram naquela fronteira (Kung). Isso é exato — se F domina C, F vem
antes de C nessa ordem, e se a dominadora de C tiver sido descartada, quem a descartou também domina C
(a dominância é transitiva). O laço ingênuo O(n²) que confere isto vive no teste, escrito do zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

AVISO_SEM_PESO = (
    "fronteira de Pareto: nenhuma unidade da 1ª ordem é melhor que outra sem uma escolha de peso; "
    "os pesos são escolhidos pelo usuário, não medidos"
)

DIRECOES: dict[str, str] = {
    "maximizar": "valor maior é melhor",
    "minimizar": "valor menor é melhor",
}

MOTIVO_AUSENTE = "objetivo sem dado nesta unidade"
MOTIVO_ALEM = "dominada por unidades de ordem melhor; além do limite de ordens pedido"

MIN_OBJETIVOS, MAX_OBJETIVOS = 2, 4
MAX_ORDENS = 10


class ErroPareto(ValueError):
    """Erro de contrato da ordenação. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class Ordenacao:
    """Saída da ordenação não dominada.

    `ordem` traz 1 para a fronteira, 2 para a de 2ª ordem, e assim por diante; 0 significa NÃO
    classificada, e `motivo` diz por quê (sem dado, ou além do limite de ordens pedido).
    """

    ordem: np.ndarray
    motivo: list[str | None]
    direcoes: list[str]
    ordens_pedidas: int
    classificadas: int
    sem_dado: int
    aviso: str = AVISO_SEM_PESO
    observacoes: list[str] = field(default_factory=list)

    def indices_da_ordem(self, k: int) -> list[int]:
        """Posições (linhas da matriz de entrada) das unidades da ordem `k`."""
        return [int(i) for i in np.flatnonzero(self.ordem == k)]

    def contagem_por_ordem(self) -> list[dict]:
        return [
            {"ordem": k, "unidades": int(np.count_nonzero(self.ordem == k))}
            for k in range(1, self.ordens_pedidas + 1)
        ]

    def como_dicionario(self) -> dict:
        """Forma serializável (API, export, painel). Guarda o aviso dos pesos junto dos números."""
        return {
            "aviso": self.aviso,
            "direcoes": list(self.direcoes),
            "ordens_pedidas": self.ordens_pedidas,
            "classificadas": self.classificadas,
            "sem_dado": self.sem_dado,
            "contagem_por_ordem": self.contagem_por_ordem(),
            "observacoes": list(self.observacoes),
        }


def _matriz(valores) -> np.ndarray:
    m = np.asarray(valores, dtype=float)
    if m.ndim != 2:
        raise ErroPareto("forma_invalida", "os valores têm de ser uma matriz unidades × objetivos")
    if m.shape[0] == 0:
        raise ErroPareto("sem_unidades", "não há unidade nenhuma para ordenar")
    if not (MIN_OBJETIVOS <= m.shape[1] <= MAX_OBJETIVOS):
        raise ErroPareto(
            "objetivos_fora_da_faixa",
            f"a análise aceita de {MIN_OBJETIVOS} a {MAX_OBJETIVOS} objetivos; vieram {m.shape[1]}",
        )
    if np.isinf(m).any():
        raise ErroPareto("valor_nao_finito", "valor infinito não é aceito como objetivo")
    return m


def _direcoes(direcoes: Sequence[str], n_objetivos: int) -> list[str]:
    d = list(direcoes)
    if len(d) != n_objetivos:
        raise ErroPareto(
            "direcoes_incompativeis",
            f"são {n_objetivos} objetivos e {len(d)} direções; uma direção por objetivo",
        )
    for x in d:
        if x not in DIRECOES:
            raise ErroPareto("direcao_desconhecida", f"direção desconhecida: {x!r}; use maximizar ou minimizar")
    return d


def _frente(v: np.ndarray, posicoes: np.ndarray) -> np.ndarray:
    """Índices (dentro de `posicoes`) das linhas não dominadas de `v[posicoes]`, tudo já em maximização."""
    sub = v[posicoes]
    # lexsort ordena pela ÚLTIMA chave primeiro: passando as colunas invertidas, a chave principal é a
    # coluna 0. O [::-1] final põe em ordem decrescente, que é a que garante "quem domina vem antes".
    ordem = np.lexsort(sub.T[::-1])[::-1]
    frente: list[int] = []
    for i in ordem:
        linha = sub[i]
        if frente:
            f = sub[frente]
            if np.any(np.all(f >= linha, axis=1) & np.any(f > linha, axis=1)):
                continue
        frente.append(int(i))
    return posicoes[np.array(sorted(frente), dtype=int)]


def ordenar(valores, direcoes: Sequence[str], ordens: int = 3) -> Ordenacao:
    """Ordenação não dominada por ordens.

    `valores`: matriz unidades × objetivos (2 a 4 colunas), ``nan`` onde falta dado.
    `direcoes`: uma por objetivo, "maximizar" ou "minimizar".
    `ordens`: quantas fronteiras retirar (1 = só a fronteira; o item pede 2ª e 3ª ordem, padrão 3).
    """
    m = _matriz(valores)
    dirs = _direcoes(direcoes, m.shape[1])
    if not isinstance(ordens, int) or isinstance(ordens, bool):
        raise ErroPareto("ordens_invalidas", "o número de ordens tem de ser inteiro")
    if not (1 <= ordens <= MAX_ORDENS):
        raise ErroPareto("ordens_fora_da_faixa", f"o número de ordens tem de estar entre 1 e {MAX_ORDENS}")

    v = m.copy()
    for j, d in enumerate(dirs):
        if d == "minimizar":
            v[:, j] = -v[:, j]

    completa = ~np.isnan(v).any(axis=1)
    ordem = np.zeros(m.shape[0], dtype=int)
    restantes = np.flatnonzero(completa)
    for k in range(1, ordens + 1):
        if restantes.size == 0:
            break
        frente = _frente(v, restantes)
        ordem[frente] = k
        restantes = np.setdiff1d(restantes, frente, assume_unique=True)

    motivo: list[str | None] = [None] * m.shape[0]
    for i in np.flatnonzero(~completa):
        motivo[int(i)] = MOTIVO_AUSENTE
    for i in restantes:
        motivo[int(i)] = MOTIVO_ALEM

    observacoes = []
    if restantes.size:
        observacoes.append(
            f"{int(restantes.size)} unidades ficaram além da {ordens}ª ordem e não foram classificadas"
        )
    sem_dado = int(np.count_nonzero(~completa))
    if sem_dado:
        observacoes.append(f"{sem_dado} unidades têm objetivo sem dado e ficaram fora da ordenação")
    return Ordenacao(
        ordem=ordem,
        motivo=motivo,
        direcoes=dirs,
        ordens_pedidas=ordens,
        classificadas=int(np.count_nonzero(ordem > 0)),
        sem_dado=sem_dado,
        observacoes=observacoes,
    )
