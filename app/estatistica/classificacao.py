"""Motor de classificação numérica (item L2-02-b-classificacao-servidor).

Cada função recebe um vetor numpy 1D já sem nulos (o nulo é contado à parte, nunca entra na conta)
e devolve os CORTES (breakpoints) da classificação, sempre em ordem crescente, sempre com
`len(cortes) == n_classes + 1` (primeiro corte = mínimo, último = máximo).

Fontes declaradas no item (estilo de classificação Esri, ADR do L2-02-a):
- https://doc.arcgis.com/en/arcgis-online/create-maps/style-numbers-mv.htm
- https://enterprise.arcgis.com/en/portal/11.4/use/style-numbers-mv.htm
- https://developers.arcgis.com/documentation/common-data-types/histogram-object.htm

Decisão de arquitetura (ADR 20260907-classificacao-servidor): quantil e intervalo igual usam
`numpy.quantile`/`numpy.linspace` diretamente — são a referência, não uma aproximação delas. Quebras
naturais (Jenks) são uma implementação própria (Fisher 1958 / variância mínima dentro do grupo) via
programação dinâmica com somas de prefixo em numpy; para não pagar O(n²) sobre a coluna inteira, os
valores são primeiro reduzidos a um vetor PONDERADO de valores DISTINTOS (`numpy.unique` com
`return_counts=True`) — isso é uma soma exata, nunca uma amostra, e é o motivo de o resultado bater
exatamente com uma implementação de referência quando os dados de teste não passam do teto de
distintos (`TETO_POSICOES_JENKS`). Só quando o número de valores DISTINTOS passa desse teto (dado de
altíssima cardinalidade) os valores são reagrupados num histograma de largura igual com esse mesmo
teto de posições — ainda soma de todos os valores, não descarta nenhum. Amostragem estratificada de
verdade (descartar linhas) só entra quando o total de valores não nulos passa de
`TETO_SEM_AMOSTRA` (1 milhão), e a resposta da rota declara isso em `amostrado`/`tamanho_amostra`."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TETO_SEM_AMOSTRA = 1_000_000
TETO_POSICOES_JENKS = 2048
LIMITE_VALORES_UNICOS = 200
FRACOES_DESVIO_PADRAO = (1.0, 0.5, 1.0 / 3.0, 0.25)


class ErroClassificacao(Exception):
    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(mensagem)


def separar_nulos(valores: np.ndarray) -> tuple[np.ndarray, int]:
    """[valores sem nulo/NaN, contagem de nulos]. Nunca inclui NaN/None na conta de classes."""
    mask = ~np.isnan(valores)
    validos = valores[mask]
    return validos, int(valores.size - validos.size)


def resumo(valores: np.ndarray, nulos: int) -> dict:
    """min/max/média/desvio/nulos — desvio populacional (ddof=0, mesma convenção do desvio_padrao)."""
    if valores.size == 0:
        return {
            "minimo": None, "maximo": None, "media": None, "desvio_padrao": None,
            "nulos": nulos, "total": nulos, "validos": 0,
        }
    return {
        "minimo": float(np.min(valores)),
        "maximo": float(np.max(valores)),
        "media": float(np.mean(valores)),
        "desvio_padrao": float(np.std(valores, ddof=0)),
        "nulos": nulos,
        "total": int(valores.size) + nulos,
        "validos": int(valores.size),
    }


def histograma(valores: np.ndarray, n_faixas: int) -> dict:
    """Histograma de N faixas de largura igual (`numpy.histogram`), para acompanhar qualquer método."""
    if valores.size == 0:
        return {"cortes": [], "contagens": []}
    contagens, cortes = np.histogram(valores, bins=n_faixas)
    return {"cortes": [float(c) for c in cortes], "contagens": [int(c) for c in contagens]}


def contagem_por_classe(valores: np.ndarray, cortes: list[float]) -> list[int]:
    """Quantos valores caem em cada classe definida por `cortes` (len(cortes) = n_classes + 1),
    classe i = (cortes[i], cortes[i+1]] exceto a primeira, que é [cortes[0], cortes[1]].

    Implementado com `searchsorted` cumulativo sobre o vetor ORDENADO, nunca com
    `numpy.histogram(bins=cortes)`: quando duas classes adjacentes têm o mesmo corte (uma classe
    de um único valor repetido — comum em Jenks sobre dado com muita repetição), `numpy.histogram`
    cria um bin de largura zero que fica sempre com contagem 0 e empurra esse valor para a classe
    seguinte, produzindo uma classe VAZIA que não é vazia de verdade (cláusula do portão:
    "repetidos não geram classe vazia"). `searchsorted(side='right')` cumulativo não tem esse
    defeito: o valor repetido cai inteiro na classe a que pertence, mesmo com corte degenerado."""
    if valores.size == 0 or len(cortes) < 2:
        return [0] * max(len(cortes) - 1, 0)
    ordenado = np.sort(valores)
    limites = [int(np.searchsorted(ordenado, c, side="right")) for c in cortes[1:]]
    limites[-1] = ordenado.size  # o último corte é o máximo: tudo até ele, inclusive, entra
    anteriores = 0
    contagens = []
    for lim in limites:
        contagens.append(max(lim - anteriores, 0))
        anteriores = lim
    return contagens


def _validar_n(valores: np.ndarray, n: int) -> None:
    if n < 1:
        raise ErroClassificacao("n_invalido", "n precisa ser >= 1")
    if valores.size == 0:
        raise ErroClassificacao("sem_dados", "campo sem nenhum valor numérico não nulo")


def quantil(valores: np.ndarray, n: int) -> list[float]:
    """Cortes de quantil: idênticos a `numpy.quantile(valores, numpy.linspace(0, 1, n + 1))`
    (cláusula do portão) — literalmente a mesma chamada, sem reimplementação própria."""
    _validar_n(valores, n)
    cortes = np.quantile(valores, np.linspace(0.0, 1.0, n + 1))
    return [float(c) for c in cortes]


def intervalo_igual(valores: np.ndarray, n: int) -> list[float]:
    """Cortes de intervalo igual: idênticos a `numpy.linspace(minimo, maximo, n + 1)`."""
    _validar_n(valores, n)
    minimo, maximo = float(np.min(valores)), float(np.max(valores))
    cortes = np.linspace(minimo, maximo, n + 1)
    return [float(c) for c in cortes]


def desvio_padrao(valores: np.ndarray, fracao: float) -> list[float]:
    """Cortes centrados na média, largura de classe = `fracao` × desvio padrão (populacional,
    ddof=0). `fracao` em {1, 1/2, 1/3, 1/4} (ADR do item; outro valor é erro do chamador, não do
    método). Os cortes cobrem de mín a máx: acrescenta uma classe aberta de cada ponta quando a
    grade não cobre os extremos, do jeito que a Esri documenta (classes centradas na média)."""
    if fracao not in FRACOES_DESVIO_PADRAO:
        raise ErroClassificacao("fracao_invalida", f"fração de desvio padrão inválida: {fracao!r}")
    if valores.size == 0:
        raise ErroClassificacao("sem_dados", "campo sem nenhum valor numérico não nulo")
    media = float(np.mean(valores))
    desvio = float(np.std(valores, ddof=0))
    minimo, maximo = float(np.min(valores)), float(np.max(valores))
    if desvio == 0.0:
        return [minimo, maximo]
    passo = fracao * desvio
    cortes_acima = [media]
    while cortes_acima[-1] < maximo:
        cortes_acima.append(cortes_acima[-1] + passo)
    cortes_abaixo = [media]
    while cortes_abaixo[-1] > minimo:
        cortes_abaixo.append(cortes_abaixo[-1] - passo)
    cortes = sorted(set(cortes_abaixo) | set(cortes_acima))
    cortes[0] = min(cortes[0], minimo)
    cortes[-1] = max(cortes[-1], maximo)
    return [float(c) for c in cortes]


def manual(valores: np.ndarray, cortes: list[float]) -> list[float]:
    """Cortes informados pelo usuário: só valida (estritamente crescentes, cobrindo os dados) e
    devolve — a rota usa isso para montar o histograma por classe."""
    if len(cortes) < 2:
        raise ErroClassificacao("cortes_insuficientes", "cortes manuais exigem ao menos 2 valores")
    ordenado = sorted(float(c) for c in cortes)
    if ordenado != [float(c) for c in cortes]:
        raise ErroClassificacao("cortes_nao_crescentes", "cortes manuais precisam estar em ordem crescente")
    if len(set(ordenado)) != len(ordenado):
        raise ErroClassificacao("cortes_repetidos", "cortes manuais não podem repetir valor")
    return ordenado


@dataclass
class ResultadoUnicos:
    valores: list[dict]
    total_distintos: int
    truncado: bool


def valores_unicos(coluna: list, limite: int = LIMITE_VALORES_UNICOS) -> ResultadoUnicos:
    """Para campo categórico: [{"valor", "contagem"}] ordenado por contagem decrescente, truncado em
    `limite` com uma linha extra 'outros' somando o resto (cláusula do portão: 5.000 distintos ->
    200 + total)."""
    contagem: dict = {}
    for v in coluna:
        contagem[v] = contagem.get(v, 0) + 1
    itens = sorted(contagem.items(), key=lambda kv: (-kv[1], str(kv[0])))
    total_distintos = len(itens)
    truncado = total_distintos > limite
    if not truncado:
        saida = [{"valor": v, "contagem": c} for v, c in itens]
        return ResultadoUnicos(saida, total_distintos, False)
    principais = itens[:limite]
    resto = itens[limite:]
    saida = [{"valor": v, "contagem": c} for v, c in principais]
    saida.append({"valor": "outros", "contagem": sum(c for _, c in resto), "distintos_agrupados": len(resto)})
    return ResultadoUnicos(saida, total_distintos, True)


# ---------------------------------------------------------------------------
# Quebras naturais (Jenks / Fisher 1958)
# ---------------------------------------------------------------------------

def _pontos_ponderados(valores: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    """(posicoes, pesos, agregado) — reduz a coluna a um vetor ponderado sem descartar nenhum
    valor: primeiro por valor distinto exato (`numpy.unique`); se ainda passar do teto de posições,
    reagrupa num histograma de largura igual com esse teto (ainda soma de tudo, não amostra)."""
    posicoes, pesos = np.unique(valores, return_counts=True)
    if posicoes.size <= TETO_POSICOES_JENKS:
        return posicoes.astype(float), pesos.astype(float), False
    contagens, bordas = np.histogram(valores, bins=TETO_POSICOES_JENKS)
    centros = (bordas[:-1] + bordas[1:]) / 2.0
    mask = contagens > 0
    return centros[mask], contagens[mask].astype(float), True


def _jenks_dp(posicoes: np.ndarray, pesos: np.ndarray, k: int) -> np.ndarray:
    """Programação dinâmica exata de variância mínima dentro do grupo sobre pontos PONDERADOS
    (Fisher 1958). `posicoes` estritamente crescente, `pesos` > 0, mesmo tamanho. Devolve os
    ÍNDICES (em `posicoes`) do primeiro elemento de cada uma das k classes (índice 0 sempre é o
    primeiro). custo(i, j) em O(1) com somas de prefixo; a busca do melhor `i` para cada `j` é
    vetorizada em numpy (o laço puro em Python sobre m² pontos não cabia no orçamento de tempo)."""
    m = posicoes.size
    if k >= m:
        return np.arange(m)
    w = pesos
    s1 = np.concatenate(([0.0], np.cumsum(w * posicoes)))
    s2 = np.concatenate(([0.0], np.cumsum(w * posicoes * posicoes)))
    sw = np.concatenate(([0.0], np.cumsum(w)))

    def custo_vetor(i_arr: np.ndarray, j: int) -> np.ndarray:
        # soma dos quadrados dos desvios ponderados de [i, j] (0-based, inclusive), i variando
        peso = sw[j + 1] - sw[i_arr]
        soma = s1[j + 1] - s1[i_arr]
        soma2 = s2[j + 1] - s2[i_arr]
        with np.errstate(invalid="ignore", divide="ignore"):
            v = soma2 - np.where(peso > 0, (soma * soma) / np.where(peso > 0, peso, 1.0), 0.0)
        return v

    INF = float("inf")
    D_prev = np.array([custo_vetor(np.array([0]), j)[0] for j in range(m)])
    P = np.zeros((k, m), dtype=np.int64)
    P[0, :] = 0
    for c in range(1, k):
        D_atual = np.full(m, INF)
        for j in range(c, m):
            i_arr = np.arange(c, j + 1)
            total = D_prev[i_arr - 1] + custo_vetor(i_arr, j)
            pos = int(np.argmin(total))
            D_atual[j] = total[pos]
            P[c, j] = i_arr[pos]
        D_prev = D_atual
    cortes_idx = [0] * k
    j = m - 1
    for c in range(k - 1, -1, -1):
        i = int(P[c, j])
        cortes_idx[c] = i
        j = i - 1
    return np.array(cortes_idx)


def quebras_naturais(valores: np.ndarray, n: int) -> tuple[list[float], bool]:
    """(cortes, agregado). `agregado=True` quando os valores distintos passaram do teto de posições
    e a Jenks correu sobre um histograma (ainda soma de tudo — ver docstring do módulo)."""
    _validar_n(valores, n)
    posicoes, pesos, agregado = _pontos_ponderados(valores)
    if posicoes.size == 1:
        v = float(posicoes[0])
        return [v] * (n + 1), agregado
    k = min(n, posicoes.size)
    idx_inicio = _jenks_dp(posicoes, pesos, k)
    # convenção (confere com implementação de referência independente): o corte entre a classe
    # c-1 e a classe c é o ÚLTIMO valor da classe c-1 (posicoes[idx_inicio[c] - 1]), não o
    # primeiro da classe c — os dois são valores DISTINTOS do dado, e só o primeiro bate com uma
    # referência externa (jenkspy, ver docs/adr do item).
    cortes = [float(posicoes[0])]
    for i in idx_inicio[1:]:
        cortes.append(float(posicoes[i - 1]))
    cortes.append(float(posicoes[-1]))
    if k < n:
        # menos valores distintos que classes pedidas: repete o último corte (classe vazia
        # explícita, nunca inventa um valor que não existe no dado)
        cortes = cortes + [cortes[-1]] * (n - k)
    cortes[0] = float(np.min(valores))
    cortes[-1] = float(np.max(valores))
    return cortes, agregado
