"""Robustez do motor multicritério por sorteio de pesos (Monte Carlo) — item L3-02-a.

Decisões de conceito que este módulo obedece (laco/decomposicao/L3L6_CONCEITO.md):

- A9: o sorteio guarda AGREGADOS por unidade (mínimo, média, máximo, desvio, frequência no top-k e no
  decil superior), nunca N × unidades — a semente fica gravada e o resultado é reproduzível bit a bit
  a partir dela. Sorteio por Dirichlet no simplex ou por faixa ± k % declarada por fator.
- A6: veto e restrição são objetos separados do peso e NUNCA entram no sorteio: a fração vetada de cada
  unidade é fixa em todos os sorteios e a unidade vetada é excluída da classificação por construção
  (nunca por sorte), não só porque a nota costuma ficar baixa.
- A2/A9: a combinação em si é a função pura de `app.amc.combinacao.combinar` (item L3-01-e), chamada
  N vezes sem reextração de fator — este módulo NÃO reimplementa a combinação, só o sorteio e o resumo.

Regra de linguagem (obrigatória em toda saída deste módulo, inclusive mensagens e documentação): o
sorteio mede SENSIBILIDADE ao peso escolhido pelo usuário, nunca um "peso ótimo" — não existe aqui
nenhuma noção de otimizar peso, só de descrever o quanto o resultado se mexe quando o peso varia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from app.amc.combinacao import COMBINADORES, ErroCombinacao, combinar

AVISO_ROBUSTEZ = (
    "o sorteio mede sensibilidade ao peso escolhido pelo usuário; não existe peso ótimo aqui, só o "
    "tanto que o resultado varia quando o peso varia"
)

TECNICAS_SORTEIO: dict[str, str] = {
    "dirichlet": "sorteio no simplex (Dirichlet); concentracao=None cobre o simplex inteiro, "
                 "concentracao>0 concentra o sorteio ao redor do peso base escolhido pelo usuário",
    "faixa": "cada peso sorteado independentemente em [base·(1−k), base·(1+k)], k declarado por fração",
}


class ErroRobustez(ValueError):
    """Erro de contrato do sorteio. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class ResultadoRobustez:
    """Resumo agregado por unidade de N sorteios de peso. Nunca guarda o sorteio inteiro (N × unidades)."""

    semente: int
    metodo: str
    n_sorteios: int
    n_unidades: int
    ids_fatores: list[str]
    pesos_base_normalizados: list[float]
    k: int
    minimo: np.ndarray
    media: np.ndarray
    maximo: np.ndarray
    desvio: np.ndarray
    frequencia_topk: np.ndarray
    frequencia_decil_superior: np.ndarray
    estavel: np.ndarray  # frequência no top-k >= 0,95
    vetado: np.ndarray
    tempo_s: float
    combinador: str
    aviso_pesos: str = AVISO_ROBUSTEZ
    observacoes: list[str] = field(default_factory=list)

    def como_dicionario(self) -> dict:
        def _lista(a: np.ndarray) -> list:
            return [None if isinstance(v, float) and not np.isfinite(v) else (bool(v) if a.dtype == bool else float(v))
                    for v in a]

        return {
            "aviso_pesos": self.aviso_pesos,
            "semente": self.semente,
            "metodo": self.metodo,
            "descricao_metodo": TECNICAS_SORTEIO[self.metodo],
            "n_sorteios": self.n_sorteios,
            "n_unidades": self.n_unidades,
            "ids_fatores": list(self.ids_fatores),
            "pesos_base_normalizados": list(self.pesos_base_normalizados),
            "k_top": self.k,
            "combinador": self.combinador,
            "tempo_s": self.tempo_s,
            "observacoes": list(self.observacoes),
            "minimo": _lista(self.minimo),
            "media": _lista(self.media),
            "maximo": _lista(self.maximo),
            "desvio": _lista(self.desvio),
            "frequencia_topk": _lista(self.frequencia_topk),
            "frequencia_decil_superior": _lista(self.frequencia_decil_superior),
            "estavel": _lista(self.estavel),
            "vetado": _lista(self.vetado),
        }


def _ordem_canonica(ids_fatores: list[str]) -> np.ndarray:
    """Ordem estável derivada só dos IDs (nunca da posição de entrada) — é o que torna o sorteio
    invariante à ordem em que o chamador lista os fatores (refutação do item: permutar a ordem dos
    fatores e reexecutar com a mesma semente tem de dar o resultado idêntico)."""
    return np.argsort(np.asarray(ids_fatores, dtype=object), kind="stable")


def sortear_pesos(
    pesos_base,
    ids_fatores: list[str],
    n: int,
    *,
    metodo: str = "dirichlet",
    concentracao: float | None = None,
    k_percentual: float = 0.3,
    semente: int,
) -> np.ndarray:
    """Sorteia `n` vetores de peso, um por fator de `ids_fatores`, na MESMA ordem de `pesos_base`.

    O sorteio em si acontece numa ordem CANÔNICA (pelos IDs, não pela posição de entrada) e só depois é
    remapeado para a ordem pedida — por isso permutar `pesos_base`/`ids_fatores` junto com a matriz de
    fatores dá exatamente o mesmo resultado por unidade com a mesma semente (invariância de ordem).
    """
    w = np.asarray(pesos_base, dtype=np.float64)
    n_fatores = w.size
    if len(ids_fatores) != n_fatores:
        raise ErroRobustez("ids_incompativeis", f"são {n_fatores} pesos e {len(ids_fatores)} identificadores")
    if metodo not in TECNICAS_SORTEIO:
        raise ErroRobustez("metodo_desconhecido", f"método de sorteio desconhecido: {metodo}",
                            {"aceitos": sorted(TECNICAS_SORTEIO)})
    if n < 1:
        raise ErroRobustez("n_invalido", "o número de sorteios tem de ser pelo menos 1")
    if not np.all(np.isfinite(w)) or np.any(w < 0) or w.sum() <= 0:
        raise ErroRobustez("peso_base_invalido", "peso base precisa ser finito, ≥ 0 e somar mais que zero")

    ordem = _ordem_canonica(ids_fatores)
    inversa = np.argsort(ordem, kind="stable")  # de volta à ordem de entrada
    w_can = w[ordem]

    rng = np.random.default_rng(semente)
    if metodo == "dirichlet":
        if concentracao is None:
            alpha = np.ones(n_fatores)
        else:
            if concentracao <= 0:
                raise ErroRobustez("concentracao_invalida", "concentracao tem de ser positiva quando declarada")
            alpha = (w_can / w_can.sum()) * concentracao * n_fatores
            alpha = np.maximum(alpha, 1e-6)
        draws_can = rng.dirichlet(alpha, size=n)
    else:  # faixa
        if not (0 < k_percentual < 10):
            raise ErroRobustez("k_percentual_invalido", "k_percentual tem de estar entre 0 e 10 (fração, não %)")
        lo = w_can * (1.0 - k_percentual)
        hi = w_can * (1.0 + k_percentual)
        lo = np.maximum(lo, 0.0)
        draws_can = rng.uniform(lo, hi, size=(n, n_fatores))
        draws_can = np.maximum(draws_can, 1e-9)  # peso zero puro derrubaria o fator sem declarar veto

    return draws_can[:, inversa]


def simular_robustez(
    fatores,
    pesos_base,
    *,
    n: int = 1000,
    metodo: str = "dirichlet",
    concentracao: float | None = None,
    k_percentual: float = 0.3,
    k_top: int | None = None,
    decil_superior: float = 0.9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada=None,
    motivo_veto=None,
    ids_fatores: list[str] | None = None,
    semente: int,
    progresso=None,
) -> ResultadoRobustez:
    """Roda `n` recombinações baratas do MESMO fator já extraído, cada uma com um vetor de peso sorteado,
    e resume por unidade. `progresso(pct)` é chamado a cada ~10 % quando fornecido (uso do job).

    Vetos e restrições (`fracao_vetada`) são fixos em todos os sorteios — nunca sorteados — e a unidade
    vetada (fração ≥ 1) é excluída da classificação por construção, nunca apenas por a nota ficar baixa.
    """
    inicio = time.monotonic()
    m = np.asarray(fatores, dtype=np.float64) if not isinstance(fatores, np.ndarray) else fatores
    if m.ndim != 2:
        raise ErroRobustez("matriz_invalida", "a matriz de fatores precisa ter duas dimensões (unidade × fator)")
    n_unidades, n_fatores = m.shape
    ids_fatores = ids_fatores if ids_fatores is not None else [f"fator_{i}" for i in range(n_fatores)]
    if combinador not in COMBINADORES:
        raise ErroRobustez("combinador_desconhecido", f"combinador desconhecido: {combinador}")
    k = k_top if k_top is not None else max(1, round(n_unidades * 0.1))
    if not (1 <= k <= n_unidades):
        raise ErroRobustez("k_top_invalido", "k_top tem de estar entre 1 e o número de unidades")
    if not (0.0 < decil_superior < 1.0):
        raise ErroRobustez("decil_invalido", "decil_superior tem de estar entre 0 e 1")

    pesos = sortear_pesos(pesos_base, ids_fatores, n, metodo=metodo, concentracao=concentracao,
                           k_percentual=k_percentual, semente=semente)

    vetado_fixo = np.zeros(n_unidades, dtype=bool)
    if fracao_vetada is not None:
        f = np.asarray(fracao_vetada, dtype=np.float64)
        vetado_fixo = f >= 1.0

    soma = np.zeros(n_unidades)
    soma2 = np.zeros(n_unidades)
    minimo = np.full(n_unidades, np.inf)
    maximo = np.full(n_unidades, -np.inf)
    conta_valido = np.zeros(n_unidades, dtype=np.int64)
    conta_topk = np.zeros(n_unidades, dtype=np.int64)
    conta_decil = np.zeros(n_unidades, dtype=np.int64)
    n_decil = max(1, round(n_unidades * (1.0 - decil_superior)))

    marco = max(1, n // 10)
    for j in range(n):
        try:
            r = combinar(m, pesos[j], combinador=combinador, politica_ausente=politica_ausente,
                         fracao_vetada=fracao_vetada, motivo_veto=motivo_veto, ids_fatores=ids_fatores)
        except ErroCombinacao as e:
            raise ErroRobustez("erro_na_combinacao", f"sorteio {j}: {e.mensagem}", e.detalhe) from e
        fav = r.fav
        presente = np.isfinite(fav)
        soma[presente] += fav[presente]
        soma2[presente] += fav[presente] ** 2
        conta_valido += presente
        minimo = np.where(presente & (fav < minimo), fav, minimo)
        maximo = np.where(presente & (fav > maximo), fav, maximo)

        # classificação exclui a unidade vetada POR CONSTRUÇÃO — nunca depende do valor da nota.
        ranking = np.where(vetado_fixo | ~presente, -np.inf, fav)
        ordem_desc = np.argsort(-ranking, kind="stable")
        topk_idx = ordem_desc[:k]
        conta_topk[topk_idx] += ranking[topk_idx] > -np.inf
        decil_idx = ordem_desc[:n_decil]
        conta_decil[decil_idx] += ranking[decil_idx] > -np.inf

        if progresso is not None and ((j + 1) % marco == 0 or j + 1 == n):
            progresso(int((j + 1) * 100 / n))

    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(conta_valido > 0, soma / np.maximum(conta_valido, 1), np.nan)
        variancia = np.where(conta_valido > 1, soma2 / np.maximum(conta_valido, 1) - media**2, 0.0)
        variancia = np.maximum(variancia, 0.0)  # erro de ponto flutuante pode dar negativo bem perto de 0
        desvio = np.sqrt(variancia)
    minimo = np.where(np.isfinite(minimo), minimo, np.nan)
    maximo = np.where(np.isfinite(maximo), maximo, np.nan)
    frequencia_topk = conta_topk / n
    frequencia_decil = conta_decil / n
    estavel = (frequencia_topk >= 0.95) & ~vetado_fixo

    observacoes = [
        f"{int(vetado_fixo.sum())} de {n_unidades} unidades vetadas: excluídas do top-{k} em todos os {n} sorteios "
        "por construção, não sorteadas",
        f"{int(estavel.sum())} de {n_unidades} unidades estáveis (frequência no top-{k} ≥ 95 % dos sorteios)",
    ]

    return ResultadoRobustez(
        semente=semente,
        metodo=metodo,
        n_sorteios=n,
        n_unidades=n_unidades,
        ids_fatores=list(ids_fatores),
        pesos_base_normalizados=[float(x) for x in (np.asarray(pesos_base, dtype=np.float64) /
                                                      np.asarray(pesos_base, dtype=np.float64).sum())],
        k=k,
        minimo=minimo,
        media=media,
        maximo=maximo,
        desvio=desvio,
        frequencia_topk=frequencia_topk,
        frequencia_decil_superior=frequencia_decil,
        estavel=estavel,
        vetado=vetado_fixo,
        tempo_s=time.monotonic() - inicio,
        combinador=combinador,
        observacoes=observacoes,
    )
