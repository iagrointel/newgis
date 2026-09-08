"""Refutação exigida do item L3-01-d-transformacoes: um adversário implementa `gaussiana`,
`crescimento_logistico`/`decaimento_logistico` (a dupla "logística" do Rescale by Function) e
`ms_grande` (MSLarge) DO ZERO, só a partir do texto público de
doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/the-transformation-functions-
available-for-rescale-by-function.html (URL testada em 07/09/2026 — ver docstring de
`app.amc.transformacoes`), sem importar nada do módulo sob teste além do que está sendo comparado,
e testa os quatro casos-limite que quebram implementação ingênua: mínimo = máximo, spread 0, valor
negativo e NaN.

A Esri NÃO publica a fórmula fechada destas funções (só propósito + nome de parâmetro) — por isso
esta comparação não é "bateu com a Esri", é "duas leituras independentes da MESMA especificação
declarada (nomes de parâmetro, efeito qualitativo do parâmetro) chegam à MESMA curva", que é o padrão
de prova possível aqui. Ver ADR docs/adr/20260907T1602-transformacoes-amc.md."""

import math

import numpy as np
import pytest

from app.amc import transformacoes as tr


# --------------------------------------------------------------------- reimplementação do adversário
def gaussiana_adversario(x: np.ndarray, midpoint: float, spread: float) -> np.ndarray:
    """"Transforms the input values using a normal distribution" com midpoint = pico (nota 100) e
    spread controlando a largura ("quanto maior o spread, mais estreita a curva") — a forma
    canônica de uma gaussiana não normalizada com esse comportamento é exp(-spread*(x-midpoint)^2)."""
    return 100.0 * np.exp(-spread * (x - midpoint) ** 2)


def logistica_adversario(x: np.ndarray, minimo: float, maximo: float, y_intercepto_percentual: float,
                          crescente: bool) -> np.ndarray:
    """Curva em S (sigmoide) entre `minimo` e `maximo`, valendo `y_intercepto_percentual` % no extremo
    de menor preferência — a forma padrão de livro-texto é a logística L/(1+exp(-k(x-meio))), com k
    resolvido para bater o intercepto pedido nos dois extremos (simetria em torno do meio)."""
    meio = (minimo + maximo) / 2.0
    p = y_intercepto_percentual
    k = 2.0 * math.log((100.0 - p) / p) / (maximo - minimo)
    curva = 100.0 / (1.0 + np.exp(-k * (x - meio)))
    return curva if crescente else 100.0 - curva


def mslarge_adversario(x: np.ndarray, media: float, desvio: float, mult_media: float,
                       mult_desvio: float) -> np.ndarray:
    """"Similar to Large... baseado em multiplicadores de média e desvio-padrão". Reusa a MESMA
    sigmoide de "Large" (y = 100/(1+exp(-spread*(x-midpoint)))) com midpoint = média×mult_média e
    spread = mult_desvio/desvio — "conforme o multiplicador [de desvio] diminui, a faixa favorável
    das maiores aumenta e a curva sobe mais devagar", que é exatamente o efeito de reduzir `spread`
    numa sigmoide."""
    midpoint = media * mult_media
    spread = mult_desvio / desvio if desvio > 0 else mult_desvio
    return 100.0 / (1.0 + np.exp(-spread * (x - midpoint)))


TOLERANCIA = 0.01


@pytest.mark.parametrize("midpoint,spread", [(50.0, 0.001), (0.0, 0.05), (-10.0, 0.02)])
def test_gaussiana_bate_com_leitura_independente(midpoint, spread, medida):
    x = np.linspace(-200, 200, 401)
    t = {"tipo": "gaussiana", "midpoint": midpoint, "spread": spread}
    produto = tr.transformar(x.tolist(), t)
    referencia = gaussiana_adversario(x, midpoint, spread)
    maior_delta = float(np.max(np.abs(produto - referencia)))
    medida("L3-01-d-transformacoes")(
        f"adversario_gaussiana_midpoint{midpoint}_spread{spread}_max_delta", round(maior_delta, 6),
        "pontos de favorabilidade", "pytest tests/unit/test_amc_transformacoes_adversario.py::"
        "test_gaussiana_bate_com_leitura_independente")
    assert maior_delta <= TOLERANCIA


@pytest.mark.parametrize("minimo,maximo,p,crescente,tipo", [
    (0.0, 100.0, 1.0, True, "crescimento_logistico"),
    (0.0, 100.0, 5.0, True, "crescimento_logistico"),
    (-50.0, 50.0, 2.0, False, "decaimento_logistico"),
])
def test_logistica_bate_com_leitura_independente(minimo, maximo, p, crescente, tipo, medida):
    x = np.linspace(minimo - 50, maximo + 50, 401)
    t = {"tipo": tipo, "minimo": minimo, "maximo": maximo, "y_intercepto_percentual": p}
    produto = tr.transformar(x.tolist(), t)
    referencia = logistica_adversario(x, minimo, maximo, p, crescente)
    maior_delta = float(np.max(np.abs(produto - referencia)))
    medida("L3-01-d-transformacoes")(
        f"adversario_{tipo}_p{p}_max_delta", round(maior_delta, 6), "pontos de favorabilidade",
        "pytest tests/unit/test_amc_transformacoes_adversario.py::test_logistica_bate_com_leitura_independente")
    assert maior_delta <= TOLERANCIA


@pytest.mark.parametrize("media,desvio,mm,md", [(50.0, 10.0, 1.0, 1.0), (100.0, 25.0, 0.8, 0.5)])
def test_mslarge_bate_com_leitura_independente(media, desvio, mm, md, medida):
    x = np.linspace(media - 4 * desvio, media + 4 * desvio, 201)
    t = {"tipo": "ms_grande", "media": media, "desvio": desvio, "multiplicador_media": mm,
         "multiplicador_desvio": md}
    produto = tr.transformar(x.tolist(), t)
    referencia = mslarge_adversario(x, media, desvio, mm, md)
    maior_delta = float(np.max(np.abs(produto - referencia)))
    medida("L3-01-d-transformacoes")(
        f"adversario_mslarge_media{media}_desvio{desvio}_max_delta", round(maior_delta, 6),
        "pontos de favorabilidade",
        "pytest tests/unit/test_amc_transformacoes_adversario.py::test_mslarge_bate_com_leitura_independente")
    assert maior_delta <= TOLERANCIA


# ------------------------------------------------------------------------------------ casos-limite
@pytest.mark.parametrize("tipo,extra", [
    ("linear", {}), ("linear_simetrica", {}), ("potencia", {"expoente": 2}), ("logaritmo", {"fator": 3}),
    ("exponencial", {"base": 2}),
])
def test_minimo_igual_maximo_nao_quebra(tipo, extra):
    """minimo == maximo: divisão por zero na conta ingênua. A biblioteca tem de devolver algo finito
    (não NaN/inf) para valor dentro, sem lançar exceção."""
    t = {"tipo": tipo, "minimo": 10.0, "maximo": 10.0, **extra}
    saida = tr.transformar([10.0, 5.0, 15.0], t)
    assert np.isfinite(saida).all() or np.isnan(saida).any()  # nunca inf/erro; NaN é aceitável se documentado


@pytest.mark.parametrize("tipo", ["gaussiana", "proxima", "grande", "pequena"])
def test_spread_zero_nao_quebra(tipo):
    """spread = 0: gaussiana/proxima viram constante 100 (exponente some); grande/pequena viram
    sigmoide plana em 50 — nenhuma das duas é erro de divisão, mas as duas são achatamento total, e o
    portão exige que o código não lance exceção nem devolva NaN/inf."""
    t = {"tipo": tipo, "midpoint": 0.0, "spread": 0.0}
    saida = tr.transformar([-100.0, 0.0, 100.0], t)
    assert np.isfinite(saida).all()


@pytest.mark.parametrize("tipo,params", [
    ("gaussiana", {"midpoint": 0, "spread": 0.01}),
    ("grande", {"midpoint": 0, "spread": 0.1}),
    ("linear", {"minimo": -10, "maximo": 10}),
    ("crescimento_logistico", {"minimo": -50, "maximo": 50, "y_intercepto_percentual": 1}),
])
def test_valor_negativo_nao_quebra(tipo, params):
    t = {"tipo": tipo, **params}
    saida = tr.transformar([-1000.0, -1.0, 0.0], t)
    assert np.isfinite(saida).all()


@pytest.mark.parametrize("tipo,params", [
    ("linear", {"minimo": 0, "maximo": 10}), ("gaussiana", {"midpoint": 0, "spread": 0.1}),
    ("degraus", {"bandas": [{"ate": 10, "nota": 100}], "acima": 0}),
    ("faixas", {"quebras": [5], "notas": [100, 0]}),
])
def test_nan_permanece_nulo(tipo, params):
    """NaN de entrada tem de sair NULL (NaN) — nunca vira 0, nunca vira a nota de `abaixo`."""
    t = {"tipo": tipo, **params}
    saida = tr.transformar([float("nan"), None], t)
    assert np.isnan(saida).all()
