"""Estatística espacial em numpy/scipy, sem banco e sem estado (item L2-05-d): pesos por distância fixa,
Getis-Ord Gi*, I de Moran global, vizinho mais próximo médio, centro médio/distância padrão/elipse de desvio
padrão, densidade de kernel e interpolação por inverso da distância (IDW).

Por que implementação própria e não uma biblioteca de análise espacial: a plataforma já carrega numpy e scipy
(rasterio depende dos dois) e as fórmulas abaixo são fechadas e curtas; trazer `esda`/`libpysal` para produção
custaria dependência nova para reproduzir o que cabe em uma tela. As fórmulas seguem as fontes declaradas no
item (Getis & Ord 1992; Moran 1950; Clark & Evans 1954; ArcGIS Pro, "How Kernel Density works" e "How Directional
Distribution works"), e o teste do item confere cada uma contra `esda` 2.10/`libpysal` 4.15, que estão no
ambiente de teste, ou contra a fórmula escrita à parte.

Convenção: `xy` é um array (n, 2) de coordenadas em METROS (projeção métrica local; quem projeta é quem chama),
`valores` é (n,) float. Nada aqui conhece SRID, item de catálogo ou inquilino.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.special import erfc

FUNCOES_KERNEL = ("quartica", "gaussiana", "triangular", "uniforme")
FUNCOES_VIZINHANCA = ("distancia_fixa",)


class ErroEstatistica(ValueError):
    """Entrada insuficiente para a estatística pedida (a rota transforma em 422 nomeado)."""


def _xy(xy) -> np.ndarray:
    a = np.asarray(xy, dtype=float)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ErroEstatistica("coordenadas devem vir como array (n, 2)")
    if not np.isfinite(a).all():
        raise ErroEstatistica("coordenada não finita na entrada")
    return a


def p_bilateral(z: np.ndarray) -> np.ndarray:
    """p bilateral da normal padrão: erfc(|z|/raiz(2)). Sem scipy.stats (erfc já vem em scipy.special)."""
    return erfc(np.abs(np.asarray(z, dtype=float)) / math.sqrt(2.0))


# ---------------------------------------------------------------- pesos
def pesos_distancia_fixa(xy, raio: float, incluir_proprio: bool = True) -> sparse.csr_matrix:
    """Matriz binária n×n: 1 quando a distância euclidiana é <= raio. `incluir_proprio` liga a diagonal, que é o
    que separa Gi* (com o próprio ponto) de Gi (sem). Usa árvore k-d: a matriz nunca é materializada densa."""
    a = _xy(xy)
    if raio <= 0:
        raise ErroEstatistica("raio da vizinhança deve ser maior que zero")
    arvore = cKDTree(a)
    w = arvore.sparse_distance_matrix(arvore, raio, output_type="coo_matrix")
    n = a.shape[0]
    linhas, colunas = w.row, w.col
    if incluir_proprio:
        linhas = np.concatenate([linhas, np.arange(n)])
        colunas = np.concatenate([colunas, np.arange(n)])
    else:
        manter = linhas != colunas
        linhas, colunas = linhas[manter], colunas[manter]
    m = sparse.csr_matrix((np.ones(linhas.size), (linhas, colunas)), shape=(n, n))
    m.data[:] = 1.0  # distância zero vira aresta de peso 1, e par repetido não vira 2
    return m


# ---------------------------------------------------------------- Getis-Ord Gi*
def gi_estrela(valores, xy, raio: float) -> dict:
    """Getis & Ord (1992), forma padronizada com pesos binários:

        Gi* = (soma_j w_ij x_j - X media * soma_j w_ij) /
              (S * raiz( (n * soma_j w_ij^2 - (soma_j w_ij)^2) / (n - 1) ))

    com S = raiz(soma x^2 / n - X media^2) e a diagonal ligada (o próprio ponto entra na vizinhança).
    Devolve z (o próprio Gi*, que já é escore padronizado), p bilateral e o número de vizinhos.
    Desvio padrão zero (todos os valores iguais) não é erro: z e p saem NaN e a ferramenta diz por quê."""
    x = np.asarray(valores, dtype=float)
    a = _xy(xy)
    n = x.size
    if n != a.shape[0]:
        raise ErroEstatistica("valores e coordenadas com tamanhos diferentes")
    if n < 2:
        raise ErroEstatistica("Gi* exige pelo menos duas feições")
    if not np.isfinite(x).all():
        raise ErroEstatistica("valor não finito na entrada")
    w = pesos_distancia_fixa(a, raio, incluir_proprio=True)
    soma_w = np.asarray(w.sum(axis=1)).ravel()
    soma_w2 = np.asarray(w.multiply(w).sum(axis=1)).ravel()  # pesos binários: soma w^2 = soma w
    soma_wx = w @ x
    media = x.mean()
    s = math.sqrt(max(0.0, (x * x).sum() / n - media * media))
    numerador = soma_wx - media * soma_w
    with np.errstate(invalid="ignore", divide="ignore"):
        denominador = s * np.sqrt((n * soma_w2 - soma_w ** 2) / (n - 1))
        z = np.where(denominador > 0, numerador / np.where(denominador > 0, denominador, 1.0), np.nan)
    return {"z": z, "p": p_bilateral(z), "vizinhos": soma_w.astype(int), "soma_local": soma_wx,
            "media": media, "desvio": s, "n": n}


# ---------------------------------------------------------------- I de Moran global
def moran_global(valores, xy, raio: float) -> dict:
    """I de Moran (1950) com pesos binários por distância fixa, SEM o próprio ponto, e o teste de significância
    sob a hipótese de normalidade (a mesma que `esda.Moran(..., permutations=0)` reporta em z_norm)."""
    x = np.asarray(valores, dtype=float)
    a = _xy(xy)
    n = x.size
    if n != a.shape[0]:
        raise ErroEstatistica("valores e coordenadas com tamanhos diferentes")
    if n < 3:
        raise ErroEstatistica("I de Moran exige pelo menos três feições")
    w = pesos_distancia_fixa(a, raio, incluir_proprio=False)
    s0 = float(w.sum())
    if s0 <= 0:
        raise ErroEstatistica("nenhum par dentro do raio: aumente a distância da vizinhança")
    d = x - x.mean()
    numerador = float(d @ (w @ d))
    i = (n / s0) * (numerador / float(d @ d))
    esperado = -1.0 / (n - 1)
    wt = w.T
    s1 = 0.5 * float((w + wt).multiply(w + wt).sum())
    linhas = np.asarray(w.sum(axis=1)).ravel()
    colunas = np.asarray(w.sum(axis=0)).ravel()
    s2 = float(((linhas + colunas) ** 2).sum())
    variancia = (n * n * s1 - n * s2 + 3 * s0 * s0) / ((s0 * s0) * (n * n - 1)) - esperado ** 2
    z = (i - esperado) / math.sqrt(variancia) if variancia > 0 else float("nan")
    return {"i": i, "esperado": esperado, "variancia": variancia, "z": z, "p": float(p_bilateral(z)),
            "s0": s0, "s1": s1, "s2": s2, "n": n}


# ---------------------------------------------------------------- vizinho mais próximo médio
def vizinho_mais_proximo_medio(xy, area: float) -> dict:
    """Índice R de Clark & Evans (1954): razão entre a distância média ao vizinho mais próximo observada e a
    esperada num processo aleatório de mesma densidade (0,5/raiz(n/A)); z pela aproximação normal com erro
    padrão 0,26136/raiz(n^2/A)."""
    a = _xy(xy)
    n = a.shape[0]
    if n < 2:
        raise ErroEstatistica("vizinho mais próximo médio exige pelo menos duas feições")
    if area <= 0:
        raise ErroEstatistica("área de referência deve ser maior que zero")
    distancias, _ = cKDTree(a).query(a, k=2)
    observada = float(distancias[:, 1].mean())
    esperada = 0.5 / math.sqrt(n / area)
    erro = 0.26136 / math.sqrt(n * n / area)
    z = (observada - esperada) / erro
    return {"observada": observada, "esperada": esperada, "razao": observada / esperada, "z": z,
            "p": float(p_bilateral(z)), "n": n, "area": float(area)}


# ---------------------------------------------------------------- centro médio, distância padrão, elipse
def centro_medio(xy, pesos=None) -> dict:
    a = _xy(xy)
    p = np.ones(a.shape[0]) if pesos is None else np.asarray(pesos, dtype=float)
    if p.size != a.shape[0]:
        raise ErroEstatistica("pesos e coordenadas com tamanhos diferentes")
    if (p < 0).any() or p.sum() <= 0:
        raise ErroEstatistica("peso negativo ou soma de pesos nula")
    c = (a * p[:, None]).sum(axis=0) / p.sum()
    dx, dy = a[:, 0] - c[0], a[:, 1] - c[1]
    padrao = math.sqrt(float((p * (dx * dx + dy * dy)).sum() / p.sum()))
    return {"x": float(c[0]), "y": float(c[1]), "distancia_padrao": padrao, "n": int(a.shape[0]),
            "peso_total": float(p.sum())}


def elipse_desvio_padrao(xy, desvios: float = 1.0, pesos=None) -> dict:
    """Elipse de distribuição direcional (ArcGIS "Directional Distribution"): eixos = desvio padrão ao longo das
    direções principais, multiplicados por `desvios`; o ângulo é medido no sentido horário a partir do Norte."""
    a = _xy(xy)
    n = a.shape[0]
    if n < 3:
        raise ErroEstatistica("a elipse exige pelo menos três feições")
    p = np.ones(n) if pesos is None else np.asarray(pesos, dtype=float)
    c = centro_medio(a, p)
    dx, dy = a[:, 0] - c["x"], a[:, 1] - c["y"]
    sw = p.sum()
    sxx = float((p * dx * dx).sum())
    syy = float((p * dy * dy).sum())
    sxy = float((p * dx * dy).sum())
    if sxy == 0.0:
        theta = 0.0 if sxx >= syy else math.pi / 2
    else:
        termo = math.sqrt((sxx - syy) ** 2 + 4 * sxy * sxy)
        theta = math.atan2(sxx - syy + termo, 2 * sxy)
    cos, sen = math.cos(theta), math.sin(theta)
    sigma_x = math.sqrt(2.0 * float((p * (dx * cos + dy * sen) ** 2).sum()) / sw) / math.sqrt(2.0)
    sigma_y = math.sqrt(2.0 * float((p * (dy * cos - dx * sen) ** 2).sum()) / sw) / math.sqrt(2.0)
    azimute = (90.0 - math.degrees(theta)) % 180.0
    return {"x": c["x"], "y": c["y"], "eixo_maior": max(sigma_x, sigma_y) * desvios,
            "eixo_menor": min(sigma_x, sigma_y) * desvios, "rotacao_graus": azimute if sigma_x >= sigma_y
            else (azimute + 90.0) % 180.0, "desvios": float(desvios), "n": n}


def pontos_da_elipse(elipse: dict, vertices: int = 72) -> np.ndarray:
    """Contorno da elipse como (vertices+1, 2), fechado — o desenho que vira a feição de saída."""
    t = np.linspace(0.0, 2 * math.pi, int(vertices) + 1)
    ang = math.radians(90.0 - elipse["rotacao_graus"])
    x = elipse["eixo_maior"] * np.cos(t)
    y = elipse["eixo_menor"] * np.sin(t)
    return np.column_stack([elipse["x"] + x * math.cos(ang) - y * math.sin(ang),
                            elipse["y"] + x * math.sin(ang) + y * math.cos(ang)])


# ---------------------------------------------------------------- densidade de kernel
def _kernel(u: np.ndarray, funcao: str) -> np.ndarray:
    """Núcleo já normalizado em DUAS dimensões: a integral sobre o plano vale 1 quando multiplicada por 1/r^2.
    `u` é a distância dividida pelo raio."""
    if funcao == "quartica":  # Silverman (1986) 4.5, o mesmo do Kernel Density do ArcGIS
        return np.where(u < 1, 3.0 / math.pi * (1.0 - u * u) ** 2, 0.0)
    if funcao == "gaussiana":  # truncada no raio; a massa fora do raio é desprezada (documentado no método)
        return np.where(u < 1, np.exp(-0.5 * (3.0 * u) ** 2) * (9.0 / (2.0 * math.pi)), 0.0)
    if funcao == "triangular":
        return np.where(u < 1, 3.0 / math.pi * (1.0 - u), 0.0)
    if funcao == "uniforme":
        return np.where(u < 1, 1.0 / math.pi, 0.0)
    raise ErroEstatistica(f"função de kernel desconhecida: {funcao!r}")


def densidade_kernel(xy, grade_x, grade_y, raio: float, funcao: str = "quartica", pesos=None) -> np.ndarray:
    """Densidade por unidade de área nos centros de célula dados por `grade_x`/`grade_y` (vetores 1-D em metros).
    Devolve array (len(grade_y), len(grade_x)), linha 0 = primeiro y. A soma do array vezes a área da célula
    devolve o número de pontos (ou a soma dos pesos) quando o raio cabe dentro da grade — é o que o portão do
    item mede com tolerância de 1 %."""
    a = _xy(xy)
    if raio <= 0:
        raise ErroEstatistica("raio do kernel deve ser maior que zero")
    p = np.ones(a.shape[0]) if pesos is None else np.asarray(pesos, dtype=float)
    if p.size != a.shape[0]:
        raise ErroEstatistica("pesos e coordenadas com tamanhos diferentes")
    gx = np.asarray(grade_x, dtype=float)
    gy = np.asarray(grade_y, dtype=float)
    saida = np.zeros((gy.size, gx.size), dtype=float)
    if a.shape[0] == 0:
        return saida
    # varre ponto a ponto, mas só na janela de células que o raio alcança: custo O(n * (raio/celula)^2)
    for (px, py), peso in zip(a, p, strict=True):
        i0, i1 = np.searchsorted(gx, [px - raio, px + raio])
        j0, j1 = np.searchsorted(gy, [py - raio, py + raio])
        if i0 >= i1 or j0 >= j1:
            continue
        dx = (gx[i0:i1] - px) / raio
        dy = (gy[j0:j1] - py) / raio
        u = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
        saida[j0:j1, i0:i1] += peso * _kernel(u, funcao) / (raio * raio)
    return saida


def amostrar_linhas(coordenadas: list, passo: float) -> tuple[np.ndarray, np.ndarray]:
    """Quebra cada linha (lista de (x, y) em metros) em pontos a cada `passo` metros e devolve (xy, pesos), com
    o peso de cada ponto igual ao comprimento que ele representa. Com isso a densidade de linhas é a mesma conta
    da densidade de pontos, e a soma do raster vezes a área da célula devolve o COMPRIMENTO total."""
    if passo <= 0:
        raise ErroEstatistica("passo de amostragem deve ser maior que zero")
    pontos, pesos = [], []
    for linha in coordenadas:
        c = np.asarray(linha, dtype=float)
        if c.ndim != 2 or c.shape[0] < 2:
            continue
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        for (x0, y0), (x1, y1), comprimento in zip(c[:-1], c[1:], seg, strict=True):
            if comprimento <= 0:
                continue
            n = max(1, int(math.ceil(comprimento / passo)))
            t = (np.arange(n) + 0.5) / n
            pontos.append(np.column_stack([x0 + t * (x1 - x0), y0 + t * (y1 - y0)]))
            pesos.append(np.full(n, comprimento / n))
    if not pontos:
        return np.zeros((0, 2)), np.zeros(0)
    return np.vstack(pontos), np.concatenate(pesos)


# ---------------------------------------------------------------- IDW
def idw(xy, valores, alvos, potencia: float = 2.0, vizinhos: int = 12, raio: float | None = None) -> np.ndarray:
    """Inverso da distância (Shepard 1968) com os `vizinhos` mais próximos, ou todos dentro de `raio` quando ele
    é dado. Alvo que cai EXATAMENTE sobre uma amostra recebe o valor da amostra — é o que o portão do item mede
    ("IDW em 100 pontos reproduz exatamente os valores nos pontos amostrados")."""
    a = _xy(xy)
    v = np.asarray(valores, dtype=float)
    alvo = _xy(alvos)
    if v.size != a.shape[0]:
        raise ErroEstatistica("valores e coordenadas com tamanhos diferentes")
    if a.shape[0] == 0:
        raise ErroEstatistica("IDW exige pelo menos uma amostra")
    if potencia <= 0:
        raise ErroEstatistica("potência do IDW deve ser maior que zero")
    k = int(min(max(1, vizinhos), a.shape[0]))
    arvore = cKDTree(a)
    d, idx = arvore.query(alvo, k=k, distance_upper_bound=np.inf if raio is None else float(raio))
    if k == 1:
        d, idx = d[:, None], idx[:, None]
    valido = np.isfinite(d) & (idx < a.shape[0])
    d = np.where(valido, d, np.inf)
    idx = np.where(valido, idx, 0)
    saida = np.full(alvo.shape[0], np.nan)
    exato = d[:, 0] == 0.0
    saida[exato] = v[idx[exato, 0]]
    resto = ~exato & valido.any(axis=1)
    if resto.any():
        w = np.where(valido[resto], 1.0 / np.power(d[resto], potencia), 0.0)
        saida[resto] = (w * v[idx[resto]]).sum(axis=1) / w.sum(axis=1)
    return saida
