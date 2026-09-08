"""Backtest contra decisão real (item L3-09-backtest-decisao-real): o modelo diz onde DEVERIA ser bom; a
realidade diz onde alguém DE FATO escolheu. Este módulo compara as duas coisas e devolve o quanto o modelo
reproduz a escolha — sem nunca dizer que o modelo está "certo": correlação com a escolha passada é evidência
sobre o modelo, não prova sobre o futuro, e as ressalvas saem no próprio relatório.

O que mede, na ordem em que o item pede:
a) **percentil das escolhas** no ranking do modelo (0-100; 100 = a unidade mais favorável da grade) e a mediana;
b) **nulo por permutação**: N sorteios de igual número de unidades entre TODAS as unidades disponíveis, para
   dizer o que um sorteio cego daria na mesma grade — é a régua contra a qual o resultado é lido;
c) **AUC** (escolhida × não escolhida), a probabilidade de uma escolha ter favorabilidade maior que uma
   não-escolha sorteada, empate contando meio (Mann-Whitney com postos médios); e o p-valor por permutação;
d) **preferência revelada por fator**: `evitamento = 1 − (fração das escolhas na metade alta do fator ÷ fração
   do nulo na mesma metade)`. É SINAL e ORDEM, nunca peso: positivo = a escolha evitou o fator, negativo =
   procurou. O módulo nunca converte isso em peso de modelo — quem escolhe peso é o usuário (regra do motor).

Ressalvas que o relatório carrega sempre (o item as exige, e elas não são rodapé):
- **anacronismo**: camada de escolhas mais nova que a decisão que se quer explicar mede o mundo DEPOIS da
  decisão; quando `data_camada > data_decisao`, o resultado sai marcado `anacronica`;
- **distância confunde**: fatores de distância a via, a cidade e a rede se correlacionam entre si e com a
  escolha; a preferência revelada de um deles não separa a causa dos outros.

O módulo é PURO: numpy, sem banco, sem relógio (a data entra por parâmetro)."""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field

import numpy as np

PERMUTACOES_PADRAO = 1000
PERMUTACOES_MAX = 100_000
RESSALVA_DISTANCIA = ("fatores de distância se confundem entre si e com a escolha: a preferência revelada de um "
                      "deles não separa a causa dos outros")
RESSALVA_CORRELACAO = ("o backtest mede concordância com a decisão passada, não acerto futuro: quem escolheu "
                       "pode ter usado informação que não está em nenhum fator")


class ErroBacktest(ValueError):
    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe or {}


@dataclass(frozen=True)
class Pedido:
    n_permutacoes: int = PERMUTACOES_PADRAO
    semente: int = 0
    data_decisao: str | None = None   # ISO; a decisão que se quer explicar
    data_camada: str | None = None    # ISO; quando a camada de escolhas foi levantada


@dataclass
class Fator:
    nome: str
    evitamento: float
    fracao_escolhas: float
    fracao_nulo: float
    sinal: str        # evitou | procurou | indiferente


@dataclass
class Resultado:
    n_unidades: int
    n_escolhas: int
    n_fora: int
    auc: float | None
    auc_indefinida: str | None
    percentil_mediano: float | None
    percentil_medio: float | None
    nulo_auc_media: float | None
    nulo_auc_p05: float | None
    nulo_auc_p95: float | None
    nulo_percentil_mediano: float | None
    p_valor: float | None
    permutacoes: int
    semente: int
    fatores: list[Fator] = field(default_factory=list)
    ressalvas: list[str] = field(default_factory=list)
    anacronica: bool = False

    def como_dicionario(self) -> dict:
        return {
            "n_unidades": self.n_unidades, "n_escolhas": self.n_escolhas, "n_fora": self.n_fora,
            "auc": self.auc, "auc_indefinida": self.auc_indefinida,
            "percentil_mediano": self.percentil_mediano, "percentil_medio": self.percentil_medio,
            "nulo": {"auc_media": self.nulo_auc_media, "auc_p05": self.nulo_auc_p05,
                     "auc_p95": self.nulo_auc_p95, "percentil_mediano": self.nulo_percentil_mediano},
            "p_valor": self.p_valor, "permutacoes": self.permutacoes, "semente": self.semente,
            "anacronica": self.anacronica, "ressalvas": list(self.ressalvas),
            "fatores": [
                {"nome": f.nome, "evitamento": f.evitamento, "fracao_escolhas": f.fracao_escolhas,
                 "fracao_nulo": f.fracao_nulo, "sinal": f.sinal}
                for f in self.fatores
            ],
        }


def _postos_medios(valores: np.ndarray) -> np.ndarray:
    """Postos com média nos empates (o mesmo que `scipy.stats.rankdata`, sem a dependência)."""
    ordem = np.argsort(valores, kind="mergesort")
    postos = np.empty(valores.size, dtype=float)
    ordenados = valores[ordem]
    i = 0
    while i < ordenados.size:
        j = i
        while j + 1 < ordenados.size and ordenados[j + 1] == ordenados[i]:
            j += 1
        postos[ordem[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return postos


def auc(fav: np.ndarray, escolhida: np.ndarray) -> float:
    """Probabilidade de uma escolha ter favorabilidade maior que uma não-escolha sorteada; empate = meio.
    Mann-Whitney com postos médios: `U / (n1·n0)`."""
    n1 = int(np.count_nonzero(escolhida))
    n0 = int(escolhida.size - n1)
    if n1 == 0 or n0 == 0:
        raise ErroBacktest("auc_indefinida", "AUC exige pelo menos uma escolha e uma não-escolha")
    postos = _postos_medios(fav)
    soma = float(postos[escolhida].sum())
    u = soma - n1 * (n1 + 1) / 2.0
    return u / (n1 * n0)


def percentis(fav: np.ndarray, escolhida: np.ndarray) -> np.ndarray:
    """Percentil de cada escolha no ranking do modelo: 100 = a mais favorável da grade."""
    postos = _postos_medios(fav)
    return 100.0 * (postos[escolhida] - 0.5) / fav.size


def _anacronismo(p: Pedido) -> bool:
    if not p.data_decisao or not p.data_camada:
        return False
    try:
        d = datetime.date.fromisoformat(p.data_decisao[:10])
        c = datetime.date.fromisoformat(p.data_camada[:10])
    except ValueError as e:
        raise ErroBacktest("data_invalida", f"data fora do formato ISO (AAAA-MM-DD): {e}") from e
    return c > d


def _fatores(fav_fatores: dict[str, np.ndarray] | None, escolhida: np.ndarray,
             sorteios: np.ndarray) -> list[Fator]:
    """Preferência revelada: fração das escolhas na METADE ALTA do fator, contra a fração do nulo na mesma
    metade. Metade alta = acima da mediana da grade (a mediana é da grade inteira, não das escolhas)."""
    saida: list[Fator] = []
    for nome, valores in (fav_fatores or {}).items():
        v = np.asarray(valores, dtype=float)
        if v.shape != escolhida.shape:
            raise ErroBacktest("fator_de_tamanho_errado",
                               f"o fator {nome!r} tem {v.size} valores e a grade tem {escolhida.size}")
        finito = np.isfinite(v)
        if not np.any(finito):
            continue
        mediana = float(np.median(v[finito]))
        alta = np.where(finito, v > mediana, False)
        fr_escolhas = float(np.count_nonzero(alta & escolhida) / max(int(np.count_nonzero(escolhida)), 1))
        if len(sorteios):
            fr_nulo = float(np.mean([np.count_nonzero(alta[s]) / max(s.size, 1) for s in sorteios]))
        else:
            fr_nulo = float(np.count_nonzero(alta) / alta.size)
        evit = 1.0 - (fr_escolhas / fr_nulo) if fr_nulo > 0 else float("nan")
        sinal = "indiferente"
        if math.isfinite(evit):
            if evit > 0.05:
                sinal = "evitou"
            elif evit < -0.05:
                sinal = "procurou"
        saida.append(Fator(nome=nome, evitamento=round(evit, 6) if math.isfinite(evit) else None,
                           fracao_escolhas=round(fr_escolhas, 6), fracao_nulo=round(fr_nulo, 6), sinal=sinal))
    return saida


def avaliar(fav: np.ndarray, escolhida: np.ndarray, *, fatores: dict[str, np.ndarray] | None = None,
            n_fora: int = 0, pedido: Pedido | None = None) -> Resultado:
    """`fav` = favorabilidade por unidade (nan onde não há nota); `escolhida` = máscara booleana do mesmo
    tamanho. Unidades sem nota saem das duas contas e são relatadas."""
    p = pedido or Pedido()
    fav = np.asarray(fav, dtype=float).ravel()
    escolhida = np.asarray(escolhida, dtype=bool).ravel()
    if fav.shape != escolhida.shape:
        raise ErroBacktest("tamanhos_diferentes",
                           f"favorabilidade tem {fav.size} unidades e a máscara de escolha tem {escolhida.size}")
    if not (1 <= p.n_permutacoes <= PERMUTACOES_MAX):
        raise ErroBacktest("permutacoes_fora_do_limite",
                           f"o número de permutações vai de 1 a {PERMUTACOES_MAX}", {"pedido": p.n_permutacoes})
    com_nota = np.isfinite(fav)
    if not np.any(com_nota):
        raise ErroBacktest("sem_unidade_com_nota", "nenhuma unidade da grade tem favorabilidade")
    fav_v = fav[com_nota]
    esc_v = escolhida[com_nota]
    n_unidades = int(fav_v.size)
    n_escolhas = int(np.count_nonzero(esc_v))
    ressalvas = [RESSALVA_CORRELACAO, RESSALVA_DISTANCIA]
    anacronica = _anacronismo(p)
    if anacronica:
        ressalvas.insert(0, f"camada de escolhas ({p.data_camada}) é mais nova que a decisão ({p.data_decisao}): "
                            "o que ela mostra pode ser efeito da decisão, não causa — resultado ANACRÔNICO")
    if int(np.count_nonzero(escolhida & ~com_nota)):
        ressalvas.append(f"{int(np.count_nonzero(escolhida & ~com_nota))} escolha(s) em unidade sem nota do "
                         "modelo: fora da conta")

    base = Resultado(
        n_unidades=n_unidades, n_escolhas=n_escolhas, n_fora=int(n_fora), auc=None, auc_indefinida=None,
        percentil_mediano=None, percentil_medio=None, nulo_auc_media=None, nulo_auc_p05=None, nulo_auc_p95=None,
        nulo_percentil_mediano=None, p_valor=None, permutacoes=0, semente=p.semente, ressalvas=ressalvas,
        anacronica=anacronica,
    )
    if n_escolhas == 0:
        base.auc_indefinida = "nenhuma unidade escolhida caiu na grade: não há o que comparar"
        return base
    if n_escolhas == n_unidades:
        # refutação do item: escolhas = todas as unidades
        base.auc_indefinida = ("todas as unidades da grade estão marcadas como escolhidas: sem não-escolhas, a "
                               "AUC não existe (não é 0,5 nem 1,0)")
        base.percentil_mediano = float(np.median(percentis(fav_v, esc_v)))
        base.percentil_medio = float(np.mean(percentis(fav_v, esc_v)))
        return base

    pc = percentis(fav_v, esc_v)
    valor_auc = auc(fav_v, esc_v)
    rng = np.random.default_rng(p.semente)
    indices = np.arange(n_unidades)
    sorteios = [rng.choice(indices, size=n_escolhas, replace=False) for _ in range(p.n_permutacoes)]
    nulos_auc = np.empty(p.n_permutacoes, dtype=float)
    nulos_pc = np.empty(p.n_permutacoes, dtype=float)
    postos = _postos_medios(fav_v)
    n0 = n_unidades - n_escolhas
    for k, s in enumerate(sorteios):
        soma = float(postos[s].sum())
        nulos_auc[k] = (soma - n_escolhas * (n_escolhas + 1) / 2.0) / (n_escolhas * n0)
        nulos_pc[k] = float(np.median(100.0 * (postos[s] - 0.5) / n_unidades))
    # p-valor de uma cauda com correção de continuidade (Davison & Hinkley): (1 + #{nulo >= observado}) / (N + 1)
    p_valor = float((1 + int(np.count_nonzero(nulos_auc >= valor_auc))) / (p.n_permutacoes + 1))

    base.auc = float(valor_auc)
    base.percentil_mediano = float(np.median(pc))
    base.percentil_medio = float(np.mean(pc))
    base.nulo_auc_media = float(np.mean(nulos_auc))
    base.nulo_auc_p05 = float(np.percentile(nulos_auc, 5))
    base.nulo_auc_p95 = float(np.percentile(nulos_auc, 95))
    base.nulo_percentil_mediano = float(np.median(nulos_pc))
    base.p_valor = p_valor
    base.permutacoes = p.n_permutacoes
    base.fatores = _fatores({k: np.asarray(v, dtype=float).ravel()[com_nota] for k, v in (fatores or {}).items()},
                            esc_v, sorteios)
    return base


__all__ = ["ErroBacktest", "Fator", "PERMUTACOES_MAX", "PERMUTACOES_PADRAO", "Pedido", "Resultado",
           "auc", "avaliar", "percentis"]
