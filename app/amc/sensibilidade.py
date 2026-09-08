"""Sensibilidade do motor multicritério — item L3-02-b.

Duas leituras, com respostas diferentes:

- GLOBAL (índices de Sobol de 1ª ordem e total): varre o espaço inteiro dos pesos e dos parâmetros de
  transformação ao mesmo tempo e devolve, para cada entrada, a fração da variância do resultado que ela
  explica sozinha (1ª ordem) e a fração que ela explica sozinha mais em interação com as outras (total).
  Amostragem de Saltelli sobre a sequência de Sobol de `scipy.stats.qmc` (dependência já instalada);
  estimadores de Saltelli 2010 para a 1ª ordem e de Jansen 1999 para o total; N declarado e semente
  gravada; intervalo por reamostragem com reposição (bootstrap) sobre as linhas da amostra.
- LOCAL (um fator por vez, gráfico tornado): move o peso de UM fator de −50 % a +100 % com os demais
  parados e mede quanto a lista dos k melhores muda. É a leitura que o usuário entende na tela, e é
  cega a interação — por isso as duas convivem.

Regra de linguagem obrigatória em toda saída deste módulo (a mesma do item L3-02-a): a sensibilidade
mede a DEPENDÊNCIA DO MODELO ao peso escolhido pelo usuário, nunca a importância real do fator no
território. Um fator pode ser decisivo na realidade e sair com índice perto de zero porque o dado dele
quase não varia na área de estudo, ou porque o peso que o usuário lhe deu é pequeno.

O módulo é PURO: não abre banco, não lê arquivo, não usa relógio a não ser para cronometrar a si
mesmo. A combinação em si continua sendo `app.amc.combinacao.combinar` (item L3-01-e) — aqui só se
sorteia entrada, chama-se a combinação e resume-se a variância.

Parâmetros de transformação entram pela função `transformacao` que o chamador passa: ela recebe a
matriz bruta e um dicionário de parâmetros sorteados e devolve a matriz já na escala 0-100. Assim os
parâmetros de transformação são sorteados JUNTO com os pesos, na mesma amostra de Saltelli, sem que
este módulo precise conhecer a lista de transformações do item L3-01-d.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import qmc

from app.amc.combinacao import ErroCombinacao, combinar

AVISO_SENSIBILIDADE = (
    "a sensibilidade mede a dependência do modelo ao peso escolhido pelo usuário, não a importância "
    "real do fator no território"
)

TEXTO_EXPLICACAO = (
    "Estes índices dizem quanto o resultado DESTE modelo se mexe quando o peso escolhido pelo usuário "
    "e os parâmetros de transformação se mexem dentro da faixa declarada. Índice alto quer dizer que o "
    "resultado depende muito daquela escolha; índice perto de zero quer dizer que, nesta área de estudo "
    "e nesta faixa, mudar aquela escolha quase não muda a lista. Nenhum dos dois é medida de importância "
    "real do fator no território: um fator decisivo na realidade sai com índice baixo se o dado dele "
    "quase não varia aqui, ou se o peso que lhe deram é pequeno; e um fator irrelevante na realidade sai "
    "com índice alto se o usuário lhe deu peso grande. O que se mede é o modelo, não o mundo."
)

# Índice total abaixo deste valor: a entrada não muda o resultado dentro da faixa declarada.
LIMIAR_IRRELEVANTE = 0.01

ALVOS: dict[str, str] = {
    "concordancia_topk": "fração dos k melhores da configuração base que continuam entre os k melhores",
    "nota_media": "média das notas de favorabilidade das unidades com nota",
}


class ErroSensibilidade(ValueError):
    """Erro de contrato da sensibilidade. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class ResultadoSobol:
    """Índices de Sobol de uma função escalar. `s1`/`st` na ordem de `nomes`; `ic_*` é (baixo, alto)."""

    nomes: list[str]
    n: int
    n_avaliacoes: int
    semente: int
    s1: np.ndarray
    st: np.ndarray
    ic_s1: np.ndarray
    ic_st: np.ndarray
    variancia: float
    nivel_confianca: float
    n_bootstrap: int
    tempo_s: float
    aviso: str = AVISO_SENSIBILIDADE
    observacoes: list[str] = field(default_factory=list)

    @property
    def irrelevantes(self) -> list[str]:
        """Entradas cujo índice TOTAL ficou abaixo do limiar: não mudam o resultado na faixa declarada."""
        return [n for n, t in zip(self.nomes, self.st, strict=True) if np.isfinite(t) and t < LIMIAR_IRRELEVANTE]

    def como_dicionario(self) -> dict:
        def _f(v) -> float | None:
            return None if not np.isfinite(v) else float(v)

        return {
            "aviso": self.aviso,
            "texto_explicacao": TEXTO_EXPLICACAO,
            "n": self.n,
            "n_avaliacoes": self.n_avaliacoes,
            "semente": self.semente,
            "variancia_do_resultado": _f(self.variancia),
            "nivel_confianca": self.nivel_confianca,
            "n_bootstrap": self.n_bootstrap,
            "tempo_s": self.tempo_s,
            "limiar_irrelevante": LIMIAR_IRRELEVANTE,
            "irrelevantes": self.irrelevantes,
            "observacoes": list(self.observacoes),
            "entradas": [
                {
                    "nome": nome,
                    "primeira_ordem": _f(self.s1[i]),
                    "total": _f(self.st[i]),
                    "intervalo_primeira_ordem": [_f(self.ic_s1[i, 0]), _f(self.ic_s1[i, 1])],
                    "intervalo_total": [_f(self.ic_st[i, 0]), _f(self.ic_st[i, 1])],
                    "irrelevante": bool(np.isfinite(self.st[i]) and self.st[i] < LIMIAR_IRRELEVANTE),
                }
                for i, nome in enumerate(self.nomes)
            ],
        }


def _valida_limites(limites) -> tuple[list[str], np.ndarray, np.ndarray]:
    if not limites:
        raise ErroSensibilidade("sem_entradas", "não há nenhuma entrada para analisar")
    nomes, baixo, alto = [], [], []
    for nome, faixa in dict(limites).items():
        lo, hi = float(faixa[0]), float(faixa[1])
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise ErroSensibilidade("faixa_nao_finita", f"a faixa da entrada {nome} tem valor não finito")
        if hi <= lo:
            raise ErroSensibilidade(
                "faixa_degenerada",
                f"a faixa da entrada {nome} precisa ter o limite de cima maior que o de baixo",
                {"entrada": nome, "baixo": lo, "alto": hi},
            )
        nomes.append(str(nome))
        baixo.append(lo)
        alto.append(hi)
    return nomes, np.asarray(baixo), np.asarray(alto)


def _colunas_por_grupo(nomes: list[str], grupos) -> tuple[list[str], list[list[int]]]:
    """Sem `grupos`, cada entrada é um grupo de uma coluna só. Com `grupos`, cada nome de grupo aponta
    para as colunas que se trocam JUNTAS — é assim que se mede a mesma camada entrando mais de uma vez.
    """
    if grupos is None:
        return list(nomes), [[i] for i in range(len(nomes))]
    posicao = {nome: i for i, nome in enumerate(nomes)}
    rotulos, colunas = [], []
    vistos: set[str] = set()
    for rotulo, membros in dict(grupos).items():
        membros = list(membros)
        if not membros:
            raise ErroSensibilidade("grupo_vazio", f"o grupo {rotulo} não tem nenhuma entrada")
        fora = [m for m in membros if m not in posicao]
        if fora:
            raise ErroSensibilidade("grupo_com_entrada_desconhecida",
                                    f"o grupo {rotulo} cita entrada que não existe: " + ", ".join(fora),
                                    {"desconhecidas": fora})
        repetidos = sorted(set(membros) & vistos)
        if repetidos:
            raise ErroSensibilidade("entrada_em_dois_grupos",
                                    "a mesma entrada está em dois grupos: " + ", ".join(repetidos))
        vistos.update(membros)
        rotulos.append(str(rotulo))
        colunas.append([posicao[m] for m in membros])
    faltando = sorted(set(nomes) - vistos)
    if faltando:
        raise ErroSensibilidade("entrada_sem_grupo",
                                "toda entrada tem de estar em algum grupo; ficaram de fora: " + ", ".join(faltando),
                                {"faltando": faltando})
    return rotulos, colunas


def amostra_saltelli(limites, n: int, semente: int, grupos=None):
    """Amostra de Saltelli: devolve (A, B, AB, rótulos) — os rótulos são os das entradas ou, quando há
    `grupos`, os dos grupos.

    `AB` tem forma (g, n, d): `AB[i]` é a matriz A com as colunas do grupo i trocadas pelas de B. `n`
    tem de ser potência de 2 — a sequência de Sobol só tem a propriedade de equilíbrio nesse tamanho,
    e o scipy avisa quando não é.
    """
    nomes, baixo, alto = _valida_limites(limites)
    d = len(nomes)
    rotulos, colunas = _colunas_por_grupo(nomes, grupos)
    if n < 4:
        raise ErroSensibilidade("n_pequeno_demais", "N tem de ser pelo menos 4")
    if n & (n - 1) != 0:
        raise ErroSensibilidade(
            "n_nao_e_potencia_de_dois",
            f"N tem de ser potência de 2 (recebido {n}); a sequência de Sobol perde o equilíbrio fora disso",
        )
    motor = qmc.Sobol(d=2 * d, scramble=True, seed=semente)
    bruto = motor.random(n)
    a_unit, b_unit = bruto[:, :d], bruto[:, d:]
    escala = alto - baixo
    a = baixo + a_unit * escala
    b = baixo + b_unit * escala
    ab = np.repeat(a[None, :, :], len(colunas), axis=0)
    for i, cols in enumerate(colunas):
        ab[i][:, cols] = b[:, cols]
    return a, b, ab, rotulos


def _indices(fa: np.ndarray, fb: np.ndarray, fab: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Estimadores: 1ª ordem por Saltelli 2010 (`E[f_B (f_ABi − f_A)]`), total por Jansen 1999
    (`E[(f_A − f_ABi)²]/2`). Variância estimada sobre A e B juntos."""
    var = float(np.var(np.concatenate([fa, fb])))
    if var <= 0.0:
        d = fab.shape[0]
        return np.full(d, np.nan), np.full(d, np.nan), var
    s1 = (fb[None, :] * (fab - fa[None, :])).mean(axis=1) / var
    st = ((fa[None, :] - fab) ** 2).mean(axis=1) / (2.0 * var)
    return s1, st, var


def sobol(
    funcao,
    limites,
    *,
    n: int = 1024,
    semente: int,
    n_bootstrap: int = 200,
    nivel_confianca: float = 0.95,
    grupos=None,
) -> ResultadoSobol:
    """Índices de Sobol de `funcao` sobre as entradas de `limites` (dicionário nome → (baixo, alto)).

    `funcao` recebe uma matriz (m × d) de pontos e devolve um vetor de m saídas escalares. `n` é o N
    declarado da amostra de Saltelli; o custo total é `n · (d + 2)` avaliações. A mesma semente dá o
    mesmo resultado bit a bit. `n_bootstrap` reamostra as LINHAS da amostra com reposição para o
    intervalo — é reamostragem da amostra, não avaliação nova da função.
    """
    inicio = time.monotonic()
    if not (0.0 < nivel_confianca < 1.0):
        raise ErroSensibilidade("nivel_invalido", "o nível de confiança tem de estar entre 0 e 1")
    if n_bootstrap < 0:
        raise ErroSensibilidade("bootstrap_invalido", "o número de reamostragens não pode ser negativo")
    a, b, ab, nomes = amostra_saltelli(limites, n, semente, grupos)
    d = len(nomes)

    fa = np.asarray(funcao(a), dtype=np.float64)
    fb = np.asarray(funcao(b), dtype=np.float64)
    if fa.shape != (n,) or fb.shape != (n,):
        raise ErroSensibilidade(
            "saida_incompativel",
            f"a função tem de devolver um vetor com uma saída por linha ({n}); veio {fa.shape}",
        )
    fab = np.empty((d, n), dtype=np.float64)
    for i in range(len(nomes)):
        fab[i] = np.asarray(funcao(ab[i]), dtype=np.float64)
    if not (np.all(np.isfinite(fa)) and np.all(np.isfinite(fb)) and np.all(np.isfinite(fab))):
        raise ErroSensibilidade("saida_nao_finita", "a função devolveu valor não finito; a variância fica indefinida")

    s1, st, var = _indices(fa, fb, fab)
    observacoes: list[str] = []
    if not np.isfinite(var) or var <= 0.0:
        observacoes.append(
            "a variância do resultado é zero na faixa declarada: o resultado não se mexe, e não há "
            "variância para repartir entre as entradas"
        )
        ic_s1 = np.full((d, 2), np.nan)
        ic_st = np.full((d, 2), np.nan)
    else:
        ic_s1, ic_st = _bootstrap(fa, fb, fab, n_bootstrap, nivel_confianca, semente)

    return ResultadoSobol(
        nomes=nomes,
        n=n,
        n_avaliacoes=n * (len(nomes) + 2),
        semente=semente,
        s1=s1,
        st=st,
        ic_s1=ic_s1,
        ic_st=ic_st,
        variancia=var,
        nivel_confianca=nivel_confianca,
        n_bootstrap=n_bootstrap,
        tempo_s=time.monotonic() - inicio,
        observacoes=observacoes,
    )


def _bootstrap(fa, fb, fab, n_bootstrap: int, nivel: float, semente: int):
    d, n = fab.shape
    if n_bootstrap == 0:
        return np.full((d, 2), np.nan), np.full((d, 2), np.nan)
    rng = np.random.default_rng(semente)
    amostras_s1 = np.empty((n_bootstrap, d))
    amostras_st = np.empty((n_bootstrap, d))
    for r in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        s1_r, st_r, _ = _indices(fa[idx], fb[idx], fab[:, idx])
        amostras_s1[r] = s1_r
        amostras_st[r] = st_r
    fora = (1.0 - nivel) / 2.0 * 100.0
    ic_s1 = np.percentile(amostras_s1, [fora, 100.0 - fora], axis=0).T
    ic_st = np.percentile(amostras_st, [fora, 100.0 - fora], axis=0).T
    return ic_s1, ic_st


# --------------------------------------------------------------------------------------------------
# Função de teste de referência: Ishigami. É o padrão da literatura de análise de sensibilidade porque
# os índices dela têm forma fechada — serve para provar que o estimador está certo, não para o produto.
# --------------------------------------------------------------------------------------------------

ISHIGAMI_A = 7.0
ISHIGAMI_B = 0.1
LIMITES_ISHIGAMI = {"x1": (-math.pi, math.pi), "x2": (-math.pi, math.pi), "x3": (-math.pi, math.pi)}


def ishigami(x, a: float = ISHIGAMI_A, b: float = ISHIGAMI_B) -> np.ndarray:
    """`sin(x1) + a·sin²(x2) + b·x3⁴·sin(x1)`, com cada x uniforme em [−π, π]."""
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * (x[:, 2] ** 4) * np.sin(x[:, 0])


def indices_analiticos_ishigami(a: float = ISHIGAMI_A, b: float = ISHIGAMI_B) -> dict[str, list[float]]:
    """Índices de referência em forma fechada (Sobol e Levitan; Saltelli et al., *Global Sensitivity
    Analysis: The Primer*). Com a=7 e b=0,1 dá S1 ≈ [0,314; 0,442; 0] e ST ≈ [0,557; 0,442; 0,244]."""
    v1 = 0.5 * (1.0 + b * math.pi**4 / 5.0) ** 2
    v2 = a**2 / 8.0
    v13 = 8.0 * b**2 * math.pi**8 / 225.0
    total = v1 + v2 + v13
    return {
        "s1": [v1 / total, v2 / total, 0.0],
        "st": [(v1 + v13) / total, v2 / total, v13 / total],
        "variancia": total,
    }


# --------------------------------------------------------------------------------------------------
# Sensibilidade do modelo multicritério
# --------------------------------------------------------------------------------------------------

FAIXA_PESO_PADRAO = (-0.5, 1.0)  # −50 % a +100 % do peso escolhido pelo usuário


def faixa_de_copias(faixa: tuple[float, float], n_copias: int) -> tuple[float, float]:
    """Faixa relativa que cada cópia de um fator repartido em `n_copias` precisa ter para o par (ou
    grupo) de cópias ficar COMPARÁVEL ao fator único.

    Repartir um fator em duas cópias com metade do peso cada e a MESMA faixa relativa NÃO conserva a
    sensibilidade: o peso somado das cópias tem metade da variância do peso único (duas metades
    sorteadas de forma independente), e o índice do par sai proporcionalmente menor. A conta: com peso
    base w/n e faixa relativa ±δ' por cópia, a soma tem variância n·(w/n)²·δ'²/3 = w²δ'²/(3n); igualar
    à variância do peso único (w²δ²/3) exige δ' = δ·√n. É por isso que a comparação honesta entre
    "um fator" e "a mesma camada entrando n vezes" alarga a faixa das cópias por √n — e é essa a
    comparação que a refutação do item usa.
    """
    if n_copias < 1:
        raise ErroSensibilidade("n_copias_invalido", "o número de cópias tem de ser pelo menos 1")
    lo, hi = float(faixa[0]), float(faixa[1])
    if hi <= lo:
        raise ErroSensibilidade("faixa_peso_invalida", "a faixa é (baixo, alto) com alto > baixo")
    centro = (lo + hi) / 2.0
    meia = (hi - lo) / 2.0 * math.sqrt(n_copias)
    return (centro - meia, centro + meia)


def _valida_modelo(fatores, pesos_base, ids_fatores):
    m = np.asarray(fatores, dtype=np.float64)
    if m.ndim != 2:
        raise ErroSensibilidade("matriz_invalida", "a matriz de fatores precisa ter duas dimensões (unidade × fator)")
    w = np.asarray(pesos_base, dtype=np.float64)
    n_unidades, n_fatores = m.shape
    if w.shape != (n_fatores,):
        raise ErroSensibilidade("pesos_incompativeis", f"são {n_fatores} fatores e {w.size} pesos")
    if not np.all(np.isfinite(w)) or np.any(w < 0) or w.sum() <= 0:
        raise ErroSensibilidade("peso_base_invalido", "peso base precisa ser finito, ≥ 0 e somar mais que zero")
    ids = list(ids_fatores) if ids_fatores is not None else [f"fator_{i}" for i in range(n_fatores)]
    if len(ids) != n_fatores:
        raise ErroSensibilidade("ids_incompativeis", f"são {n_fatores} fatores e {len(ids)} identificadores")
    return m, w, ids, n_unidades, n_fatores


def _resolve_k(k_top, n_unidades: int) -> int:
    k = k_top if k_top is not None else max(1, round(n_unidades * 0.1))
    if not (1 <= k <= n_unidades):
        raise ErroSensibilidade("k_top_invalido", "k_top tem de estar entre 1 e o número de unidades")
    return k


def _topk(fav: np.ndarray, vetado: np.ndarray, k: int) -> np.ndarray:
    """Índices das k melhores unidades. Unidade vetada ou sem nota sai da classificação por construção."""
    ranking = np.where(vetado | ~np.isfinite(fav), -np.inf, fav)
    ordem = np.argsort(-ranking, kind="stable")[:k]
    return ordem[ranking[ordem] > -np.inf]


def _avaliador(m, w_base, ids, *, alvo, k, combinador, politica_ausente, fracao_vetada, transformacao,
               parametros_base):
    """Devolve (função vetorizada para o Sobol, top-k base). A função recebe pontos cujas primeiras
    colunas são multiplicadores de peso e as demais são parâmetros de transformação, na ordem declarada.

    A configuração BASE — a que o usuário escolheu — é multiplicador 1 em todo peso e, no parâmetro de
    transformação, o meio da faixa declarada. É contra o top-k dessa configuração que se mede o quanto
    a lista muda."""
    n_fatores = len(ids)
    nomes_parametros = list(parametros_base)

    def _uma(multiplicadores, parametros) -> tuple[np.ndarray, np.ndarray]:
        matriz = m if transformacao is None else np.asarray(transformacao(m, parametros), dtype=np.float64)
        try:
            r = combinar(matriz, w_base * multiplicadores, combinador=combinador,
                         politica_ausente=politica_ausente, fracao_vetada=fracao_vetada, ids_fatores=ids)
        except ErroCombinacao as e:
            raise ErroSensibilidade("erro_na_combinacao", e.mensagem, e.detalhe) from e
        return r.fav, r.vetado

    fav_base, vetado_base = _uma(np.ones(n_fatores), dict(parametros_base))
    base_topk = set(int(i) for i in _topk(fav_base, vetado_base, k))

    def funcao(pontos: np.ndarray) -> np.ndarray:
        pontos = np.atleast_2d(pontos)
        saida = np.empty(pontos.shape[0])
        for linha in range(pontos.shape[0]):
            mult = pontos[linha, :n_fatores]
            params = {nome: float(v) for nome, v in zip(nomes_parametros, pontos[linha, n_fatores:], strict=True)}
            fav, vetado = _uma(mult, params)
            if alvo == "concordancia_topk":
                atual = set(int(i) for i in _topk(fav, vetado, k))
                saida[linha] = len(atual & base_topk) / k
            else:  # nota_media
                finito = np.isfinite(fav)
                saida[linha] = float(fav[finito].mean()) if finito.any() else 0.0
        return saida

    return funcao, sorted(base_topk)


def sensibilidade_global(
    fatores,
    pesos_base,
    *,
    ids_fatores=None,
    n: int = 256,
    semente: int,
    alvo: str = "concordancia_topk",
    k_top: int | None = None,
    faixa_peso: tuple[float, float] = FAIXA_PESO_PADRAO,
    faixas_peso: dict | None = None,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada=None,
    transformacao=None,
    faixas_parametros: dict | None = None,
    n_bootstrap: int = 100,
    nivel_confianca: float = 0.95,
    grupos=None,
) -> ResultadoSobol:
    """Índices de Sobol do modelo: entradas = um multiplicador por peso (faixa declarada, padrão −50 %
    a +100 %) mais os parâmetros de transformação de `faixas_parametros`, sorteados na mesma amostra.

    O nome da entrada de peso é ``peso:<id do fator>``, o do parâmetro é ``parametro:<nome>`` — para a
    leitura não confundir "mexer no peso do fator" com "mexer no fator". `faixas_peso` troca a faixa de
    fatores nomeados, um a um (é o que a refutação do fator duplicado precisa; ver `faixa_de_copias`).
    """
    m, w, ids, n_unidades, n_fatores = _valida_modelo(fatores, pesos_base, ids_fatores)
    if alvo not in ALVOS:
        raise ErroSensibilidade("alvo_desconhecido", f"alvo desconhecido: {alvo}", {"aceitos": sorted(ALVOS)})
    lo, hi = float(faixa_peso[0]), float(faixa_peso[1])
    if hi <= lo or lo <= -1.0:
        raise ErroSensibilidade("faixa_peso_invalida", "a faixa do peso é (baixo, alto) com baixo > −1 e alto > baixo")
    k = _resolve_k(k_top, n_unidades)
    faixas_parametros = dict(faixas_parametros or {})
    if faixas_parametros and transformacao is None:
        raise ErroSensibilidade(
            "parametro_sem_transformacao",
            "há parâmetro de transformação declarado mas nenhuma função de transformação foi passada",
        )
    parametros_base = {nome: (float(faixa[0]) + float(faixa[1])) / 2.0
                       for nome, faixa in faixas_parametros.items()}
    faixas_peso = dict(faixas_peso or {})
    desconhecidos = sorted(set(faixas_peso) - set(ids))
    if desconhecidos:
        raise ErroSensibilidade(
            "faixa_de_fator_desconhecido",
            "faixa declarada para fator que não está no modelo: " + ", ".join(desconhecidos),
            {"desconhecidos": desconhecidos},
        )
    limites = {}
    for i in ids:
        f_lo, f_hi = faixas_peso.get(i, (lo, hi))
        if f_hi <= f_lo or f_lo <= -1.0:
            raise ErroSensibilidade("faixa_peso_invalida",
                                    f"a faixa do peso do fator {i} é (baixo, alto) com baixo > -1 e alto > baixo")
        limites[f"peso:{i}"] = (1.0 + float(f_lo), 1.0 + float(f_hi))
    limites.update({f"parametro:{nome}": tuple(faixa) for nome, faixa in faixas_parametros.items()})

    funcao, _ = _avaliador(m, w, ids, alvo=alvo, k=k, combinador=combinador,
                           politica_ausente=politica_ausente, fracao_vetada=fracao_vetada,
                           transformacao=transformacao, parametros_base=parametros_base)
    resultado = sobol(funcao, limites, n=n, semente=semente, n_bootstrap=n_bootstrap,
                      nivel_confianca=nivel_confianca, grupos=grupos)
    resultado.observacoes.append(
        f"alvo {alvo}: {ALVOS[alvo]}; k = {k} de {n_unidades} unidades; peso variando de "
        f"{lo * 100:+.0f} % a {hi * 100:+.0f} % do escolhido pelo usuário"
    )
    if combinador in ("soma_ponderada", "media_geometrica"):
        resultado.observacoes.append(
            "este combinador normaliza pela soma dos pesos, então só o peso RELATIVO conta: mexer em um "
            "peso sozinho quase sempre aparece como interação com os outros. Por isso o índice de 1ª ordem "
            "sai baixo e o índice TOTAL é o que se lê aqui"
        )
    return resultado


def tornado_oat(
    fatores,
    pesos_base,
    *,
    ids_fatores=None,
    k_top: int | None = None,
    faixa_peso: tuple[float, float] = FAIXA_PESO_PADRAO,
    passos: int = 9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada=None,
) -> dict:
    """Sensibilidade local, um fator por vez: move o peso de cada fator dentro da faixa (os demais
    parados no valor escolhido pelo usuário) e mede quanto a lista dos k melhores muda.

    Devolve, por fator, a concordância com o top-k base no limite de baixo, no de cima, a menor
    concordância vista na varredura e a amplitude (1 − menor concordância) — a barra do tornado.
    """
    inicio = time.monotonic()
    m, w, ids, n_unidades, n_fatores = _valida_modelo(fatores, pesos_base, ids_fatores)
    k = _resolve_k(k_top, n_unidades)
    lo, hi = float(faixa_peso[0]), float(faixa_peso[1])
    if hi <= lo or lo <= -1.0:
        raise ErroSensibilidade("faixa_peso_invalida", "a faixa do peso é (baixo, alto) com baixo > −1 e alto > baixo")
    if passos < 2:
        raise ErroSensibilidade("passos_invalido", "a varredura precisa de pelo menos 2 passos")

    funcao, base_topk = _avaliador(m, w, ids, alvo="concordancia_topk", k=k, combinador=combinador,
                                   politica_ausente=politica_ausente, fracao_vetada=fracao_vetada,
                                   transformacao=None, parametros_base={})
    multiplicadores = np.linspace(1.0 + lo, 1.0 + hi, passos)
    barras = []
    for i, nome in enumerate(ids):
        pontos = np.ones((passos, n_fatores))
        pontos[:, i] = multiplicadores
        concordancia = funcao(pontos)
        barras.append({
            "fator": nome,
            "peso_base": float(w[i]),
            "concordancia_no_minimo": float(concordancia[0]),
            "concordancia_no_maximo": float(concordancia[-1]),
            "menor_concordancia": float(concordancia.min()),
            "amplitude": float(1.0 - concordancia.min()),
            "multiplicadores": [float(x) for x in multiplicadores],
            "concordancia": [float(x) for x in concordancia],
        })
    barras.sort(key=lambda b: (-b["amplitude"], b["fator"]))
    return {
        "aviso": AVISO_SENSIBILIDADE,
        "texto_explicacao": TEXTO_EXPLICACAO,
        "metodo": "um fator por vez (OAT): move o peso de um fator e deixa os outros parados; "
                  "cego a interação entre fatores, por isso anda junto com o índice de Sobol",
        "k_top": k,
        "n_unidades": n_unidades,
        "faixa_peso": [lo, hi],
        "passos": passos,
        "top_k_base": base_topk,
        "barras": barras,
        "tempo_s": time.monotonic() - inicio,
    }


def relatorio_sensibilidade(
    fatores,
    pesos_base,
    *,
    modelo: str,
    versao_modelo: str | None = None,
    ids_fatores=None,
    n: int = 256,
    semente: int,
    alvo: str = "concordancia_topk",
    k_top: int | None = None,
    faixa_peso: tuple[float, float] = FAIXA_PESO_PADRAO,
    passos_tornado: int = 9,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada=None,
    transformacao=None,
    faixas_parametros: dict | None = None,
    n_bootstrap: int = 100,
    nivel_confianca: float = 0.95,
) -> dict:
    """Relatório de sensibilidade de UM modelo: global (Sobol, com N, índices e intervalo por
    bootstrap), local (tornado OAT), tempo medido de cada parte e o texto que explica o que a
    sensibilidade mede e o que ela NÃO mede."""
    inicio = time.monotonic()
    global_ = sensibilidade_global(
        fatores, pesos_base, ids_fatores=ids_fatores, n=n, semente=semente, alvo=alvo, k_top=k_top,
        faixa_peso=faixa_peso, combinador=combinador, politica_ausente=politica_ausente,
        fracao_vetada=fracao_vetada, transformacao=transformacao, faixas_parametros=faixas_parametros,
        n_bootstrap=n_bootstrap, nivel_confianca=nivel_confianca,
    )
    local = tornado_oat(
        fatores, pesos_base, ids_fatores=ids_fatores, k_top=k_top, faixa_peso=faixa_peso,
        passos=passos_tornado, combinador=combinador, politica_ausente=politica_ausente,
        fracao_vetada=fracao_vetada,
    )
    ordem = sorted(range(len(global_.nomes)), key=lambda i: -(global_.st[i] if np.isfinite(global_.st[i]) else -1))
    mandam = [global_.nomes[i] for i in ordem if np.isfinite(global_.st[i]) and global_.st[i] >= LIMIAR_IRRELEVANTE]
    return {
        "modelo": modelo,
        "versao_modelo": versao_modelo,
        "aviso": AVISO_SENSIBILIDADE,
        "texto_explicacao": TEXTO_EXPLICACAO,
        "alvo": alvo,
        "descricao_alvo": ALVOS[alvo],
        "global": global_.como_dicionario(),
        "local": local,
        "mandam_no_resultado": mandam,
        "irrelevantes": global_.irrelevantes,
        "tempo_global_s": global_.tempo_s,
        "tempo_local_s": local["tempo_s"],
        "tempo_s": time.monotonic() - inicio,
    }
