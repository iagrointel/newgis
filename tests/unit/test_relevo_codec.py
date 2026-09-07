"""Codec de altura em RGB (item L2-09-a-terreno-terrain-rgb-relevo): ida-e-volta numérica pura, sem
GDAL e sem rede. Cobre as três codificações (terrain-RGB, Terrarium, normal map) e o tratamento de
nodata que a decodificação depende (preto puro = sem dado)."""

from __future__ import annotations

import numpy as np
import pytest

from app.relevo import codec


# ---------------------------------------------------------------------------- terrain-RGB (Mapbox)

@pytest.mark.parametrize("altura", [-413.0, 0.0, 0.1, 1.0, 848.9, 8848.86, 3.7])
# nota: -10000,0 m (o próprio TERRAIN_RGB_OFFSET) codifica para (0,0,0), que é o marcador de nodata —
# ambiguidade real do formato Mapbox, documentada em codec.py; nenhum terreno real chega lá (o ponto
# mais baixo em terra firme é o Mar Morto, ~-430 m), então não entra neste teste de ida-e-volta.
def test_terrain_rgb_ida_e_volta_no_passo_de_01m(altura):
    rgb = codec.codificar_terrain_rgb(np.array([[altura]]))
    de_volta = codec.decodificar_terrain_rgb(rgb)
    assert abs(de_volta[0, 0] - altura) <= codec.TERRAIN_RGB_PASSO / 2 + 1e-9


def test_terrain_rgb_offset_minimo_colide_com_nodata_achado_registrado():
    """Achado registrado (não é bug a consertar agora): -10000,0 m — o próprio `TERRAIN_RGB_OFFSET` —
    codifica para (0,0,0), idêntico ao marcador de nodata, então a decodificação devolve `nan` em vez
    da altura real. É a mesma ambiguidade do formato Mapbox terrain-RGB original (documentada por eles).
    Nenhum terreno real chega a -10000 m (o ponto mais baixo em terra firme é o Mar Morto, ~-430 m; a
    Fossa das Marianas, -10935 m, não é elevação de superfície terrestre neste produto), então o efeito
    prático é nulo — mas fica registrado para não ser redescoberto como bug."""
    rgb = codec.codificar_terrain_rgb(np.array([[codec.TERRAIN_RGB_OFFSET]]))
    assert tuple(rgb[0, 0]) == codec.NODATA_RGB
    assert np.isnan(codec.decodificar_terrain_rgb(rgb)[0, 0])


def test_terrain_rgb_nodata_vira_preto_puro_e_volta_como_nan():
    alturas = np.array([[100.0, np.nan], [np.nan, -5.5]])
    rgb = codec.codificar_terrain_rgb(alturas)
    assert tuple(rgb[0, 1]) == codec.NODATA_RGB
    assert tuple(rgb[1, 0]) == codec.NODATA_RGB
    de_volta = codec.decodificar_terrain_rgb(rgb)
    assert np.isnan(de_volta[0, 1])
    assert np.isnan(de_volta[1, 0])
    assert de_volta[0, 0] == pytest.approx(100.0, abs=0.05)
    assert de_volta[1, 1] == pytest.approx(-5.5, abs=0.05)


def test_terrain_rgb_satura_em_vez_de_estourar_no_pico_do_everest_mais_1000():
    # faixa útil ~ -10000 m a 1.667.721,5 m; nada na Terra real deveria saturar, mas o codec não pode
    # devolver lixo silencioso se algum dia receber um valor fora da faixa (ex.: erro de unidade a montante)
    rgb = codec.codificar_terrain_rgb(np.array([[10_000_000.0]]))
    de_volta = codec.decodificar_terrain_rgb(rgb)
    assert de_volta[0, 0] == pytest.approx(
        codec.TERRAIN_RGB_OFFSET + codec.TERRAIN_RGB_MAX_INTEIRO * codec.TERRAIN_RGB_PASSO, abs=0.2
    )
    assert not np.isnan(de_volta[0, 0])


def test_terrain_rgb_degrau_de_128m_da_armadilha_conhecida():
    """Armadilha citada na hipótese do item: um erro clássico de codificador terrain-RGB é confundir o
    byte mais significativo (R) — isso produz um degrau de exatamente 256 * 0,1 m = 25,6 m (1 passo do
    byte G) ou 65536 * 0,1 m = 6553,6 m (1 passo do byte R) na fronteira de byte, em vez de uma rampa
    suave de 0,1 m em 0,1 m. Sobe de 1 em 1 metro ao redor de várias fronteiras de byte (25,5/25,6 m,
    255,9/256,0 m) e confere que o degrau entre alturas vizinhas nunca passa de 1 passo (0,1 m + folga
    de arredondamento)."""
    alturas = np.arange(-50.0, 30_000.0, 1.0)
    rgb = codec.codificar_terrain_rgb(alturas.reshape(1, -1))
    de_volta = codec.decodificar_terrain_rgb(rgb)[0]
    diffs = np.diff(de_volta)
    assert np.max(diffs) <= 1.0 + codec.TERRAIN_RGB_PASSO + 1e-6, "degrau maior que 1 passo do codec entre alturas vizinhas"
    assert np.min(diffs) >= 1.0 - codec.TERRAIN_RGB_PASSO - 1e-6


# ---------------------------------------------------------------------------- Terrarium (Mapzen)

@pytest.mark.parametrize("altura", [-8000.0, -0.5, 0.0, 500.25, 8848.86])
def test_terrarium_ida_e_volta(altura):
    rgb = codec.codificar_terrarium(np.array([[altura]]))
    de_volta = codec.decodificar_terrarium(rgb)
    assert abs(de_volta[0, 0] - altura) <= 1.0 / codec.TERRARIUM_PASSO_INVERSO / 2 + 1e-9


def test_terrarium_nodata():
    alturas = np.array([[np.nan]])
    rgb = codec.codificar_terrarium(alturas)
    assert tuple(rgb[0, 0]) == codec.NODATA_RGB
    assert np.isnan(codec.decodificar_terrarium(rgb)[0, 0])


# ---------------------------------------------------------------------------- normal map (Mapzen "normal")

def test_normal_map_area_plana_aponta_reto_para_cima():
    alturas = np.full((8, 8), 500.0)
    rgba = codec.codificar_normal_map(alturas, passo_x_m=30.0, passo_y_m=30.0)
    # nx=ny=0, nz=1 -> R=G=127/128, B=255
    assert np.all(np.abs(rgba[..., 0].astype(int) - 128) <= 1)
    assert np.all(np.abs(rgba[..., 1].astype(int) - 128) <= 1)
    assert np.all(rgba[..., 2] == 255)
    # sem variação de altura -> alfa constante em 0,5 (ver _alfa_elevacao)
    assert np.all(np.abs(rgba[..., 3].astype(int) - 127) <= 1)


def test_normal_map_inclinacao_a_45_graus_inclina_a_normal():
    # dz/dx = 1 (subida de 1 m a cada 1 m) -> nx = -1/sqrt(2), componente R cai bem abaixo de 128
    x = np.arange(8, dtype=np.float64)
    alturas = np.tile(x, (8, 1))  # altura cresce 1 m por pixel em x
    rgba = codec.codificar_normal_map(alturas, passo_x_m=1.0, passo_y_m=1.0)
    meio = rgba[4, 4]
    assert meio[0] < 100  # nx claramente negativo (R < 128)


def test_normal_map_alfa_e_proxy_de_elevacao_invertido_pico_baixo_vale_alto():
    alturas = np.array([[0.0, 500.0, 1000.0], [0.0, 500.0, 1000.0], [0.0, 500.0, 1000.0]])
    rgba = codec.codificar_normal_map(alturas, passo_x_m=30.0, passo_y_m=30.0)
    assert rgba[1, 2, 3] < rgba[1, 0, 3]  # pico (maior altura, coluna 2) tem alfa menor que o vale (coluna 0)
