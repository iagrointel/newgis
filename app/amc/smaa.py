"""SMAA-2 simplificado — análise de aceitabilidade estocástica multicritério (item L3-02-c).

Referência: Lahdelma, R. e Salminen, P. (2001). "SMAA-2: Reference Point Based Preference Modeling
Rendering Aggregation Method for Group Decision Making". Operations Research 49(3), 444-454.

O que este módulo responde é a pergunta inversa da do motor: em vez de "qual é a nota desta unidade
com o peso que o usuário escolheu", ele responde "que pesos precisariam ser verdade para esta unidade
ficar em primeiro lugar". Três medidas, todas do artigo de 2001:

- índice de aceitabilidade por posição (b^r_i): a fração dos vetores de peso sorteados em que a unidade
  i ficou na posição r do ranking. A primeira coluna, b^1, é a aceitabilidade de primeiro lugar.
- vetor central de pesos (w^c_i): a média dos vetores de peso que colocaram a unidade i em primeiro
  lugar, normalizada para somar 1. É a resposta literal a "que pesos fariam esta unidade ganhar";
  quando b^1_i é zero o vetor central não existe e vem como ausente, nunca como zero.
- fator de confiança (p^c_i): 1 se a unidade realmente fica em primeiro quando a combinação é refeita
  com o vetor central dela, 0 se não fica. É MEDIDO, recombinando; não é assumido.

Decisões de conceito que este módulo obedece (laco/decomposicao/L3L6_CONCEITO.md):

- A9: guarda só agregados por unidade (aceitabilidade por posição, vetor central, fator de confiança)
  mais a semente — nunca a matriz N × unidades. Mesma semente reproduz o resultado bit a bit.
- A6: veto e restrição não entram no sorteio. A unidade vetada é excluída do ranking por construção, em
  todos os sorteios, e por isso tem aceitabilidade zero em toda posição — nunca por a nota ficar baixa.
- A2/A9: a combinação é a função pura de `app.amc.combinacao.combinar` (item L3-01-e) e o sorteio de
  pesos é `app.amc.robustez.sortear_pesos` (item L3-02-a). Este módulo não reimplementa nenhum dos dois.

Limites declarados (também em docs/AMC_SMAA.md, e a saída os carrega em `limites`):

1. O SMAA-2 do artigo trata incerteza NOS CRITÉRIOS e NOS PESOS. Aqui os fatores já extraídos são
   tratados como determinísticos: só o peso é sorteado. Toda leitura vale "sob incerteza de peso",
   nunca "sob incerteza do dado".
2. Com fator determinístico e combinador linear (`soma_ponderada`), a região de pesos que faz uma
   unidade ganhar é convexa, então a média dos pesos vencedores cai dentro dela e o fator de confiança
   dá 1 por construção para toda unidade com b^1 > 0. Ele só é informativo com combinador não linear.
   Por isso o fator é medido e não assumido: com `media_geometrica` ele pode dar 0.
3. Combinador que ignora peso por definição (mínimo, máximo, produto, soma fuzzy, gama) torna o
   sorteio inócuo: o ranking não muda entre sorteios e a aceitabilidade vira 0 ou 1. A saída avisa.
4. Empate de nota entre unidades é desempatado pela ordem das unidades na matriz, de forma
   determinística. Com peso contínuo o empate tem probabilidade zero, mas com fator inteiro e poucos
   fatores ele acontece, e aí a aceitabilidade depende da ordem de entrada — o aviso sai na saída.
5. b^r só é contado até a posição `posicoes` (padrão 20). Unidade que nunca aparece nessas posições
   tem a linha inteira em zero, o que não quer dizer que ela seja a última.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from app.amc.combinacao import COMBINADORES, SEM_PESO, ErroCombinacao, combinar
from app.amc.robustez import ErroRobustez, sortear_pesos

REFERENCIA = ("Lahdelma, R. e Salminen, P. (2001). SMAA-2: Reference Point Based Preference Modeling "
              "Rendering Aggregation Method for Group Decision Making. Operations Research 49(3), 444-454.")

AVISO_SMAA = ("a aceitabilidade responde 'que pesos precisariam ser verdade para esta unidade ganhar'; "
              "ela descreve o espaço de pesos, não recomenda peso nenhum")

LIMITES = [
    "só o peso é sorteado: o fator já extraído entra como determinístico, então a leitura vale sob "
    "incerteza de peso e nunca sob incerteza do dado",
    "com combinador linear e fator determinístico a região de pesos vencedores é convexa, então o fator "
    "de confiança dá 1 por construção para toda unidade com aceitabilidade de primeiro lugar acima de "
    "zero; ele só separa unidades com combinador não linear",
    "combinador que ignora peso por definição deixa o ranking igual em todos os sorteios e a "
    "aceitabilidade vira 0 ou 1",
    "empate de nota é desempatado pela ordem da unidade na matriz, de forma determinística",
    "a aceitabilidade é contada só até a posição declarada; linha toda em zero não quer dizer último "
    "lugar, quer dizer fora dessas posições",
]

POSICOES_PADRAO = 20
TOPO_PADRAO = 20


@dataclass
class ResultadoSmaa:
    """Resumo por unidade de N sorteios de peso. Nunca guarda o sorteio inteiro (N × unidades)."""

    semente: int
    metodo: str
    n_sorteios: int
    n_unidades: int
    ids_fatores: list[str]
    pesos_base_normalizados: list[float]
    posicoes: int
    topo: int
    aceitabilidade: np.ndarray          # unidade × posição, fração dos sorteios
    vetor_central: np.ndarray           # unidade × fator, nan onde não houve primeiro lugar
    fator_confianca: np.ndarray         # unidade, nan onde não houve primeiro lugar
    media_fav: np.ndarray
    vetado: np.ndarray
    sorteios_sem_vencedor: int
    empates_no_primeiro: int
    combinador: str
    tempo_s: float
    observacoes: list[str] = field(default_factory=list)
    aviso_pesos: str = AVISO_SMAA
    referencia: str = REFERENCIA

    @property
    def soma_aceitabilidade_primeiro(self) -> float:
        """Soma de b^1 sobre TODAS as unidades. Cada sorteio tem no máximo um vencedor, então isto vale
        (n_sorteios − sorteios_sem_vencedor) / n_sorteios: 1 quando existe pelo menos uma unidade não
        vetada e com nota em todo sorteio. É a conferência que o adversário do item faz."""
        return float(self.aceitabilidade[:, 0].sum())

    def indices_do_topo(self) -> list[int]:
        """Os `topo` melhores por aceitabilidade de primeiro lugar; empate desempatado pela média da nota
        e depois pela ordem da unidade, de forma determinística."""
        b1 = self.aceitabilidade[:, 0]
        media = np.where(np.isfinite(self.media_fav), self.media_fav, -np.inf)
        ordem = np.lexsort((np.arange(self.n_unidades), -media, -b1))
        return [int(i) for i in ordem[: min(self.topo, self.n_unidades)]]

    def tabela_do_topo(self, ids_unidades: list[str] | None = None) -> list[dict]:
        """Tabela de aceitabilidade do topo: uma linha por unidade, uma coluna por posição.
        `vetor_central` e `fator_confianca` vão na mesma linha — é o que a explicação exibe."""
        linhas = []
        for pos, i in enumerate(self.indices_do_topo(), start=1):
            central = self.vetor_central[i]
            linhas.append({
                "posicao_na_tabela": pos,
                "indice_unidade": i,
                "id_unidade": (ids_unidades[i] if ids_unidades is not None else None),
                "aceitabilidade": [float(v) for v in self.aceitabilidade[i]],
                "aceitabilidade_primeiro": float(self.aceitabilidade[i, 0]),
                "media_fav": (None if not np.isfinite(self.media_fav[i]) else float(self.media_fav[i])),
                "vetado": bool(self.vetado[i]),
                "vetor_central": (None if not np.all(np.isfinite(central))
                                  else {self.ids_fatores[j]: float(central[j]) for j in range(central.size)}),
                "fator_confianca": (None if not np.isfinite(self.fator_confianca[i])
                                    else float(self.fator_confianca[i])),
            })
        return linhas

    def explicacao_da_unidade(self, indice: int, ids_unidades: list[str] | None = None) -> dict:
        """Explicação de UMA unidade, em português e com o vetor central exibido fator a fator.

        É o texto que a tela e o PDF mostram: quantas vezes a unidade ganhou, que peso por fator
        precisaria ser verdade para isso, e se esse peso, aplicado de volta, de fato a coloca em
        primeiro (fator de confiança). Sem vetor central, diz que não existe e por quê."""
        if not (0 <= indice < self.n_unidades):
            raise ErroSmaa("indice_invalido", "índice de unidade fora da matriz")
        b = self.aceitabilidade[indice]
        central = self.vetor_central[indice]
        nome = ids_unidades[indice] if ids_unidades is not None else f"unidade {indice}"
        tem_central = bool(np.all(np.isfinite(central)))
        if self.vetado[indice]:
            frase = (f"{nome} está vetada: fica fora da classificação em todos os {self.n_sorteios} sorteios "
                     "por construção, então não existe peso que a faça ganhar")
        elif not tem_central:
            frase = (f"{nome} não ficou em primeiro lugar em nenhum dos {self.n_sorteios} sorteios de peso, "
                     "então não existe vetor central de pesos para ela neste sorteio")
        else:
            pares = ", ".join(f"{self.ids_fatores[j]} {central[j] * 100:.1f} %" for j in range(central.size))
            frase = (f"{nome} ficou em primeiro lugar em {b[0] * 100:.1f} % dos {self.n_sorteios} sorteios. "
                     f"O peso médio que a levou ao primeiro lugar (vetor central) é: {pares}. "
                     f"Refazendo a combinação com esse peso, ela "
                     f"{'fica' if self.fator_confianca[indice] >= 1.0 else 'não fica'} em primeiro lugar "
                     f"(fator de confiança {self.fator_confianca[indice]:.2f})")
        return {
            "indice_unidade": indice,
            "id_unidade": (ids_unidades[indice] if ids_unidades is not None else None),
            "aceitabilidade": [float(v) for v in b],
            "vetor_central": (None if not tem_central
                              else {self.ids_fatores[j]: float(central[j]) for j in range(central.size)}),
            "fator_confianca": (None if not np.isfinite(self.fator_confianca[indice])
                                else float(self.fator_confianca[indice])),
            "texto": frase,
            "aviso_pesos": self.aviso_pesos,
            "referencia": self.referencia,
        }

    def como_dicionario(self, ids_unidades: list[str] | None = None) -> dict:
        return {
            "aviso_pesos": self.aviso_pesos,
            "referencia": self.referencia,
            "limites": list(LIMITES),
            "semente": self.semente,
            "metodo": self.metodo,
            "n_sorteios": self.n_sorteios,
            "n_unidades": self.n_unidades,
            "ids_fatores": list(self.ids_fatores),
            "pesos_base_normalizados": list(self.pesos_base_normalizados),
            "posicoes": self.posicoes,
            "topo": self.topo,
            "combinador": self.combinador,
            "descricao_combinador": COMBINADORES[self.combinador],
            "tempo_s": self.tempo_s,
            "sorteios_sem_vencedor": self.sorteios_sem_vencedor,
            "empates_no_primeiro": self.empates_no_primeiro,
            "soma_aceitabilidade_primeiro": self.soma_aceitabilidade_primeiro,
            "observacoes": list(self.observacoes),
            "tabela_topo": self.tabela_do_topo(ids_unidades),
        }


class ErroSmaa(ValueError):
    """Erro de contrato do SMAA. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


def _ranking_decrescente(ranking: np.ndarray, quantas: int) -> np.ndarray:
    """Índices das `quantas` maiores notas, em ordem decrescente, com empate desempatado pelo índice da
    unidade. `argpartition` evita ordenar a coluna inteira quando há milhares de unidades."""
    n = ranking.size
    if quantas >= n:
        return np.lexsort((np.arange(n), -ranking))
    candidatos = np.argpartition(-ranking, quantas - 1)[:quantas]
    ordem = np.lexsort((candidatos, -ranking[candidatos]))
    return candidatos[ordem]


def simular_smaa(
    fatores,
    pesos_base,
    *,
    n: int = 1000,
    metodo: str = "dirichlet",
    concentracao: float | None = None,
    k_percentual: float = 0.3,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    fracao_vetada=None,
    motivo_veto=None,
    ids_fatores: list[str] | None = None,
    posicoes: int = POSICOES_PADRAO,
    topo: int = TOPO_PADRAO,
    semente: int,
    progresso=None,
) -> ResultadoSmaa:
    """Roda `n` recombinações do MESMO fator já extraído com pesos sorteados e resume, por unidade, a
    aceitabilidade por posição, o vetor central de pesos e o fator de confiança."""
    inicio = time.monotonic()
    m = fatores if isinstance(fatores, np.ndarray) else np.asarray(fatores, dtype=np.float64)
    m = m.astype(np.float64, copy=False)
    if m.ndim != 2:
        raise ErroSmaa("matriz_invalida", "a matriz de fatores precisa ter duas dimensões (unidade × fator)")
    n_unidades, n_fatores = m.shape
    if n_unidades < 1 or n_fatores < 1:
        raise ErroSmaa("matriz_vazia", "a matriz de fatores precisa ter pelo menos uma unidade e um fator")
    ids_fatores = list(ids_fatores) if ids_fatores is not None else [f"fator_{i}" for i in range(n_fatores)]
    if combinador not in COMBINADORES:
        raise ErroSmaa("combinador_desconhecido", f"combinador desconhecido: {combinador}",
                       {"aceitos": sorted(COMBINADORES)})
    if not (1 <= posicoes <= 1000):
        raise ErroSmaa("posicoes_invalidas", "o número de posições tem de estar entre 1 e 1000")
    if topo < 1:
        raise ErroSmaa("topo_invalido", "o topo da tabela tem de ser pelo menos 1")

    try:
        pesos = sortear_pesos(pesos_base, ids_fatores, n, metodo=metodo, concentracao=concentracao,
                              k_percentual=k_percentual, semente=semente)
    except ErroRobustez as e:
        raise ErroSmaa(e.codigo, e.mensagem, e.detalhe) from e

    vetado_fixo = np.zeros(n_unidades, dtype=bool)
    if fracao_vetada is not None:
        vetado_fixo = np.asarray(fracao_vetada, dtype=np.float64) >= 1.0

    p = min(posicoes, n_unidades)
    conta_posicao = np.zeros((n_unidades, p), dtype=np.int64)
    soma_peso_vencedor = np.zeros((n_unidades, n_fatores), dtype=np.float64)
    conta_primeiro = np.zeros(n_unidades, dtype=np.int64)
    soma_fav = np.zeros(n_unidades, dtype=np.float64)
    conta_fav = np.zeros(n_unidades, dtype=np.int64)
    sem_vencedor = 0
    empates_primeiro = 0
    marco = max(1, n // 10)

    for j in range(n):
        try:
            r = combinar(m, pesos[j], combinador=combinador, politica_ausente=politica_ausente,
                         fracao_vetada=fracao_vetada, motivo_veto=motivo_veto, ids_fatores=ids_fatores)
        except ErroCombinacao as e:
            raise ErroSmaa("erro_na_combinacao", f"sorteio {j}: {e.mensagem}", e.detalhe) from e
        fav = r.fav
        presente = np.isfinite(fav)
        soma_fav[presente] += fav[presente]
        conta_fav += presente

        # A unidade vetada e a sem nota saem do ranking POR CONSTRUÇÃO, não por a nota ficar baixa.
        valido = presente & ~vetado_fixo
        n_validas = int(valido.sum())
        if n_validas == 0:
            sem_vencedor += 1
            if progresso is not None and ((j + 1) % marco == 0 or j + 1 == n):
                progresso(int((j + 1) * 100 / n))
            continue
        ranking = np.where(valido, fav, -np.inf)
        quantas = min(p, n_validas)
        ordem = _ranking_decrescente(ranking, quantas)
        conta_posicao[ordem, np.arange(quantas)] += 1

        vencedor = int(ordem[0])
        conta_primeiro[vencedor] += 1
        soma_peso_vencedor[vencedor] += pesos[j]
        if n_validas > 1 and quantas > 1 and ranking[ordem[1]] == ranking[vencedor]:
            empates_primeiro += 1

        if progresso is not None and ((j + 1) % marco == 0 or j + 1 == n):
            progresso(int((j + 1) * 100 / n))

    aceitabilidade = conta_posicao / float(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        media_fav = np.where(conta_fav > 0, soma_fav / np.maximum(conta_fav, 1), np.nan)

    vetor_central = np.full((n_unidades, n_fatores), np.nan, dtype=np.float64)
    ganhou = conta_primeiro > 0
    if ganhou.any():
        bruto = soma_peso_vencedor[ganhou] / conta_primeiro[ganhou][:, None]
        vetor_central[ganhou] = bruto / bruto.sum(axis=1, keepdims=True)

    fator_confianca = _fator_de_confianca(m, vetor_central, ganhou, vetado_fixo, combinador,
                                          politica_ausente, fracao_vetada, motivo_veto, ids_fatores)

    observacoes = [
        f"{int(vetado_fixo.sum())} de {n_unidades} unidades vetadas: fora da classificação em todos os {n} "
        "sorteios por construção, com aceitabilidade zero em toda posição",
        f"{int(ganhou.sum())} de {n_unidades} unidades ficaram em primeiro lugar em pelo menos um sorteio e "
        "por isso têm vetor central de pesos",
    ]
    if combinador in SEM_PESO:
        observacoes.append(
            f"o combinador '{combinador}' ignora o peso por definição: o ranking é o mesmo em todos os "
            "sorteios e a aceitabilidade só pode dar 0 ou 1")
    if empates_primeiro:
        observacoes.append(
            f"{empates_primeiro} de {n} sorteios tiveram empate de nota no primeiro lugar, desempatado pela "
            "ordem da unidade na matriz")
    if sem_vencedor:
        observacoes.append(
            f"{sem_vencedor} de {n} sorteios não tiveram nenhuma unidade classificável (todas vetadas ou sem "
            "nota): a soma da aceitabilidade de primeiro lugar fica abaixo de 1 por isso, não por erro")

    return ResultadoSmaa(
        semente=semente,
        metodo=metodo,
        n_sorteios=n,
        n_unidades=n_unidades,
        ids_fatores=ids_fatores,
        pesos_base_normalizados=[float(x) for x in (np.asarray(pesos_base, dtype=np.float64) /
                                                    np.asarray(pesos_base, dtype=np.float64).sum())],
        posicoes=p,
        topo=topo,
        aceitabilidade=aceitabilidade,
        vetor_central=vetor_central,
        fator_confianca=fator_confianca,
        media_fav=media_fav,
        vetado=vetado_fixo,
        sorteios_sem_vencedor=sem_vencedor,
        empates_no_primeiro=empates_primeiro,
        combinador=combinador,
        tempo_s=time.monotonic() - inicio,
        observacoes=observacoes,
    )


def _fator_de_confianca(m, vetor_central, ganhou, vetado_fixo, combinador, politica_ausente,
                        fracao_vetada, motivo_veto, ids_fatores) -> np.ndarray:
    """Refaz a combinação com o vetor central de cada unidade e mede se ela realmente fica em primeiro.
    Uma combinação por unidade com vetor central — nunca uma por sorteio."""
    n_unidades = m.shape[0]
    saida = np.full(n_unidades, np.nan, dtype=np.float64)
    for i in np.nonzero(ganhou)[0]:
        r = combinar(m, vetor_central[i], combinador=combinador, politica_ausente=politica_ausente,
                     fracao_vetada=fracao_vetada, motivo_veto=motivo_veto, ids_fatores=ids_fatores)
        valido = np.isfinite(r.fav) & ~vetado_fixo
        if not valido.any():
            saida[i] = 0.0
            continue
        ranking = np.where(valido, r.fav, -np.inf)
        vencedor = int(np.lexsort((np.arange(n_unidades), -ranking))[0])
        saida[i] = 1.0 if vencedor == int(i) else 0.0
    return saida
