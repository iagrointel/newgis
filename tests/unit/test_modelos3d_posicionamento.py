"""Geodésia do posicionamento do modelo (item L2-09-c).

A cláusula do portão é "o GLB aparece na posição e escala corretas, com folga de 0,5 m". Aqui a folga
exigida é MUITO menor (milímetros): é aritmética fechada, sem navegador no meio. A folga de 0,5 m vale
para o teste de navegador, onde entram a projeção do MapLibre e a leitura de pixel.
"""

import math

import pytest

from app.modelos3d import posicionamento as pos
from tests.apoio_modelos3d import (
    ALTURA_M,
    CAIXA_ALTURA_M,
    LARGURA_M,
    LAT,
    LON,
    PROFUNDIDADE_M,
    caixa_vertices,
)

TOLERANCIA_M = 0.005


@pytest.mark.parametrize("lon, lat, h", [(-46.6333, -23.5505, 760.0), (0.0, 0.0, 0.0),
                                         (-38.5, -3.7, 12.0), (10.0, 60.0, 1500.0)])
def test_ida_e_volta_geodesica(lon, lat, h):
    x, y, z = pos.geodesico_para_ecef(lon, lat, h)
    lon2, lat2, h2 = pos.ecef_para_geodesico(x, y, z)
    assert lon2 == pytest.approx(lon, abs=1e-9)
    assert lat2 == pytest.approx(lat, abs=1e-9)
    assert h2 == pytest.approx(h, abs=1e-4)


def test_base_local_e_ortonormal():
    leste, norte, cima = pos.base_enu(LON, LAT)
    for v in (leste, norte, cima):
        assert math.sqrt(sum(c * c for c in v)) == pytest.approx(1.0, abs=1e-12)
    assert sum(leste[i] * norte[i] for i in range(3)) == pytest.approx(0.0, abs=1e-12)
    assert sum(leste[i] * cima[i] for i in range(3)) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("enu, esperado_m", [((10.0, 0.0, 0.0), 10.0), ((0.0, 25.0, 0.0), 25.0),
                                             ((30.0, 40.0, 0.0), 50.0)])
def test_deslocamento_local_da_a_distancia_pedida(enu, esperado_m):
    destino = pos.enu_para_geodesico(LON, LAT, ALTURA_M, enu)
    assert pos.distancia_m((LON, LAT), destino[:2], altura_m=ALTURA_M) == pytest.approx(esperado_m, abs=TOLERANCIA_M)


def test_altura_local_vira_altura_elipsoidal():
    _, _, h = pos.enu_para_geodesico(LON, LAT, ALTURA_M, (0.0, 0.0, 8.0))
    assert h == pytest.approx(ALTURA_M + 8.0, abs=TOLERANCIA_M)


def test_matriz_ecef_leva_a_origem_ao_ponto():
    m = pos.matriz_ecef(LON, LAT, ALTURA_M)
    assert pos.ecef_para_geodesico(m[12], m[13], m[14])[0] == pytest.approx(LON, abs=1e-9)
    assert pos.ecef_para_geodesico(m[12], m[13], m[14])[1] == pytest.approx(LAT, abs=1e-9)
    assert pos.ecef_para_geodesico(m[12], m[13], m[14])[2] == pytest.approx(ALTURA_M, abs=1e-4)


def test_rotacao_zero_poe_o_eixo_z_negativo_no_norte():
    """Convenção declarada: X do modelo é leste, -Z é norte, rotação é azimute horário."""
    assert pos.local_para_enu((0.0, 0.0, -10.0), 0.0)[1] == pytest.approx(10.0, abs=1e-9)
    assert pos.local_para_enu((10.0, 0.0, 0.0), 0.0)[0] == pytest.approx(10.0, abs=1e-9)


def test_rotacao_de_90_graus_manda_o_norte_para_o_leste():
    leste, norte, _ = pos.local_para_enu((0.0, 0.0, -10.0), 90.0)
    assert leste == pytest.approx(10.0, abs=1e-9)
    assert norte == pytest.approx(0.0, abs=1e-9)


def test_escala_multiplica_a_caixa():
    vertices = caixa_vertices()
    minimo = [min(v[i] for v in vertices) for i in range(3)]
    maximo = [max(v[i] for v in vertices) for i in range(3)]
    simples = pos.caixa_geografica(minimo, maximo, LON, LAT, ALTURA_M, 0.0, 1.0)
    dobro = pos.caixa_geografica(minimo, maximo, LON, LAT, ALTURA_M, 0.0, 2.0)
    largura_simples = pos.distancia_m((simples["oeste"], LAT), (simples["leste"], LAT), altura_m=ALTURA_M)
    largura_dobro = pos.distancia_m((dobro["oeste"], LAT), (dobro["leste"], LAT), altura_m=ALTURA_M)
    assert largura_simples == pytest.approx(LARGURA_M, abs=TOLERANCIA_M)
    assert largura_dobro == pytest.approx(2 * LARGURA_M, abs=TOLERANCIA_M)


def test_caixa_geografica_da_as_dimensoes_declaradas():
    """Esta é a conta que o teste de navegador confere depois, com folga de 0,5 m em vez de milímetros."""
    vertices = caixa_vertices()
    minimo = [min(v[i] for v in vertices) for i in range(3)]
    maximo = [max(v[i] for v in vertices) for i in range(3)]
    caixa = pos.caixa_geografica(minimo, maximo, LON, LAT, ALTURA_M, 0.0, 1.0)
    largura = pos.distancia_m((caixa["oeste"], LAT), (caixa["leste"], LAT), altura_m=ALTURA_M)
    profundidade = pos.distancia_m((LON, caixa["sul"]), (LON, caixa["norte"]), altura_m=ALTURA_M)
    assert largura == pytest.approx(LARGURA_M, abs=TOLERANCIA_M)
    assert profundidade == pytest.approx(PROFUNDIDADE_M, abs=TOLERANCIA_M)
    assert caixa["altura_minima"] == pytest.approx(ALTURA_M, abs=TOLERANCIA_M)
    assert caixa["altura_maxima"] == pytest.approx(ALTURA_M + CAIXA_ALTURA_M, abs=TOLERANCIA_M)
    assert len(caixa["cantos"]) == 8


def test_rotacao_de_90_graus_troca_largura_por_profundidade():
    vertices = caixa_vertices()
    minimo = [min(v[i] for v in vertices) for i in range(3)]
    maximo = [max(v[i] for v in vertices) for i in range(3)]
    caixa = pos.caixa_geografica(minimo, maximo, LON, LAT, ALTURA_M, 90.0, 1.0)
    largura = pos.distancia_m((caixa["oeste"], LAT), (caixa["leste"], LAT), altura_m=ALTURA_M)
    profundidade = pos.distancia_m((LON, caixa["sul"]), (LON, caixa["norte"]), altura_m=ALTURA_M)
    assert largura == pytest.approx(PROFUNDIDADE_M, abs=TOLERANCIA_M)
    assert profundidade == pytest.approx(LARGURA_M, abs=TOLERANCIA_M)
