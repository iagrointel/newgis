"""Biblioteca declarativa de transformações valor bruto → favorabilidade 0-100 (item L3-01-d).

Cada transformação é um JSON (esquema `docs/esquemas/amc_modelo.v1.json#/$defs/transformacao`, campo
`tipo` + parâmetros) com DUAS implementações que precisam bater: esta, em numpy (pré-visualização no
navegador de dados e recomputação independente), e a equivalente em SQL/PL-pgSQL
(`plat.amc_transformar`, migração `db/migracoes/20260907T1600_amc_transformacoes.sql`), usada para
MATERIALIZAR a favorabilidade de milhões de linhas sem trazer nada para o Python.

Tipos suportados (16): `categoria` (Unique Categories), `faixas` (Range of Classes, com quebra manual
ou por quantil/intervalo igual/quebras naturais), `linear` (mínimo/máximo/direção), `degraus` (bandas
do motor logístico de referência da casa) e as 12 funções contínuas do Rescale by Function do ArcGIS Pro 3.4:
`exponencial`, `gaussiana`, `grande` (Large), `logaritmo`, `decaimento_logistico` (Logistic Decay),
`crescimento_logistico` (Logistic Growth), `ms_grande` (MSLarge), `ms_pequena` (MSSmall), `proxima`
(Near), `potencia` (Power), `pequena` (Small), `linear_simetrica` (Symmetric Linear).

⚠ FÓRMULA DECLARADA, não engenharia reversa: a documentação da Esri para o Rescale by Function
(doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/the-transformation-functions-
available-for-rescale-by-function.html, testada em 07/09/2026) descreve o PROPÓSITO e os NOMES dos
parâmetros de cada função (ex.: Gaussian tem Midpoint/Spread; MSLarge tem Mean multiplier/Std
multiplier) mas não publica a fórmula fechada — é comportamento de produto fechado, não uma conta
aberta. Este módulo DECLARA uma fórmula concreta para cada nome de função, com os MESMOS parâmetros
e o MESMO efeito qualitativo descrito pela Esri (ex.: "quanto maior o spread, mais estreita a curva"),
e documenta a escolha — nunca afirma reproduzir byte a byte o produto da Esri. Constância com a regra
da casa: "transformação é escolha declarada do usuário, nunca calibrada por nós" (ver prompt do item).

Convenções comuns a todas as funções contínuas e à `linear`:
- `minimo`/`maximo` (ou `midpoint`/`spread` conforme o tipo) definem o domínio de entrada;
- `abaixo`/`acima`: nota fixa para valor fora do domínio declarado (abaixo do mínimo/acima do máximo);
  ausente = usa o valor de borda da própria curva (comportamento contínuo, sem degrau na fronteira);
- `saida_min`/`saida_max` (opcionais, padrão 0/100): remapeamento AFIM da saída da curva — extensão
  aditiva deste item (o esquema não lista os campos mas não fecha `additionalProperties` no objeto
  `transformacao`, então isto não quebra nenhum modelo já gravado). Sem eles a curva sai em 0-100 como
  seria de esperar; com eles, uma rampa "y vai de 100 a 10", como o fator `rod` do motor logístico,
  fica representável sem inventar um tipo novo;
- NULL (Python `None`/`nan`) permanece NULL: nunca vira 0 nem qualquer outra nota.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------------------- categorias
FUNCOES_CONTINUAS = ("exponencial", "gaussiana", "grande", "logaritmo", "decaimento_logistico",
                     "crescimento_logistico", "ms_grande", "ms_pequena", "proxima", "potencia",
                     "pequena", "linear_simetrica")
TIPOS_VALIDOS = ("categoria", "faixas", "linear", "degraus") + FUNCOES_CONTINUAS


class ErroTransformacao(Exception):
    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _num(x) -> float:
    return float(x)


def _saida(frac_0_1: np.ndarray, t: dict) -> np.ndarray:
    """Remapeamento afim opcional da saída (extensão `saida_min`/`saida_max`, padrão 0/100), aplicado
    depois de qualquer curva já ter normalizado sua fração em [0, 1]."""
    smin = _num(t.get("saida_min", 0.0))
    smax = _num(t.get("saida_max", 100.0))
    return smin + frac_0_1 * (smax - smin)


def _abaixo_acima(valores: np.ndarray, frac: np.ndarray, saida: np.ndarray, t: dict,
                   direcao_decrescente: bool) -> np.ndarray:
    """Aplica `abaixo`/`acima` aos pontos fora de [0, 1] em `frac` (fração do valor BRUTO dentro de
    [minimo, maximo], sempre calculada na mesma orientação — `abaixo` é sempre "valor < minimo" e
    `acima` sempre "valor > maximo", independente da `direcao` da curva, que só decide se a nota SOBE
    ou DESCE entre as duas pontas, não qual ponta é qual)."""
    fora_baixo = frac < 0.0
    fora_cima = frac > 1.0
    abaixo = t.get("abaixo")
    acima = t.get("acima")
    if abaixo is not None:
        saida = np.where(fora_baixo, float(abaixo), saida)
    if acima is not None:
        saida = np.where(fora_cima, float(acima), saida)
    return saida


# ------------------------------------------------------------------------------------------ categoria
def _t_categoria(valores, t: dict) -> np.ndarray:
    notas = t.get("notas") or {}
    outros = t.get("outros")
    saida = np.full(len(valores), np.nan, dtype=float)
    for i, v in enumerate(valores):
        if v is None:
            continue
        chave = str(v)
        if chave in notas:
            saida[i] = float(notas[chave])
        elif outros is not None:
            saida[i] = float(outros)
        # nem em `notas` nem `outros`: fica NULL — modelo incompleto, nunca inventa nota
    return saida


# --------------------------------------------------------------------------------------------- faixas
def resolver_quebras(valores: np.ndarray, t: dict) -> dict:
    """Resolve `metodo` (quantil/intervalo_igual/quebras_naturais) em `quebras` EXPLÍCITAS, a partir da
    amostra — sempre que `metodo != 'manual'` (padrão). A transformação devolvida já tem `quebras`
    concretas e `metodo: 'manual'`: é ESSA versão, congelada, que vai para o SQL (que só sabe aplicar
    quebra explícita — não teria como recalcular quantil sem trazer a coluna inteira para dentro da
    função escalar). Chamar de novo com outra amostra dá quebras diferentes; por isso o resultado
    materializado grava a versão resolvida, não a original com `metodo`."""
    if t.get("tipo") != "faixas":
        return t
    metodo = t.get("metodo", "manual")
    if metodo == "manual":
        return t
    limpos = np.asarray([v for v in valores if v is not None and not (isinstance(v, float) and math.isnan(v))],
                        dtype=float)
    n_faixas = len(t["notas"])
    n_quebras = n_faixas - 1
    if limpos.size == 0:
        raise ErroTransformacao(f"faixas método {metodo!r}: amostra vazia, não há como derivar quebras")
    if metodo == "quantil":
        qs = np.linspace(0.0, 1.0, n_quebras + 2)[1:-1]
        quebras = sorted(set(float(x) for x in np.quantile(limpos, qs)))
    elif metodo == "intervalo_igual":
        lo, hi = float(limpos.min()), float(limpos.max())
        quebras = [lo + (hi - lo) * i / (n_quebras + 1) for i in range(1, n_quebras + 1)]
    elif metodo == "quebras_naturais":
        quebras = _quebras_naturais_jenks(limpos, n_quebras)
    else:
        raise ErroTransformacao(f"método de faixas desconhecido: {metodo!r}")
    novo = dict(t)
    novo["quebras"] = quebras
    novo["metodo"] = "manual"
    return novo


def _quebras_naturais_jenks(valores: np.ndarray, n_quebras: int) -> list[float]:
    """Jenks natural breaks, implementação direta (programação dinâmica O(n²·k), aceitável para a
    amostra de pré-visualização — nunca roda sobre a tabela inteira, só sobre o array já em memória)."""
    dados = np.sort(np.unique(valores))
    k = n_quebras + 1
    n = len(dados)
    if n <= k:
        return list(dados[1:].astype(float))
    # soma de quadrados dos desvios à média, por classe [i..j]
    prefixo = np.concatenate([[0.0], np.cumsum(dados)])
    prefixo2 = np.concatenate([[0.0], np.cumsum(dados ** 2)])

    def variancia(i, j):  # custo da classe dados[i:j] (0-indexado, j exclusivo)
        s = prefixo[j] - prefixo[i]
        s2 = prefixo2[j] - prefixo2[i]
        m = j - i
        return s2 - (s * s) / m if m > 0 else 0.0

    INF = float("inf")
    custo = [[INF] * (k + 1) for _ in range(n + 1)]
    corte = [[0] * (k + 1) for _ in range(n + 1)]
    custo[0][0] = 0.0
    for j in range(1, n + 1):
        for c in range(1, k + 1):
            melhor, melhor_i = INF, 0
            for i in range(c - 1, j):
                if custo[i][c - 1] == INF:
                    continue
                v = custo[i][c - 1] + variancia(i, j)
                if v < melhor:
                    melhor, melhor_i = v, i
            custo[j][c] = melhor
            corte[j][c] = melhor_i
    cortes_idx = []
    j, c = n, k
    while c > 1:
        i = corte[j][c]
        cortes_idx.append(i)
        j, c = i, c - 1
    cortes_idx = sorted(cortes_idx)
    return [float(dados[i]) for i in cortes_idx]


def _t_faixas(valores, t: dict) -> np.ndarray:
    """Convenção de fronteira (única, para as quebras MANUAIS): valor <= quebras[0] → notas[0];
    quebras[i-1] < valor <= quebras[i] → notas[i]; valor > quebras[-1] → notas[-1]. Quebra por
    quantil/intervalo_igual/quebras_naturais precisa ser resolvida ANTES (`resolver_quebras`)."""
    t = resolver_quebras([v for v in valores if v is not None], t) if t.get("metodo", "manual") != "manual" else t
    quebras = [float(q) for q in t["quebras"]]
    notas = [float(n) for n in t["notas"]]
    saida = np.full(len(valores), np.nan, dtype=float)
    for i, v in enumerate(valores):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        v = float(v)
        idx = 0
        while idx < len(quebras) and v > quebras[idx]:
            idx += 1
        saida[i] = notas[idx]
    return saida


# --------------------------------------------------------------------------------------------- linear
def _t_linear(valores, t: dict) -> np.ndarray:
    minimo, maximo = _num(t["minimo"]), _num(t["maximo"])
    decrescente = t.get("direcao", "crescente") == "decrescente"
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    if maximo == minimo:
        saida = np.full_like(valores, _saida(np.array([0.5]), t)[0])
        return np.where(np.isnan(valores), np.nan, saida)
    frac = (valores - minimo) / (maximo - minimo)
    frac_curva = 1.0 - frac if decrescente else frac
    saida = _saida(np.clip(frac_curva, 0.0, 1.0), t)
    saida = _abaixo_acima(valores, frac, saida, t, decrescente)
    return np.where(np.isnan(valores), np.nan, saida)


def _t_linear_simetrica(valores, t: dict) -> np.ndarray:
    """Symmetric Linear: pico (favorabilidade máxima) no ponto médio de [minimo, maximo], caindo
    linearmente para 0 nas duas pontas — mesmos parâmetros Minimo/Maximo da Linear (documentado pela
    Esri como "mirrored around the midpoint")."""
    minimo, maximo = _num(t["minimo"]), _num(t["maximo"])
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    meio = (minimo + maximo) / 2.0
    metade = (maximo - minimo) / 2.0
    if metade == 0:
        saida = np.where(valores == meio, _saida(np.array([1.0]), t)[0], np.nan)
        return saida
    dist = np.abs(valores - meio) / metade
    frac_curva = np.clip(1.0 - dist, 0.0, 1.0)
    saida = _saida(frac_curva, t)
    fora = dist > 1.0
    abaixo, acima = t.get("abaixo"), t.get("acima")
    nota_fora = abaixo if abaixo is not None else acima
    if nota_fora is not None:
        saida = np.where(fora, float(nota_fora), saida)
    return np.where(np.isnan(valores), np.nan, saida)


# -------------------------------------------------------------------------------------------- degraus
def _t_degraus(valores, t: dict) -> np.ndarray:
    """valor <= bandas[0].ate → bandas[0].nota; bandas[i-1].ate < valor <= bandas[i].ate →
    bandas[i].nota; valor > última bandas[].ate → `acima` (None se ausente: fica NULL, não inventa)."""
    bandas = sorted(t["bandas"], key=lambda b: float(b["ate"]))
    ates = [float(b["ate"]) for b in bandas]
    notas = [float(b["nota"]) for b in bandas]
    acima = t.get("acima")
    saida = np.full(len(valores), np.nan, dtype=float)
    for i, v in enumerate(valores):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        v = float(v)
        idx = 0
        while idx < len(ates) and v > ates[idx]:
            idx += 1
        if idx < len(ates):
            saida[i] = notas[idx]
        elif acima is not None:
            saida[i] = float(acima)
    return saida


# ----------------------------------------------------------------------- funções contínuas (declaradas)
def _dominio(t: dict) -> tuple[float, float]:
    return _num(t["minimo"]), _num(t["maximo"])


def _t_potencia(valores, t: dict) -> np.ndarray:
    """Power: y = ((x − deslocamento − minimo) / (maximo − minimo))^expoente, escala 0-1 antes do
    remapeamento de saída. `deslocamento` (Shift) desloca a origem antes de normalizar; `expoente`
    (Exponent) — maior expoente concentra a favorabilidade perto do máximo (comportamento descrito pela
    Esri: "as preferências aumentam rapidamente perto dos maiores valores")."""
    minimo, maximo = _dominio(t)
    deslocamento = _num(t.get("deslocamento", 0.0))
    expoente = _num(t.get("expoente", 1.0))
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    frac = (valores - deslocamento - minimo) / (maximo - minimo) if maximo != minimo else np.zeros_like(valores)
    frac_clip = np.clip(frac, 0.0, 1.0)
    curva = np.power(frac_clip, expoente) if expoente >= 0 else np.power(np.where(frac_clip == 0, 1e-12, frac_clip),
                                                                          expoente)
    saida = _saida(curva, t)
    saida = _abaixo_acima(valores, frac, saida, t, False)
    return np.where(np.isnan(valores), np.nan, saida)


def _t_logaritmo(valores, t: dict) -> np.ndarray:
    """Logarithm: y = ln(1 + fator·t) / ln(1 + fator), t = fração normalizada de [minimo, maximo] após
    o deslocamento. `fator` controla a velocidade da subida inicial (Esri: "sobe rápido e depois
    achata"); `fator` → 0 tende ao comportamento linear."""
    minimo, maximo = _dominio(t)
    deslocamento = _num(t.get("deslocamento", 0.0))
    fator = _num(t.get("fator", 1.0))
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    frac = (valores + deslocamento - minimo) / (maximo - minimo) if maximo != minimo else np.zeros_like(valores)
    frac_clip = np.clip(frac, 0.0, 1.0)
    if fator <= 0:
        curva = frac_clip
    else:
        curva = np.log1p(fator * frac_clip) / math.log1p(fator)
    saida = _saida(curva, t)
    saida = _abaixo_acima(valores, frac, saida, t, False)
    return np.where(np.isnan(valores), np.nan, saida)


def _t_exponencial(valores, t: dict) -> np.ndarray:
    """Exponential: y = (base^(t+deslocamento) − base^deslocamento) / (base^(1+deslocamento) −
    base^deslocamento), t fração normalizada de [minimo, maximo]. `base` (Base factor) > 1 dá subida
    acentuada perto do máximo (Esri: "preferências sobem rápido para valores maiores")."""
    minimo, maximo = _dominio(t)
    deslocamento = _num(t.get("deslocamento", 0.0))
    base = _num(t.get("base", math.e))
    if base <= 0 or base == 1:
        raise ErroTransformacao(f"exponencial: base precisa ser > 0 e ≠ 1 (veio {base!r})")
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    frac = (valores - minimo) / (maximo - minimo) if maximo != minimo else np.zeros_like(valores)
    frac_clip = np.clip(frac, 0.0, 1.0)
    denom = base ** (1 + deslocamento) - base ** deslocamento
    if denom == 0:
        curva = frac_clip
    else:
        curva = (base ** (frac_clip + deslocamento) - base ** deslocamento) / denom
    saida = _saida(curva, t)
    saida = _abaixo_acima(valores, frac, saida, t, False)
    return np.where(np.isnan(valores), np.nan, saida)


def _logistico_k(minimo: float, maximo: float, p: float) -> float:
    """k tal que a logística padrão vale p % no ponto `minimo` e (100−p) % no ponto `maximo`, simétrica
    em torno do meio — a partir do `y_intercepto_percentual` (Y intercept percent) da Esri."""
    p = min(max(p, 1e-6), 50.0 - 1e-6) if p < 50 else p  # p é a % no extremo mais BAIXO da curva
    razao = (100.0 - p) / p
    if maximo == minimo:
        return 0.0
    return 2.0 * math.log(razao) / (maximo - minimo)


def _t_crescimento_logistico(valores, t: dict) -> np.ndarray:
    """Logistic Growth: y = 100 / (1 + exp(−k·(x − meio))), k calibrado por `y_intercepto_percentual`
    (valor da curva, em % de 100, no ponto `minimo`) — S crescente, achatado nas duas pontas."""
    minimo, maximo = _dominio(t)
    p = _num(t.get("y_intercepto_percentual", 1.0))
    meio = (minimo + maximo) / 2.0
    k = _logistico_k(minimo, maximo, p)
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    with np.errstate(over="ignore"):
        curva = 1.0 / (1.0 + np.exp(-k * (valores - meio)))
    saida = _saida(curva, t)
    abaixo, acima = t.get("abaixo"), t.get("acima")
    if abaixo is not None:
        saida = np.where(valores < minimo, float(abaixo), saida)
    if acima is not None:
        saida = np.where(valores > maximo, float(acima), saida)
    return np.where(np.isnan(valores), np.nan, saida)


def _t_decaimento_logistico(valores, t: dict) -> np.ndarray:
    """Logistic Decay: espelho da Logistic Growth (100 − crescimento), mesmos parâmetros — S
    decrescente ("preferências caem rápido e depois achatam")."""
    espelho = dict(t)
    espelho.pop("saida_min", None)
    espelho.pop("saida_max", None)
    espelho.pop("abaixo", None)
    espelho.pop("acima", None)
    base = _t_crescimento_logistico(valores, espelho)
    curva_0_1 = base / 100.0
    saida = _saida(1.0 - curva_0_1, t)
    minimo, maximo = _dominio(t)
    valores_arr = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    abaixo, acima = t.get("abaixo"), t.get("acima")
    if abaixo is not None:
        saida = np.where(valores_arr < minimo, float(abaixo), saida)
    if acima is not None:
        saida = np.where(valores_arr > maximo, float(acima), saida)
    return np.where(np.isnan(curva_0_1), np.nan, saida)


def _t_gaussiana(valores, t: dict) -> np.ndarray:
    """Gaussian: y = 100·exp(−spread·(x − midpoint)²). `spread` maior → curva mais estreita (mesmo
    efeito descrito pela Esri)."""
    midpoint = _num(t["midpoint"])
    spread = _num(t["spread"])
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    with np.errstate(over="ignore"):
        curva = np.exp(-spread * (valores - midpoint) ** 2)
    return _saida(curva, t)


def _t_proxima(valores, t: dict) -> np.ndarray:
    """Near: como a Gaussiana mas com expoente 4 no desvio — cai mais rápido perto do midpoint
    (Esri: "diminui mais rápido, com espalhamento mais estreito" que a Gaussiana)."""
    midpoint = _num(t["midpoint"])
    spread = _num(t["spread"])
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    with np.errstate(over="ignore"):
        curva = np.exp(-spread * (valores - midpoint) ** 4)
    return _saida(curva, t)


def _t_grande(valores, t: dict) -> np.ndarray:
    """Large: sigmoide crescente y = 100 / (1 + exp(−spread·(x − midpoint))) — valores bem acima do
    midpoint são preferidos (Esri: "valores maiores que o midpoint aumentam a preferência")."""
    midpoint = _num(t["midpoint"])
    spread = _num(t["spread"])
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    with np.errstate(over="ignore", divide="ignore"):
        curva = 1.0 / (1.0 + np.exp(-spread * (valores - midpoint)))
    return _saida(curva, t)


def _t_pequena(valores, t: dict) -> np.ndarray:
    """Small: sigmoide decrescente y = 100 / (1 + exp(spread·(x − midpoint))) — espelho de Large."""
    midpoint = _num(t["midpoint"])
    spread = _num(t["spread"])
    valores = np.asarray([np.nan if v is None else float(v) for v in valores], dtype=float)
    with np.errstate(over="ignore", divide="ignore"):
        curva = 1.0 / (1.0 + np.exp(spread * (valores - midpoint)))
    return _saida(curva, t)


def _estatisticas_ms(valores, t: dict) -> tuple[float, float]:
    """midpoint/spread efetivos de MSSmall/MSLarge a partir de `multiplicador_media`/
    `multiplicador_desvio` (Mean multiplier/Std multiplier) × média/desvio-padrão DA AMOSTRA — os
    únicos dois parâmetros que a Esri diz que a função usa. Se `media`/`desvio` já vierem gravados na
    transformação (congelados por `resolver_estatisticas`, o mesmo padrão de `resolver_quebras`), usa
    esses — é o que o SQL sempre recebe, para não precisar agregar a coluna inteira dentro da função
    escalar."""
    if "media" in t and "desvio" in t:
        media, desvio = _num(t["media"]), _num(t["desvio"])
    else:
        limpos = np.asarray([float(v) for v in valores if v is not None and not
                             (isinstance(v, float) and math.isnan(v))], dtype=float)
        if limpos.size == 0:
            raise ErroTransformacao(f"{t.get('tipo')}: amostra vazia, não há como derivar média/desvio")
        media, desvio = float(limpos.mean()), float(limpos.std())
    mult_media = _num(t.get("multiplicador_media", 1.0))
    mult_desvio = _num(t.get("multiplicador_desvio", 1.0))
    midpoint = media * mult_media
    desvio_efetivo = desvio if desvio > 0 else 1.0
    spread = mult_desvio / desvio_efetivo
    return midpoint, spread


def resolver_estatisticas(valores, t: dict) -> dict:
    """Congela `media`/`desvio` em `ms_grande`/`ms_pequena` a partir da amostra, do mesmo jeito que
    `resolver_quebras` congela quebra por quantil — é essa versão resolvida que o SQL aplica."""
    if t.get("tipo") not in ("ms_grande", "ms_pequena") or ("media" in t and "desvio" in t):
        return t
    limpos = [v for v in valores if v is not None and not (isinstance(v, float) and math.isnan(v))]
    limpos_arr = np.asarray([float(v) for v in limpos], dtype=float)
    novo = dict(t)
    novo["media"] = float(limpos_arr.mean()) if limpos_arr.size else 0.0
    novo["desvio"] = float(limpos_arr.std()) if limpos_arr.size else 1.0
    return novo


def _t_ms_grande(valores, t: dict) -> np.ndarray:
    midpoint, spread = _estatisticas_ms(valores, t)
    return _t_grande(valores, {**t, "midpoint": midpoint, "spread": spread})


def _t_ms_pequena(valores, t: dict) -> np.ndarray:
    midpoint, spread = _estatisticas_ms(valores, t)
    return _t_pequena(valores, {**t, "midpoint": midpoint, "spread": spread})


_DESPACHO = {
    "categoria": _t_categoria,
    "faixas": _t_faixas,
    "linear": _t_linear,
    "linear_simetrica": _t_linear_simetrica,
    "degraus": _t_degraus,
    "potencia": _t_potencia,
    "logaritmo": _t_logaritmo,
    "exponencial": _t_exponencial,
    "crescimento_logistico": _t_crescimento_logistico,
    "decaimento_logistico": _t_decaimento_logistico,
    "gaussiana": _t_gaussiana,
    "proxima": _t_proxima,
    "grande": _t_grande,
    "pequena": _t_pequena,
    "ms_grande": _t_ms_grande,
    "ms_pequena": _t_ms_pequena,
}


def transformar(valores, transformacao: dict) -> np.ndarray:
    """valor bruto (lista/array; `None`/NaN preservados) → favorabilidade 0-100 (ou a escala de
    `saida_min`/`saida_max`), conforme `transformacao['tipo']`. Vetorizado: uma chamada, todos os
    valores; é o que a pré-visualização e a recomputação independente usam."""
    tipo = transformacao.get("tipo")
    fn = _DESPACHO.get(tipo)
    if fn is None:
        raise ErroTransformacao(f"tipo de transformação desconhecido: {tipo!r} (válidos: {TIPOS_VALIDOS})")
    return fn(list(valores), transformacao)


def transformar_um(valor, transformacao: dict) -> float | None:
    """Conveniência escalar (usada pelo executor, um valor por unidade)."""
    r = transformar([valor], transformacao)
    v = r[0]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


@dataclass
class PreVisualizacao:
    entrada_histograma: dict
    saida_histograma: dict
    n: int
    n_nulo: int
    tempo_ms: float


def pre_visualizar(valores, transformacao: dict, bins: int = 30) -> PreVisualizacao:
    """Histograma de entrada e de saída para o painel de pré-visualização (portão de pronto: ≤ 300 ms
    para 100 mil valores). Não abre banco; recebe o array já em memória."""
    import time

    t0 = time.perf_counter()
    valores = list(valores)
    saida = transformar(valores, transformacao)
    if transformacao.get("tipo") == "categoria":
        categorias, contagens = np.unique([str(v) for v in valores if v is not None], return_counts=True)
        hist_entrada = {"tipo": "categorico", "categorias": categorias.tolist(), "contagens": contagens.tolist()}
    else:
        limpos = np.asarray([float(v) for v in valores if v is not None and not
                             (isinstance(v, float) and math.isnan(v))], dtype=float)
        if limpos.size:
            contagens, bordas = np.histogram(limpos, bins=bins)
            hist_entrada = {"tipo": "numerico", "contagens": contagens.tolist(), "bordas": bordas.tolist()}
        else:
            hist_entrada = {"tipo": "numerico", "contagens": [], "bordas": []}
    limpos_saida = saida[~np.isnan(saida)]
    if limpos_saida.size:
        contagens_s, bordas_s = np.histogram(limpos_saida, bins=bins, range=(0.0, 100.0))
        hist_saida = {"tipo": "numerico", "contagens": contagens_s.tolist(), "bordas": bordas_s.tolist()}
    else:
        hist_saida = {"tipo": "numerico", "contagens": [], "bordas": []}
    dt_ms = (time.perf_counter() - t0) * 1000.0
    n_nulo = int(np.isnan(saida).sum())
    return PreVisualizacao(hist_entrada, hist_saida, len(valores), n_nulo, dt_ms)
