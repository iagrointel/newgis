"""Testes do motor de classificação numérica (item L2-02-b-classificacao-servidor). Cada teste
prova uma cláusula literal do portão de pronto; a medida de desempenho é gravada à parte
(tests/api/catalogo/test_classes_rota.py) porque exige a máquina calma (ver brief comum)."""

import numpy as np
import pytest

from app.estatistica import classificacao as c

# ---------------------------------------------------------------------------
# cláusula 1: quantil e intervalo igual iguais a numpy.quantile/numpy.linspace (5 campos)
# ---------------------------------------------------------------------------

CAMPOS_CLAUSULA_1 = [
    np.random.default_rng(1).normal(50, 10, 500),
    np.random.default_rng(2).exponential(3, 800),
    np.random.default_rng(3).uniform(-100, 100, 300),
    np.concatenate([np.random.default_rng(4).normal(0, 1, 400), np.full(50, 7.0)]),  # com repetidos
    np.random.default_rng(5).lognormal(0, 1, 1000),
]


@pytest.mark.parametrize("valores", CAMPOS_CLAUSULA_1, ids=[f"campo{i+1}" for i in range(5)])
@pytest.mark.parametrize("n", [3, 5, 7])
def test_quantil_igual_a_numpy(valores, n):
    esperado = np.quantile(valores, np.linspace(0.0, 1.0, n + 1))
    obtido = c.quantil(valores, n)
    assert np.allclose(obtido, esperado, atol=0.0, rtol=0.0)


@pytest.mark.parametrize("valores", CAMPOS_CLAUSULA_1, ids=[f"campo{i+1}" for i in range(5)])
@pytest.mark.parametrize("n", [3, 5, 7])
def test_intervalo_igual_a_numpy(valores, n):
    esperado = np.linspace(float(np.min(valores)), float(np.max(valores)), n + 1)
    obtido = c.intervalo_igual(valores, n)
    assert np.allclose(obtido, esperado, atol=0.0, rtol=0.0)


# ---------------------------------------------------------------------------
# cláusula 2: Jenks confere com implementação de referência independente
# (jenkspy — pacote de terceiro, algoritmo Fisher-Jenks, dependência só de teste)
# ---------------------------------------------------------------------------

jenkspy = pytest.importorskip("jenkspy", reason="jenkspy é a referência independente desta cláusula do portão")

CONJUNTOS_1000 = [
    ("normal", np.random.default_rng(10).normal(0, 1, 1000)),
    ("exponencial", np.random.default_rng(11).exponential(50, 1000)),
    ("uniforme", np.random.default_rng(12).uniform(0, 1000, 1000)),
]


@pytest.mark.parametrize("nome,valores", CONJUNTOS_1000, ids=[n for n, _ in CONJUNTOS_1000])
@pytest.mark.parametrize("n", [3, 5, 7])
def test_jenks_confere_com_referencia_independente(nome, valores, n):
    referencia = jenkspy.jenks_breaks(valores.tolist(), n_classes=n)
    obtido, agregado = c.quebras_naturais(valores, n)
    assert agregado is False, "1000 valores não deveriam disparar o histograma de posições"
    assert len(obtido) == len(referencia) == n + 1
    for a, b in zip(obtido, referencia, strict=True):
        assert abs(a - b) <= 1e-9, f"{nome} n={n}: {a!r} != {b!r} (diferença {abs(a-b):.3e})"


# ---------------------------------------------------------------------------
# cláusula 3: nulos excluídos e contados; repetidos não geram classe vazia
# ---------------------------------------------------------------------------

def test_nulos_excluidos_e_contados():
    bruto = np.array([1.0, 2.0, np.nan, 3.0, np.nan, np.nan, 4.0])
    validos, nulos = c.separar_nulos(bruto)
    assert nulos == 3
    assert validos.size == 4
    resumo = c.resumo(validos, nulos)
    assert resumo["nulos"] == 3
    assert resumo["validos"] == 4
    assert resumo["total"] == 7
    assert resumo["minimo"] == 1.0 and resumo["maximo"] == 4.0


@pytest.mark.parametrize("metodo", ["quantil", "intervalo_igual", "jenks", "desvio_padrao"])
def test_repetidos_nao_geram_classe_vazia(metodo):
    # muita repetição forçada — a classe do valor mais repetido não pode desaparecer
    bruto = np.array([1.0] + [2.0] * 30 + [3.0] * 2 + [4.0], dtype=float)
    validos, nulos = c.separar_nulos(bruto)
    if metodo == "quantil":
        cortes = c.quantil(validos, 3)
    elif metodo == "intervalo_igual":
        cortes = c.intervalo_igual(validos, 3)
    elif metodo == "jenks":
        cortes, _ = c.quebras_naturais(validos, 3)
    else:
        cortes = c.desvio_padrao(validos, 1.0)
    contagens = c.contagem_por_classe(validos, cortes)
    assert sum(contagens) == validos.size
    # o valor 2.0 (30 ocorrências) tem que estar inteiro em UMA classe não vazia
    assert max(contagens) >= 30, f"{metodo}: {cortes} -> {contagens} perdeu o bloco de repetidos"
    assert all(ct >= 0 for ct in contagens)


def test_jenks_com_poucos_distintos_nao_produz_lacuna_falsa():
    """Caso extremo do achado de build: 4 valores distintos, 3 classes pedidas, corte duplicado
    (classe de um único ponto) — contagem_por_classe não pode zerar essa classe."""
    bruto = np.array([1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 4.0])
    cortes, _ = c.quebras_naturais(bruto, 3)
    contagens = c.contagem_por_classe(bruto, cortes)
    assert sum(contagens) == bruto.size == 7
    assert 0 not in contagens, f"cortes {cortes} produziram classe vazia: {contagens}"


# ---------------------------------------------------------------------------
# cláusula 4: 1 milhão de valores classificados em <= 2 s (medida na suíte de API/desempenho)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metodo", ["quantil", "intervalo_igual", "jenks", "desvio_padrao"])
def test_um_milhao_de_valores_nao_trava(metodo):
    """Prova funcional rápida (sem cronômetro — o cronômetro é a suíte de API, que precisa da
    máquina calma). Aqui só garante que o caminho de 1 milhão de valores devolve cortes válidos
    e não estoura memória nem trava num laço O(n²)."""
    valores = np.random.default_rng(42).normal(100, 20, 1_000_000)
    if metodo == "quantil":
        cortes = c.quantil(valores, 6)
    elif metodo == "intervalo_igual":
        cortes = c.intervalo_igual(valores, 6)
    elif metodo == "jenks":
        cortes, agregado = c.quebras_naturais(valores, 6)
        assert agregado is True, "1 milhão de valores contínuos deveria passar do teto de posições"
    else:
        cortes = c.desvio_padrao(valores, 0.5)
    assert len(cortes) >= 2
    assert cortes == sorted(cortes)


# ---------------------------------------------------------------------------
# cláusula 5: categorias com 5.000 distintos devolvem 200 + total
# ---------------------------------------------------------------------------

def test_categorias_5000_distintos_devolve_200_mais_outros():
    rng = np.random.default_rng(7)
    universo = [f"categoria_{i}" for i in range(5000)]
    extra = list(rng.choice(universo, size=35000))
    coluna = universo + extra  # garante as 5.000 categorias presentes ao menos 1 vez
    resultado = c.valores_unicos(coluna, limite=200)
    assert resultado.total_distintos == 5000
    assert resultado.truncado is True
    assert len(resultado.valores) == 201  # 200 principais + 1 linha "outros"
    outros = resultado.valores[-1]
    assert outros["valor"] == "outros"
    soma_principais = sum(v["contagem"] for v in resultado.valores[:200])
    assert soma_principais + outros["contagem"] == len(coluna)
    assert outros["distintos_agrupados"] == 5000 - 200


def test_categorias_abaixo_do_limite_nao_trunca():
    coluna = ["a"] * 10 + ["b"] * 5 + ["c"] * 1
    resultado = c.valores_unicos(coluna, limite=200)
    assert resultado.truncado is False
    assert resultado.total_distintos == 3
    assert len(resultado.valores) == 3
    assert resultado.valores[0] == {"valor": "a", "contagem": 10}


# ---------------------------------------------------------------------------
# outras validações do motor (fora do portão literal, mas exigidas pela refutação)
# ---------------------------------------------------------------------------

def test_desvio_padrao_fracao_invalida_rejeitada():
    with pytest.raises(c.ErroClassificacao):
        c.desvio_padrao(np.array([1.0, 2.0, 3.0]), 0.2)


def test_manual_cortes_fora_de_ordem_rejeitado():
    with pytest.raises(c.ErroClassificacao):
        c.manual(np.array([1.0, 2.0, 3.0]), [5.0, 1.0, 10.0])


def test_manual_cortes_repetidos_rejeitado():
    with pytest.raises(c.ErroClassificacao):
        c.manual(np.array([1.0, 2.0, 3.0]), [1.0, 2.0, 2.0, 5.0])


def test_n_zero_ou_negativo_rejeitado():
    with pytest.raises(c.ErroClassificacao):
        c.quantil(np.array([1.0, 2.0, 3.0]), 0)
    with pytest.raises(c.ErroClassificacao):
        c.intervalo_igual(np.array([1.0, 2.0, 3.0]), -1)


def test_sem_dados_rejeitado():
    with pytest.raises(c.ErroClassificacao):
        c.quantil(np.array([]), 5)
    with pytest.raises(c.ErroClassificacao):
        c.quebras_naturais(np.array([]), 5)


def test_histograma_n_faixas():
    valores = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    h = c.histograma(valores, 4)
    assert len(h["cortes"]) == 5
    assert sum(h["contagens"]) == valores.size


def test_n_maior_que_distintos_repete_ultimo_corte_sem_inventar_valor():
    valores = np.array([1.0, 1.0, 2.0])  # só 2 valores distintos
    cortes, _ = c.quebras_naturais(valores, 5)
    assert len(cortes) == 6
    assert cortes[0] == 1.0 and cortes[-1] == 2.0
    assert all(v in (1.0, 2.0) for v in cortes)
