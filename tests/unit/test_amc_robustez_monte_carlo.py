"""Item L3-02-a-monte-carlo-pesos — o sorteio de pesos medido contra respostas CALCULADAS À MÃO.

Arquivo separado de `tests/unit/test_amc_robustez.py` de propósito: aquele prova o contrato do módulo
(recusas, reprodução, veto fora do sorteio). Este mede as duas cláusulas do `portao_de_pronto` que só
valem se o valor esperado vier de fora do código — "semente gravada e resultado reproduzível bit a bit
com a mesma semente" e "teste com modelo de 2 fatores de resposta analítica conhecida" — e a faixa de
posição estável que sai dessa mesma conta.

## A conta, feita à mão antes de rodar

Dois fatores, sorteio Dirichlet com concentração `None` (alpha = [1, 1]). Em duas dimensões, Dirichlet(1,1)
é a distribuição UNIFORME no simplex: w1 ~ U(0, 1) e w2 = 1 − w1. O combinador `soma_ponderada` normaliza
os pesos pela soma (que já é 1), então a nota de uma unidade com fatores (a, b) é exatamente

    fav = w1·a + (1 − w1)·b ,  com w1 ~ U(0, 1)

Com isso, para cada unidade do conjunto de teste:

  A = (100, 0):  fav_A = 100·w1
       E[fav_A] = 100·E[w1] = 100 · 1/2 = 50,0 exatos
       desvio(fav_A) = 100 · sqrt(1/12) = 100 / 3,4641016 = 28,867513 exatos
       mínimo → 0 e máximo → 100 (varredura do intervalo inteiro)

  B = (0, 100):  fav_B = 100·(1 − w1) = 100 − fav_A
       E[fav_B] = 50,0 ; fav_A + fav_B = 100 em CADA sorteio (identidade, não aproximação)

  E = (99, 99):  fav_E = 99·w1 + 99·(1 − w1) = 99,0 em todo sorteio
       desvio(fav_E) = 0 exato ; mínimo = máximo = 99,0

Frequência no top-1 (k_top = 1) do conjunto {A, B, E}:
  E fica em 1º lugar quando 99 > 100·w1 E 99 > 100·(1 − w1), ou seja 0,01 < w1 < 0,99.
  P(E em 1º) = 0,99 − 0,01 = 0,98 exato.
  A fica em 1º quando 100·w1 > 99, ou seja w1 > 0,99  →  P = 0,01.
  B fica em 1º quando 100·(1 − w1) > 99, ou seja w1 < 0,01  →  P = 0,01.
  Soma: 0,98 + 0,01 + 0,01 = 1,00 (sempre há exatamente um primeiro colocado).

Faixa de posição estável, também calculada à mão: com N = 1.000 sorteios independentes, a frequência
observada de E é binomial(1000; 0,98), média 980 e desvio sqrt(1000·0,98·0,02) = 4,427. A banda de
5 desvios é 980 ± 22,1 → [957,9 ; 1000]. O corte de "estável" do módulo (≥ 95 %, isto é 950) fica
6,8 desvios abaixo da média, então E tem de sair `estavel=True` sem depender de sorte. Pelo mesmo
cálculo, A e B são binomial(1000; 0,01), média 10 e desvio 3,146 — a banda de 5 desvios é [0 ; 25,7],
muito abaixo de 950, logo A e B nunca podem sair `estavel`.

Nenhum dos números acima foi lido da saída de `app.amc.robustez`: todos saem de w1 ~ U(0, 1).
"""

import math

import numpy as np
import pytest

from app.amc import robustez

# conjunto de teste do cabeçalho: A só tem o fator 1, B só o fator 2, E tem 99 nos dois.
FATORES = np.array([[100.0, 0.0], [0.0, 100.0], [99.0, 99.0]])
IDS_FATORES = ["f1", "f2"]
N = 1000
SEMENTE = 20260917

# valores calculados à mão no cabeçalho
MEDIA_ANALITICA = 50.0
DESVIO_ANALITICO_A = 100.0 / math.sqrt(12.0)          # 28,867513...
P_TOPO_E = 0.98
P_TOPO_A = 0.01
DESVIO_BINOMIAL_E = math.sqrt(N * P_TOPO_E * (1 - P_TOPO_E)) / N   # 0,004427
DESVIO_BINOMIAL_A = math.sqrt(N * P_TOPO_A * (1 - P_TOPO_A)) / N   # 0,003146


def _simular(semente: int = SEMENTE, n: int = N):
    return robustez.simular_robustez(
        FATORES, [1.0, 1.0], n=n, metodo="dirichlet", concentracao=None,
        ids_fatores=IDS_FATORES, k_top=1, semente=semente,
    )


def test_media_e_desvio_batem_com_a_esperanca_analitica():
    """E[fav_A] = 50,0 e desvio = 100/sqrt(12) = 28,8675, das contas do cabeçalho. A tolerância é a do
    erro de amostragem de N = 1.000 sorteios (desvio da média = 28,87/sqrt(1000) = 0,913; usa-se 5×)."""
    r = _simular()
    erro_padrao_da_media = DESVIO_ANALITICO_A / math.sqrt(N)
    assert r.media[0] == pytest.approx(MEDIA_ANALITICA, abs=5 * erro_padrao_da_media)
    assert r.media[1] == pytest.approx(MEDIA_ANALITICA, abs=5 * erro_padrao_da_media)
    assert r.desvio[0] == pytest.approx(DESVIO_ANALITICO_A, rel=0.10)
    assert r.desvio[1] == pytest.approx(DESVIO_ANALITICO_A, rel=0.10)


def test_identidade_exata_do_simplex_de_dois_fatores():
    """fav_A + fav_B = 100 em todo sorteio porque w1 + w2 = 1 — identidade, não aproximação: vale para
    o mínimo de A com o máximo de B e vice-versa, não só para a média."""
    r = _simular()
    assert r.media[0] + r.media[1] == pytest.approx(100.0, abs=1e-9)
    assert r.minimo[0] + r.maximo[1] == pytest.approx(100.0, abs=1e-9)
    assert r.maximo[0] + r.minimo[1] == pytest.approx(100.0, abs=1e-9)


def test_unidade_indiferente_ao_peso_tem_desvio_zero_exato():
    """E = (99, 99): fav = 99·w1 + 99·(1−w1) = 99 em todo sorteio, qualquer que seja o peso. Mínimo,
    média e máximo iguais a 99,0 e desvio exatamente 0 — a conta não depende da semente."""
    r = _simular()
    assert r.media[2] == pytest.approx(99.0, abs=1e-9)
    assert r.minimo[2] == pytest.approx(99.0, abs=1e-9)
    assert r.maximo[2] == pytest.approx(99.0, abs=1e-9)
    assert r.desvio[2] == pytest.approx(0.0, abs=1e-9)


def test_minimo_e_maximo_varrem_o_intervalo_analitico_sem_ultrapassar():
    """fav_A = 100·w1 com w1 em (0,1): nunca sai de [0, 100]. Com 1.000 sorteios uniformes, o maior w1
    esperado é 1000/1001 = 0,999 (E[máximo de N uniformes] = N/(N+1)), então o máximo observado tem de
    passar de 95 e o mínimo ficar abaixo de 5 — a probabilidade de falhar é (0,95)^1000 ≈ 5e-23."""
    r = _simular()
    assert 0.0 <= r.minimo[0] < 5.0
    assert 95.0 < r.maximo[0] <= 100.0


def test_frequencia_no_topo_bate_com_a_probabilidade_calculada_a_mao():
    """P(E em 1º) = 0,98, P(A) = P(B) = 0,01, somando 1,00 — tudo do cabeçalho. A banda é de 5 desvios
    binomiais, também calculada à mão."""
    r = _simular()
    assert r.frequencia_topk[2] == pytest.approx(P_TOPO_E, abs=5 * DESVIO_BINOMIAL_E)
    assert r.frequencia_topk[0] == pytest.approx(P_TOPO_A, abs=5 * DESVIO_BINOMIAL_A)
    assert r.frequencia_topk[1] == pytest.approx(P_TOPO_A, abs=5 * DESVIO_BINOMIAL_A)
    # exatamente um primeiro colocado por sorteio: as frequências somam 1 sem folga
    assert float(r.frequencia_topk.sum()) == pytest.approx(1.0, abs=1e-12)


def test_faixa_de_posicao_estavel_sai_da_mesma_conta():
    """`estavel` = frequência no top-k ≥ 95 %. Do cálculo à mão: E vale 0,98 (6,8 desvios acima do
    corte) e A/B valem 0,01 (muito abaixo). A separação é estrutural, não sorte."""
    r = _simular()
    assert bool(r.estavel[2]) is True
    assert bool(r.estavel[0]) is False
    assert bool(r.estavel[1]) is False
    assert r.frequencia_topk[2] >= 0.95
    assert r.frequencia_topk[0] < 0.95 and r.frequencia_topk[1] < 0.95


def test_a_conta_nao_depende_da_semente_escolhida():
    """Par positivo da reprodutibilidade: o resultado é reproduzível bit a bit com a MESMA semente (teste
    abaixo), mas a resposta analítica tem de aparecer com QUALQUER semente — senão o número certo seria
    coincidência de uma semente escolhida a dedo."""
    for semente in (1, 7, 2026, 999983):
        r = _simular(semente=semente)
        assert r.media[0] == pytest.approx(MEDIA_ANALITICA, abs=6.0)
        assert r.desvio[2] == pytest.approx(0.0, abs=1e-9)
        assert r.frequencia_topk[2] == pytest.approx(P_TOPO_E, abs=6 * DESVIO_BINOMIAL_E)
        assert bool(r.estavel[2]) is True


def test_semente_gravada_e_resultado_reproduzivel_bit_a_bit():
    """A semente sai gravada no resultado e no dicionário; duas execuções com a mesma semente são
    idênticas BIT A BIT (igualdade exata de float, nunca `approx`) em todas as saídas agregadas."""
    r1, r2 = _simular(), _simular()
    assert r1.semente == SEMENTE and r2.semente == SEMENTE
    assert r1.como_dicionario()["semente"] == SEMENTE
    for campo in ("minimo", "media", "maximo", "desvio", "frequencia_topk",
                  "frequencia_decil_superior", "estavel", "vetado"):
        a, b = getattr(r1, campo), getattr(r2, campo)
        assert np.array_equal(a, b, equal_nan=True), f"{campo} não reproduziu bit a bit"
    # e os vetores de peso sorteados também, que é onde a semente entra de fato
    p1 = robustez.sortear_pesos([1.0, 1.0], IDS_FATORES, 200, semente=SEMENTE)
    p2 = robustez.sortear_pesos([1.0, 1.0], IDS_FATORES, 200, semente=SEMENTE)
    assert np.array_equal(p1, p2)


def test_semente_diferente_muda_o_sorteio_mas_nao_a_resposta_analitica():
    """Par positivo da recusa acima: se qualquer semente desse o mesmo vetor, a reprodução bit a bit não
    provaria nada. Os pesos TÊM de mudar; as estatísticas analíticas, não."""
    p1 = robustez.sortear_pesos([1.0, 1.0], IDS_FATORES, 200, semente=SEMENTE)
    p2 = robustez.sortear_pesos([1.0, 1.0], IDS_FATORES, 200, semente=SEMENTE + 1)
    assert not np.array_equal(p1, p2)
    # mas os dois sorteios vivem no mesmo simplex: cada linha soma 1 (Dirichlet), sempre
    assert np.allclose(p1.sum(axis=1), 1.0) and np.allclose(p2.sum(axis=1), 1.0)


def test_permutar_a_ordem_dos_fatores_nao_muda_o_resultado_por_unidade():
    """Refutação declarada do item: permutar a ordem dos fatores e reexecutar com a mesma semente tem de
    dar resultado idêntico por unidade (o sorteio acontece em ordem canônica pelos IDs). Conferido contra
    a conta à mão: trocando f1 por f2, a unidade A vira (0, 100) e continua valendo fav = 100·w(f1)."""
    fatores_permutados = FATORES[:, ::-1]
    r_direto = _simular()
    r_permutado = robustez.simular_robustez(
        fatores_permutados, [1.0, 1.0], n=N, metodo="dirichlet", concentracao=None,
        ids_fatores=IDS_FATORES[::-1], k_top=1, semente=SEMENTE,
    )
    for campo in ("minimo", "media", "maximo", "desvio", "frequencia_topk", "estavel"):
        assert np.array_equal(getattr(r_direto, campo), getattr(r_permutado, campo), equal_nan=True), campo
