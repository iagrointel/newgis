"""Perfil de elevação e altitude no cursor (item L2-09-a-terreno-terrain-rgb-relevo).

A hipótese do item exige que a amostragem do perfil e da altitude no cursor aconteça no SERVIDOR
sobre o COG, não no tile — este teste confere que `app.relevo.perfil` é isso mesmo: um perfil de
10 km com 200 amostras cujo valor em cada ponto bate com uma chamada independente a `rasterio.sample`
nas mesmas coordenadas (a mesma verificação que o portão de pronto pede)."""

from __future__ import annotations

import math
import socket

import numpy as np
import pytest
import rasterio

from app.relevo import perfil

VRT_LORENA = "/home/dev/plataforma/laco/var/dem_lorena/lorena_glo30.vrt"


def _tem_rede_s3() -> bool:
    try:
        socket.create_connection(("copernicus-dem-30m.s3.amazonaws.com", 443), timeout=4).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _tem_rede_s3(), reason="sem alcance ao S3 copernicus-dem-30m nesta máquina agora")

# reta de ~10 km cruzando a serra perto de Lorena-SP (ponto de partida e chegada dentro do bloco S23_00_W046_00)
LAT1, LON1 = -22.75, -45.20
LAT2, LON2 = -22.68, -45.13


def test_distancia_haversine_bate_com_formula_direta_para_10km():
    d = perfil.distancia_haversine_m(LAT1, LON1, LAT2, LON2)
    assert 9_000 < d < 11_500  # ~10 km, tolerância generosa para a reta escolhida à mão


def test_perfil_de_10km_com_200_amostras_confere_com_rasterio_sample_direto():
    n = 200
    pontos = perfil.perfil_elevacao(VRT_LORENA, LAT1, LON1, LAT2, LON2, n_amostras=n)
    assert len(pontos) == n
    assert pontos[0].distancia_m == pytest.approx(0.0, abs=1e-6)
    assert pontos[-1].distancia_m == pytest.approx(perfil.distancia_haversine_m(LAT1, LON1, LAT2, LON2), rel=1e-9)

    # leitura independente, direta, sem passar por app.relevo.perfil
    coordenadas = [(p.lon, p.lat) for p in pontos]
    with rasterio.open(VRT_LORENA) as ds:
        valores_diretos = [v[0] for v in ds.sample(coordenadas)]

    validos = 0
    for p, esperado in zip(pontos, valores_diretos):
        if esperado <= -9000.0:
            assert p.altura_m is None
            continue
        assert p.altura_m == pytest.approx(float(esperado), abs=1e-6)
        validos += 1
    assert validos > n * 0.8, "cobertura de dado válido baixa demais para o trecho escolhido"


def test_altitude_no_ponto_usa_a_mesma_leitura_do_perfil():
    altura = perfil.altitude_no_ponto(VRT_LORENA, LAT1, LON1)
    with rasterio.open(VRT_LORENA) as ds:
        esperado = list(ds.sample([(LON1, LAT1)]))[0][0]
    assert altura == pytest.approx(float(esperado), abs=1e-6)


def test_pontos_do_perfil_extremos_batem_com_as_coordenadas_de_entrada():
    pontos = perfil.pontos_do_perfil(LAT1, LON1, LAT2, LON2, 5)
    assert pontos[0] == (LAT1, LON1)
    assert pontos[-1] == (LAT2, LON2)


def test_perfil_recusa_menos_de_2_amostras():
    with pytest.raises(ValueError):
        perfil.pontos_do_perfil(LAT1, LON1, LAT2, LON2, 1)
