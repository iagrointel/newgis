"""Item L2-05-d: a estatística espacial de `app/ferramentas/estatistica_espacial.py` conferida contra uma
SEGUNDA implementação, na mesma entrada. Quem faz o papel de segunda implementação:

  * `esda` 2.10 + `libpysal` 4.15 (instalados no ambiente de teste, não em produção) para Getis-Ord Gi* e para
    o I de Moran global — sempre com os pesos em forma BINÁRIA, que é a forma em que as duas fórmulas foram
    publicadas (o padrão dessas bibliotecas é padronizar por linha, o que dá outro número);
  * a fórmula fechada escrita no próprio teste, com numpy, para o Gi* em conjuntos sintéticos, para o índice R
    de Clark & Evans, para o centro médio/distância padrão e para a elipse;
  * a integral do kernel e o valor nos pontos amostrados, para densidade e IDW.

Nenhum número esperado é escrito à mão.
"""

import math

import numpy as np
import pytest

from app.ferramentas import estatistica_espacial as ee

RAIO = 250.0


def nuvem(n=60, semente=7, lado=1000.0):
    rng = np.random.default_rng(semente)
    return rng.uniform(0, lado, size=(n, 2)), rng.normal(10.0, 3.0, n)


def pesos_libpysal(xy, raio):
    libpysal = pytest.importorskip("libpysal")
    return libpysal.weights.DistanceBand(np.asarray(xy), threshold=raio, binary=True, silence_warnings=True)


# ---------------------------------------------------------------- Gi*
def gi_estrela_fechada(valores, xy, raio):
    """A fórmula de Getis & Ord (1992) escrita de novo, com matriz densa e laço explícito."""
    x = np.asarray(valores, float)
    n = x.size
    d = np.linalg.norm(np.asarray(xy)[:, None, :] - np.asarray(xy)[None, :, :], axis=2)
    w = (d <= raio).astype(float)  # a diagonal já entra: distância zero
    media = x.mean()
    s = math.sqrt((x * x).sum() / n - media * media)
    z = np.empty(n)
    for i in range(n):
        soma_w = w[i].sum()
        numerador = (w[i] * x).sum() - media * soma_w
        denominador = s * math.sqrt((n * (w[i] ** 2).sum() - soma_w ** 2) / (n - 1))
        z[i] = numerador / denominador
    return z


@pytest.mark.parametrize("semente", [1, 7, 99])
def test_gi_estrela_bate_com_a_formula_fechada(semente):
    xy, v = nuvem(semente=semente)
    z = ee.gi_estrela(v, xy, RAIO)["z"]
    assert np.abs(z - gi_estrela_fechada(v, xy, RAIO)).max() < 1e-6


def test_gi_estrela_bate_com_esda():
    esda = pytest.importorskip("esda")
    xy, v = nuvem()
    z = ee.gi_estrela(v, xy, RAIO)["z"]
    referencia = esda.G_Local(v, pesos_libpysal(xy, RAIO), star=True, transform="B", permutations=0).Zs
    assert np.abs(z - referencia).max() < 1e-6


def test_gi_estrela_com_valores_iguais_devolve_nan_e_nao_erro():
    xy, _ = nuvem(n=20)
    r = ee.gi_estrela(np.full(20, 5.0), xy, RAIO)
    assert np.isnan(r["z"]).all() and r["desvio"] == 0.0


def test_gi_estrela_com_uma_feicao_recusa():
    with pytest.raises(ee.ErroEstatistica):
        ee.gi_estrela([1.0], [[0.0, 0.0]], RAIO)


def test_gi_estrela_com_todos_os_pontos_no_mesmo_lugar():
    """Vizinhança total: cada feição tem todas as outras por vizinha, o desvio da soma local é ZERO e o Gi*
    fica indefinido (n*soma(w^2) - soma(w)^2 = 0). O certo é devolver NaN, não um zero que pareceria resultado."""
    xy = np.zeros((25, 2))
    v = np.arange(25, dtype=float)
    r = ee.gi_estrela(v, xy, RAIO)
    assert (r["vizinhos"] == 25).all()
    assert np.isnan(r["z"]).all() and np.isnan(r["p"]).all()


# ---------------------------------------------------------------- Moran
def test_moran_global_bate_com_esda():
    esda = pytest.importorskip("esda")
    xy, v = nuvem()
    r = ee.moran_global(v, xy, RAIO)
    referencia = esda.Moran(v, pesos_libpysal(xy, RAIO), permutations=0, transformation="B")
    assert abs(r["i"] - referencia.I) < 1e-9
    assert abs(r["esperado"] - referencia.EI) < 1e-12
    assert abs(r["variancia"] - referencia.VI_norm) < 1e-12
    assert abs(r["z"] - referencia.z_norm) < 1e-6


def test_moran_global_sem_par_no_raio_recusa():
    xy = np.array([[0.0, 0.0], [10_000.0, 0.0], [20_000.0, 0.0]])
    with pytest.raises(ee.ErroEstatistica):
        ee.moran_global([1.0, 2.0, 3.0], xy, 10.0)


# ---------------------------------------------------------------- vizinho mais próximo médio
def test_vizinho_mais_proximo_medio_contra_formula_fechada():
    xy, _ = nuvem(n=200, semente=3)
    area = 1000.0 * 1000.0
    r = ee.vizinho_mais_proximo_medio(xy, area)
    d = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    assert abs(r["observada"] - d.min(axis=1).mean()) < 1e-9
    assert abs(r["esperada"] - 0.5 / math.sqrt(200 / area)) < 1e-12
    assert abs(r["razao"] - r["observada"] / r["esperada"]) < 1e-12


def test_vizinho_mais_proximo_medio_detecta_agrupamento():
    """Dois aglomerados apertados dentro de uma área grande: razão bem abaixo de 1 e z negativo."""
    rng = np.random.default_rng(11)
    a = rng.normal([100, 100], 5, size=(50, 2))
    b = rng.normal([900, 900], 5, size=(50, 2))
    r = ee.vizinho_mais_proximo_medio(np.vstack([a, b]), 1000.0 * 1000.0)
    assert r["razao"] < 0.5 and r["z"] < -5


# ---------------------------------------------------------------- centro médio, distância padrão, elipse
def test_centro_medio_e_distancia_padrao():
    xy, _ = nuvem(n=100, semente=5)
    p = np.abs(np.random.default_rng(2).normal(3, 1, 100))
    c = ee.centro_medio(xy, p)
    assert abs(c["x"] - float((xy[:, 0] * p).sum() / p.sum())) < 1e-9
    esperado = math.sqrt(float((p * ((xy[:, 0] - c["x"]) ** 2 + (xy[:, 1] - c["y"]) ** 2)).sum() / p.sum()))
    assert abs(c["distancia_padrao"] - esperado) < 1e-9


def test_elipse_de_nuvem_alongada_alinha_com_o_eixo_maior():
    rng = np.random.default_rng(4)
    xy = np.column_stack([rng.normal(0, 400, 500), rng.normal(0, 50, 500)])
    e = ee.elipse_desvio_padrao(xy, 1.0)
    assert e["eixo_maior"] > 5 * e["eixo_menor"]
    assert abs(e["rotacao_graus"] - 90.0) < 5.0  # eixo maior no sentido leste-oeste = azimute 90 graus
    assert abs(e["eixo_maior"] - float(xy[:, 0].std())) / e["eixo_maior"] < 0.05
    contorno = ee.pontos_da_elipse(e)
    assert contorno.shape == (73, 2) and np.allclose(contorno[0], contorno[-1])


def test_elipse_de_nuvem_circular_tem_eixos_parecidos():
    rng = np.random.default_rng(6)
    xy = rng.normal(0, 100, size=(2000, 2))
    e = ee.elipse_desvio_padrao(xy, 2.0)
    assert 0.9 < e["eixo_maior"] / e["eixo_menor"] < 1.1
    assert abs(e["eixo_maior"] / 2.0 - 100.0) < 10.0


# ---------------------------------------------------------------- densidade de kernel
@pytest.mark.parametrize("funcao", ["quartica", "triangular", "uniforme"])
def test_densidade_kernel_integra_o_numero_de_pontos(funcao):
    """A cláusula do portão: soma do raster vezes a área do pixel = N pontos, tolerância de 1 %."""
    rng = np.random.default_rng(13)
    xy = rng.uniform(2000, 8000, size=(200, 2))
    celula, raio = 50.0, 500.0
    gx = np.arange(0, 10_000, celula) + celula / 2
    gy = np.arange(0, 10_000, celula) + celula / 2
    z = ee.densidade_kernel(xy, gx, gy, raio, funcao)
    assert abs(z.sum() * celula * celula - 200.0) / 200.0 < 0.01


def test_densidade_kernel_gaussiana_truncada_perde_a_cauda_declarada():
    """A gaussiana é truncada no raio: falta 1 - exp(-4,5) da massa, e o teste registra isso em vez de fingir."""
    xy = np.array([[5000.0, 5000.0]])
    celula, raio = 25.0, 500.0
    g = np.arange(0, 10_000, celula) + celula / 2
    z = ee.densidade_kernel(xy, g, g, raio, "gaussiana")
    assert abs(z.sum() * celula * celula - (1.0 - math.exp(-4.5))) < 0.01


def test_densidade_kernel_com_peso_integra_a_soma_dos_pesos():
    rng = np.random.default_rng(17)
    xy = rng.uniform(3000, 7000, size=(50, 2))
    pesos = rng.uniform(1, 10, 50)
    celula, raio = 50.0, 400.0
    g = np.arange(0, 10_000, celula) + celula / 2
    z = ee.densidade_kernel(xy, g, g, raio, "quartica", pesos)
    assert abs(z.sum() * celula * celula - pesos.sum()) / pesos.sum() < 0.01


def test_densidade_de_linhas_integra_o_comprimento_total():
    linha = [[(1000.0, 5000.0), (9000.0, 5000.0)]]
    xy, pesos = ee.amostrar_linhas(linha, 25.0)
    assert abs(pesos.sum() - 8000.0) < 1e-6
    celula, raio = 50.0, 400.0
    g = np.arange(0, 10_000, celula) + celula / 2
    z = ee.densidade_kernel(xy, g, g, raio, "quartica", pesos)
    assert abs(z.sum() * celula * celula - 8000.0) / 8000.0 < 0.01


def test_densidade_kernel_recusa_raio_zero():
    with pytest.raises(ee.ErroEstatistica):
        ee.densidade_kernel([[0.0, 0.0]], [0.0], [0.0], 0.0)


# ---------------------------------------------------------------- IDW
def test_idw_reproduz_exatamente_os_valores_nos_pontos_amostrados():
    """A cláusula do portão: IDW em 100 pontos devolve o valor da amostra quando o alvo é a própria amostra."""
    rng = np.random.default_rng(23)
    xy = rng.uniform(0, 1000, size=(100, 2))
    v = rng.normal(50, 10, 100)
    assert np.array_equal(ee.idw(xy, v, xy, 2.0, 12), v)


def test_idw_entre_duas_amostras_fica_entre_os_dois_valores():
    xy = np.array([[0.0, 0.0], [100.0, 0.0]])
    v = np.array([0.0, 10.0])
    meio = ee.idw(xy, v, [[50.0, 0.0]], 2.0, 2)[0]
    assert abs(meio - 5.0) < 1e-9
    perto = ee.idw(xy, v, [[10.0, 0.0]], 2.0, 2)[0]
    assert 0.0 < perto < 5.0


def test_idw_com_potencia_alta_tende_ao_vizinho_mais_proximo():
    rng = np.random.default_rng(29)
    xy = rng.uniform(0, 1000, size=(30, 2))
    v = rng.normal(0, 5, 30)
    alvo = np.array([[123.4, 567.8]])
    forte = ee.idw(xy, v, alvo, 30.0, 30)[0]
    ordem = np.argsort(np.linalg.norm(xy - alvo, axis=1))
    mais_proximo, segundo = v[ordem[0]], v[ordem[1]]
    # não é interpolação exata: o que se afirma é que a potência alta cola no vizinho mais próximo
    assert abs(forte - mais_proximo) < 0.05 * abs(segundo - mais_proximo)


def test_idw_recusa_entrada_incoerente():
    with pytest.raises(ee.ErroEstatistica):
        ee.idw([[0.0, 0.0]], [1.0, 2.0], [[1.0, 1.0]])
    with pytest.raises(ee.ErroEstatistica):
        ee.idw([[0.0, 0.0]], [1.0], [[1.0, 1.0]], potencia=0.0)
