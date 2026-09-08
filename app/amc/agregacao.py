"""Agregação de notas por CÉLULA para notas por FEIÇÃO, ponderada pela área de interseção.

Motivo de existir (item L3-01-j): o motor multicritério trabalha sobre uma unidade de análise de cada
vez, mas o resultado que o usuário lê é quase sempre por feição (um imóvel, um lote, um trecho) —
enquanto os fatores foram medidos numa grade regular. A regra da casa para essa passagem, escrita no
motor logístico de referência e reescrita aqui de forma genérica, tem três partes:

1. cada fator da feição é a média das células ponderada pela ÁREA DE INTERSEÇÃO, calculada só sobre as
   células NÃO VETADAS e só sobre as células em que aquele fator tem dado (o denominador é a soma das
   áreas com dado, nunca a área total — fator ausente não vira zero);
2. a FRAÇÃO VETADA da feição é a área em células vetadas dividida pela área intersectada total; ela sai
   daqui como número, para o combinador multiplicar a nota por (1 − fração) — veto é objeto separado do
   peso (decisão A6), não um fator com nota baixa;
3. o MOTIVO do veto que a feição carrega é o motivo da maior área vetada, não o primeiro encontrado.

O módulo é PURO: numpy, sem banco, sem arquivo, sem relógio. Quem lê a geometria e monta os pares
(feição, célula, área) é o chamador.

Sobre `arredondar`: o motor de referência grava a nota agregada como inteiro (smallint). Arredondar é
uma decisão de ARMAZENAMENTO, não da conta, por isso é opcional aqui e o padrão é NÃO arredondar. Quando
ligado, o critério é "meio para longe do zero" (0,5 → 1), o mesmo do `round` do Postgres, e não o
"meio para o par" do numpy — as duas convenções discordam exatamente nos empates e essa discordância
aparece como diferença de 1 ponto na comparação com qualquer base já materializada.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class ErroAgregacao(ValueError):
    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass
class Agregado:
    """Uma linha por feição, na ordem de `feicoes`."""

    feicoes: list
    fatores: np.ndarray          # feição × fator, escala 0-100, nan onde nenhuma célula tinha dado
    fracao_vetada: np.ndarray    # 0 a 1
    motivo_veto: list            # motivo da maior área vetada, ou None
    n_celulas: np.ndarray        # células NÃO vetadas que entraram na média
    area_total: np.ndarray       # área intersectada total (vetada + não vetada), na unidade de entrada


def arredondar_meio_para_longe_do_zero(x: np.ndarray) -> np.ndarray:
    """0,5 → 1 e −0,5 → −1, como o `round` do Postgres; `np.round` daria 0 nos dois (meio para o par)."""
    return np.where(np.isnan(x), x, np.sign(x) * np.floor(np.abs(x) + 0.5))


def agregar_por_feicao(
    indice_feicao,
    areas,
    fatores_celula,
    *,
    vetado=None,
    motivo_celula=None,
    n_feicoes: int | None = None,
    arredondar: bool = False,
) -> Agregado:
    """Agrega `fatores_celula` (linha por PAR feição-célula) em uma linha por feição.

    `indice_feicao[k]` é o número da feição do par k (0 a n_feicoes−1); `areas[k]` é a área de
    interseção daquele par, em qualquer unidade coerente (só a razão importa). `fatores_celula` tem uma
    linha por par e uma coluna por fator, com `nan` onde falta dado. `vetado[k]` diz se a célula do par
    está vetada e `motivo_celula[k]` traz o texto do motivo.
    """
    idx = np.asarray(indice_feicao, dtype=np.int64)
    a = np.asarray(areas, dtype=np.float64)
    m = np.asarray(fatores_celula, dtype=np.float64)
    if m.ndim != 2:
        raise ErroAgregacao("matriz_invalida", "fatores_celula tem de ser uma matriz par × fator")
    n_pares, n_fatores = m.shape
    if idx.shape != (n_pares,) or a.shape != (n_pares,):
        raise ErroAgregacao("tamanhos_incompativeis",
                            "indice_feicao, areas e fatores_celula têm de ter o mesmo número de pares")
    if n_pares and idx.min() < 0:
        raise ErroAgregacao("indice_negativo", "o índice da feição não pode ser negativo")
    if not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ErroAgregacao("area_invalida", "área de interseção tem de ser finita e não negativa")
    n = int(n_feicoes if n_feicoes is not None else (idx.max() + 1 if n_pares else 0))
    if n_pares and idx.max() >= n:
        raise ErroAgregacao("indice_fora_da_faixa", "índice de feição maior que o número de feições")

    v = np.zeros(n_pares, dtype=bool) if vetado is None else np.asarray(vetado, dtype=bool)
    if v.shape != (n_pares,):
        raise ErroAgregacao("veto_incompativel", "um sinal de veto por par feição-célula")

    area_total = np.bincount(idx, weights=a, minlength=n)
    area_vetada = np.bincount(idx, weights=np.where(v, a, 0.0), minlength=n)
    with np.errstate(divide="ignore", invalid="ignore"):
        fracao_vetada = np.where(area_total > 0, area_vetada / area_total, 0.0)
    fracao_vetada = np.clip(fracao_vetada, 0.0, 1.0)

    # a média por fator roda SÓ sobre célula não vetada e SÓ onde o fator tem dado
    peso = np.where(v, 0.0, a)
    tem = ~np.isnan(m)
    saida = np.full((n, n_fatores), np.nan, dtype=np.float64)
    for j in range(n_fatores):
        p = peso * tem[:, j]
        num = np.bincount(idx, weights=p * np.nan_to_num(m[:, j]), minlength=n)
        den = np.bincount(idx, weights=p, minlength=n)
        with np.errstate(divide="ignore", invalid="ignore"):
            saida[:, j] = np.where(den > 0, num / den, np.nan)
    if arredondar:
        saida = arredondar_meio_para_longe_do_zero(saida)

    n_celulas = np.bincount(idx, weights=(~v).astype(np.float64), minlength=n).astype(np.int64)

    motivo: list = [None] * n
    if motivo_celula is not None:
        if len(motivo_celula) != n_pares:
            raise ErroAgregacao("motivo_incompativel", "um motivo por par feição-célula")
        maior = np.zeros(n, dtype=np.float64)
        for k in np.nonzero(v)[0]:
            i = int(idx[k])
            texto = motivo_celula[k]
            if texto is None:
                continue
            if a[k] > maior[i]:
                maior[i] = a[k]
                motivo[i] = texto

    return Agregado(
        feicoes=list(range(n)),
        fatores=saida,
        fracao_vetada=fracao_vetada,
        motivo_veto=motivo,
        n_celulas=n_celulas,
        area_total=area_total,
    )
