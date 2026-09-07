"""Ladrilhamento do terreno (item L2-09-a-terreno-terrain-rgb-relevo).

Duas famílias de teste:
1. Geometria da grade XYZ/Web Mercator — fórmulas puras, sem GDAL, sem rede.
2. Fidelidade ponta-a-ponta contra o GLO-30 real, lido por `/vsicurl` (2 blocos Copernicus DSM que
   cobrem a região de Lorena-SP/serra da Mantiqueira, `laco/var/dem_lorena/lorena_glo30.vrt` — NÃO
   copiado para disco local, streaming puro; ver `laco/vivo/prompts/L2-09-a-terreno-terrain-rgb-relevo.md`).
   As coordenadas dos 20 pontos vêm de estações RN do IBGE (rede altimétrica oficial, WFS
   `geoservicos.ibge.gov.br/geoserver/CGED`, `tests/dados/rn_ibge_lorena.json`) — usadas aqui só como
   lista de coordenadas reais e espalhadas pelo relevo, não como aferição da acurácia absoluta do
   GLO-30 (isso pediria compensar datum vertical Imbituba × EGM2008, fora do escopo deste item).

Marcado `lento`/rede: pula sozinho se a máquina não alcançar o S3 da Copernicus (sem exigir --no-rede
manual, e sem quebrar o driver que roda offline)."""

from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.enums import Resampling

from app.relevo import codec, malha

RAIZ = Path(__file__).resolve().parents[2]
VRT_LORENA = "/home/dev/plataforma/laco/var/dem_lorena/lorena_glo30.vrt"
FIXTURE_RN = RAIZ / "tests/dados/rn_ibge_lorena.json"


def _tem_rede_s3() -> bool:
    try:
        socket.create_connection(("copernicus-dem-30m.s3.amazonaws.com", 443), timeout=4).close()
        return True
    except OSError:
        return False


pytestmark_rede = pytest.mark.skipif(not _tem_rede_s3(), reason="sem alcance ao S3 copernicus-dem-30m nesta máquina agora")


# ---------------------------------------------------------------------------- geometria pura

def test_bounds_mercator_z0_e_o_globo_inteiro():
    esquerda, baixo, direita, cima = malha.bounds_mercator(0, 0, 0)
    meio = malha.CIRCUNFERENCIA_M / 2.0
    assert esquerda == pytest.approx(-meio)
    assert direita == pytest.approx(meio)
    assert baixo == pytest.approx(-meio)
    assert cima == pytest.approx(meio)


def test_bounds_mercator_z1_quatro_quadrantes_cobrem_o_globo_sem_buraco():
    tiles = [malha.bounds_mercator(1, x, y) for x in range(2) for y in range(2)]
    esquerdas = sorted({round(t[0], 3) for t in tiles})
    direitas = sorted({round(t[2], 3) for t in tiles})
    meio = malha.CIRCUNFERENCIA_M / 2.0
    assert esquerdas[0] == pytest.approx(-meio)
    assert direitas[-1] == pytest.approx(meio)


def test_resolucao_mercator_dobra_de_zoom_em_zoom():
    r10 = malha.resolucao_mercator_m(10)
    r11 = malha.resolucao_mercator_m(11)
    assert r10 / r11 == pytest.approx(2.0)


def test_passo_em_metros_reais_e_menor_que_a_grade_bruta_fora_do_equador():
    # a grade Web Mercator estica por 1/cos(lat); a correção real tem de encolher o passo em metros
    z = 12
    n = 2**z
    y_equador = n // 2
    y_alta_lat = int(n * 0.1)  # perto do topo da grade (~lat alta)
    passo_equador = malha.passo_em_metros_reais(z, y_equador)
    passo_alta_lat = malha.passo_em_metros_reais(z, y_alta_lat)
    bruto = malha.resolucao_mercator_m(z)
    assert passo_equador == pytest.approx(bruto, rel=0.05)
    assert passo_alta_lat < bruto


def test_ladrilhos_cobertos_nao_gera_ladrilho_fora_do_bbox_da_fonte(tmp_path):
    caminho = tmp_path / "fonte.tif"
    dados = np.zeros((10, 10), dtype=np.float32)
    perfil = dict(
        driver="GTiff", height=10, width=10, count=1, dtype="float32", crs="EPSG:4326",
        transform=rasterio.transform.from_bounds(-45.2, -22.8, -45.0, -22.6, 10, 10),
    )
    with rasterio.open(caminho, "w", **perfil) as ds:
        ds.write(dados, 1)
    cobertos_z10 = malha.ladrilhos_cobertos(str(caminho), 10)
    n = 2**10
    assert 0 < len(cobertos_z10) < n * n
    for x, y in cobertos_z10:
        e, b, d, c = malha.bounds_mercator(10, x, y)
        lat_b = malha._mercator_y_para_lat(b)
        lat_c = malha._mercator_y_para_lat(c)
        lon_e = math.degrees(e / malha.RAIO_TERRA_M)
        lon_d = math.degrees(d / malha.RAIO_TERRA_M)
        assert lon_d >= -45.2 and lon_e <= -45.0
        assert lat_c >= -22.8 and lat_b <= -22.6


# ---------------------------------------------------------------------------- fidelidade contra o GLO-30 real

@pytest.fixture(scope="module")
def pontos_rn():
    return json.loads(FIXTURE_RN.read_text())["pontos"]


def _pixel_do_tile(z: int, x: int, y: int, lat: float, lon: float, tamanho: int = 256) -> tuple[int, int]:
    """Linha/coluna do pixel do ladrilho `z/x/y` mais próximo de `lat, lon` (mesma grade de `ladrilho_elevacao`)."""
    ponto_x_m = math.radians(lon) * malha.RAIO_TERRA_M
    ponto_y_m = malha.RAIO_TERRA_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    esquerda, baixo, direita, cima = malha.bounds_mercator(z, x, y, tamanho)
    col = int(round((ponto_x_m - esquerda) / (direita - esquerda) * tamanho))
    linha = int(round((cima - ponto_y_m) / (cima - baixo) * tamanho))
    return max(0, min(tamanho - 1, linha)), max(0, min(tamanho - 1, col))


def _lonlat_do_pixel(z: int, x: int, y: int, linha: int, col: int, tamanho: int = 256) -> tuple[float, float]:
    esquerda, baixo, direita, cima = malha.bounds_mercator(z, x, y, tamanho)
    ponto_x_m = esquerda + (col + 0.5) / tamanho * (direita - esquerda)
    ponto_y_m = cima - (linha + 0.5) / tamanho * (cima - baixo)
    lon = math.degrees(ponto_x_m / malha.RAIO_TERRA_M)
    lat = malha._mercator_y_para_lat(ponto_y_m)
    return lat, lon


@pytestmark_rede
def test_altura_decodificada_de_20_pontos_rn_ibge_a_menos_de_1m_do_cog(pontos_rn):
    """Portão de pronto, cláusula 1: para cada um dos 20 pontos RN, gera o ladrilho z=13 real (via
    /vsicurl no GLO-30), codifica em terrain-RGB, grava um PNG de verdade, RELÊ com PIL (não com o
    array em memória) e decodifica — depois compara com uma leitura direta e independente do MESMO
    pixel no COG por `rasterio.sample`, usando reamostragem `nearest` para que a correspondência
    pixel-a-pixel seja exata (sem mistura de vizinhos que uma bilinear introduziria)."""
    z = 13
    n = 2**z
    piores = []
    for p in pontos_rn:
        lat, lon = p["lat"], p["lon"]
        ponto_x_m = math.radians(lon) * malha.RAIO_TERRA_M
        ponto_y_m = malha.RAIO_TERRA_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        largura_tile = malha.CIRCUNFERENCIA_M / n
        x = int((ponto_x_m + malha.CIRCUNFERENCIA_M / 2) / largura_tile)
        y = int((malha.CIRCUNFERENCIA_M / 2 - ponto_y_m) / largura_tile)

        tile = malha.ladrilho_elevacao(VRT_LORENA, z, x, y, tamanho=256, reamostragem=Resampling.nearest)
        rgb = codec.codificar_terrain_rgb(tile.alturas)

        png_path = Path(f"/tmp/relevo_teste_{p['estacao']}_{z}_{x}_{y}.png")
        Image.fromarray(rgb, mode="RGB").save(png_path)
        rgb_lido = np.array(Image.open(png_path).convert("RGB"))
        png_path.unlink(missing_ok=True)

        alturas_decodificadas = codec.decodificar_terrain_rgb(rgb_lido)
        linha, col = _pixel_do_tile(z, x, y, lat, lon)
        altura_tile = alturas_decodificadas[linha, col]

        lat_pixel, lon_pixel = _lonlat_do_pixel(z, x, y, linha, col)
        with rasterio.open(VRT_LORENA) as ds:
            valor_cog = list(ds.sample([(lon_pixel, lat_pixel)]))[0][0]

        assert not np.isnan(altura_tile), f"{p['estacao']}: pixel do tile ficou nodata"
        diferenca = abs(float(altura_tile) - float(valor_cog))
        piores.append((p["estacao"], diferenca))
        assert diferenca <= 1.0, f"{p['estacao']}: tile={altura_tile:.2f} cog={valor_cog:.2f} diff={diferenca:.2f} m"

    pior = max(piores, key=lambda t: t[1])
    assert pior[1] <= 1.0


@pytestmark_rede
def test_degrau_entre_tiles_vizinhos_menor_que_5m_em_area_plana():
    """Portão de pronto, cláusula 2 (e refutação do adversário): varredura automatizada da borda entre
    dois ladrilhos vizinhos numa área plana medida de verdade (vale do rio Paraíba do Sul perto de
    Lorena-SP, desvio-padrão de altura ≈ 1,7 m numa janela de 2×2 km — ver nota de descoberta desta
    coordenada no commit). Gera os dois ladrilhos z=14 lado a lado direto do GLO-30, decodifica a
    coluna/linha da borda comum de cada um e mede o maior desnível entre pixels que deveriam ser quase
    o mesmo ponto do terreno."""
    lat_area, lon_area = -22.72, -45.16
    z = 14
    n = 2**z
    ponto_x_m = math.radians(lon_area) * malha.RAIO_TERRA_M
    ponto_y_m = malha.RAIO_TERRA_M * math.log(math.tan(math.pi / 4 + math.radians(lat_area) / 2))
    largura_tile = malha.CIRCUNFERENCIA_M / n
    x = int((ponto_x_m + malha.CIRCUNFERENCIA_M / 2) / largura_tile)
    y = int((malha.CIRCUNFERENCIA_M / 2 - ponto_y_m) / largura_tile)

    tile_a = malha.ladrilho_elevacao(VRT_LORENA, z, x, y, tamanho=256)
    tile_b_leste = malha.ladrilho_elevacao(VRT_LORENA, z, x + 1, y, tamanho=256)
    tile_b_sul = malha.ladrilho_elevacao(VRT_LORENA, z, x, y + 1, tamanho=256)

    borda_direita_a = tile_a.alturas[:, -1]
    borda_esquerda_b = tile_b_leste.alturas[:, 0]
    borda_baixo_a = tile_a.alturas[-1, :]
    borda_cima_b = tile_b_sul.alturas[0, :]

    validos_h = ~np.isnan(borda_direita_a) & ~np.isnan(borda_esquerda_b)
    validos_v = ~np.isnan(borda_baixo_a) & ~np.isnan(borda_cima_b)
    assert validos_h.sum() > 200, "cobertura insuficiente na borda horizontal para o teste valer"
    assert validos_v.sum() > 200, "cobertura insuficiente na borda vertical para o teste valer"

    degrau_h = np.max(np.abs(borda_direita_a[validos_h] - borda_esquerda_b[validos_h]))
    degrau_v = np.max(np.abs(borda_baixo_a[validos_v] - borda_cima_b[validos_v]))

    assert degrau_h <= 5.0, f"degrau horizontal de {degrau_h:.2f} m entre tile ({x},{y}) e ({x+1},{y})"
    assert degrau_v <= 5.0, f"degrau vertical de {degrau_v:.2f} m entre tile ({x},{y}) e ({x},{y+1})"
