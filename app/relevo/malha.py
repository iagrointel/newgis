"""Ladrilhamento: lê o MDT/MDS de origem (GLO-30 ou outro, em qualquer CRS que o GDAL abra) e produz
o ladrilho XYZ em Web Mercator (EPSG:3857), UMA vez por zoom, direto da fonte — nunca reamostrando
um ladrilho de zoom vizinho já codificado (regra da casa: terrain-RGB nunca reamostrado). A única
reamostragem que existe é a reprojeção geográfica → Web Mercator que o próprio MapLibre exigiria de
qualquer fonte raster nessa grade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

WEBMERCATOR = "EPSG:3857"
GEOGRAFICO = "EPSG:4326"
RAIO_TERRA_M = 6378137.0
CIRCUNFERENCIA_M = 2 * math.pi * RAIO_TERRA_M

# GLO-30 usa vazio -9999 nas bordas de cobertura (mar/sem dado) em parte dos blocos; o metadado do
# COG às vezes não declara `nodata` (medido nesta trilha: `None` no S23_00_W046_00), então o valor é
# tratado aqui como constante declarada, não lido do arquivo.
GLO30_VAZIO_DECLARADO = -9999.0


def bounds_mercator(z: int, x: int, y: int, tamanho: int = 256) -> tuple[float, float, float, float]:
    """Bordas (esquerda, baixo, direita, cima) do ladrilho XYZ em metros Web Mercator, sem depender
    de biblioteca externa de teselas (fórmula padrão da grade Google/OSM/MapLibre)."""
    n = 2**z
    meio = CIRCUNFERENCIA_M / 2.0
    largura_tile = CIRCUNFERENCIA_M / n
    esquerda = -meio + x * largura_tile
    direita = esquerda + largura_tile
    cima = meio - y * largura_tile
    baixo = cima - largura_tile
    return esquerda, baixo, direita, cima


def resolucao_mercator_m(z: int, tamanho: int = 256) -> float:
    """Metros por pixel da grade Web Mercator neste zoom (uniforme; a correção de latitude para
    metros REAIS no solo é feita à parte, ver `passo_em_metros_reais`)."""
    return CIRCUNFERENCIA_M / (2**z * tamanho)


def passo_em_metros_reais(z: int, y: int, tamanho: int = 256) -> float:
    """Metros por pixel no SOLO no centro do ladrilho (a grade Web Mercator estica por 1/cos(lat);
    sem esta correção o gradiente do mapa de normais fica errado em latitudes distantes do equador)."""
    _, baixo, _, cima = bounds_mercator(z, 0, y, tamanho)
    lat_central = _mercator_y_para_lat((baixo + cima) / 2.0)
    return resolucao_mercator_m(z, tamanho) * math.cos(math.radians(lat_central))


def _mercator_y_para_lat(y_m: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y_m / RAIO_TERRA_M)) - math.pi / 2)


@dataclass(frozen=True)
class LadrilhoElevacao:
    alturas: np.ndarray  # (tamanho, tamanho), float64, nan = sem dado
    z: int
    x: int
    y: int
    tamanho: int
    fracao_valida: float  # 0..1 — usada pelo adversário para separar "fora de cobertura" de nodata real


def ladrilho_elevacao(caminho_fonte: str, z: int, x: int, y: int, tamanho: int = 256,
                       reamostragem: Resampling = Resampling.bilinear,
                       vazio_declarado: float | None = GLO30_VAZIO_DECLARADO) -> LadrilhoElevacao:
    """Lê `caminho_fonte` (caminho local, `/vsicurl/...` ou VRT) e devolve as alturas do ladrilho XYZ
    `z/x/y` já em Web Mercator. Uma única reprojeção, direto da fonte."""
    esquerda, baixo, direita, cima = bounds_mercator(z, x, y, tamanho)
    destino_transform = from_bounds(esquerda, baixo, direita, cima, tamanho, tamanho)
    destino = np.full((tamanho, tamanho), np.nan, dtype=np.float64)
    with rasterio.open(caminho_fonte) as ds:
        origem = ds.read(1).astype(np.float64)
        if vazio_declarado is not None:
            origem[origem == vazio_declarado] = np.nan
        if ds.nodata is not None:
            origem[origem == ds.nodata] = np.nan
        reproject(
            source=origem,
            destination=destino,
            src_transform=ds.transform,
            src_crs=ds.crs,
            dst_transform=destino_transform,
            dst_crs=WEBMERCATOR,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=reamostragem,
        )
    fracao_valida = float(np.mean(~np.isnan(destino)))
    return LadrilhoElevacao(alturas=destino, z=z, x=x, y=y, tamanho=tamanho, fracao_valida=fracao_valida)


def ladrilhos_cobertos(caminho_fonte: str, z: int) -> list[tuple[int, int]]:
    """Lista (x, y) dos ladrilhos deste zoom cujo bbox intersecta o bbox da fonte (evita gerar
    ladrilho 100% nodata no meio do oceano)."""
    with rasterio.open(caminho_fonte) as ds:
        oeste, sul, leste, norte = ds.bounds
    n = 2**z
    resultado = []
    for x in range(n):
        for y in range(n):
            e, b, d, c = bounds_mercator(z, x, y)
            lat_b, lat_c = _mercator_y_para_lat(b), _mercator_y_para_lat(c)
            lon_e = math.degrees(e / RAIO_TERRA_M)
            lon_d = math.degrees(d / RAIO_TERRA_M)
            if lon_d < oeste or lon_e > leste or lat_c < sul or lat_b > norte:
                continue
            resultado.append((x, y))
    return resultado


__all__ = [
    "bounds_mercator", "resolucao_mercator_m", "passo_em_metros_reais",
    "ladrilho_elevacao", "ladrilhos_cobertos", "LadrilhoElevacao", "GLO30_VAZIO_DECLARADO",
]
