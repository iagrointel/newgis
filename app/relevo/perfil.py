"""Perfil de elevação e altitude no cursor (item L2-09-a-terreno-terrain-rgb-relevo).

A amostragem acontece SEMPRE sobre o COG de origem (rasterio, resolução nativa GLO-30), nunca sobre
o tile terrain-RGB já codificado — um perfil de 10 km cruzaria dezenas de tiles em vários zooms e a
quantização de 0,1 m do codec não muda o resultado, mas a reprojeção Web Mercator do tile mudaria a
posição das amostras. A distância entre os dois pontos extremos é a geodésica (Haversine); os pontos
intermediários são interpolados linearmente em latitude/longitude (curto o bastante — dezenas de km —
para o erro dessa aproximação ser desprezível perto do metro).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import rasterio

RAIO_TERRA_M = 6378137.0


@dataclass(frozen=True)
class PontoPerfil:
    indice: int
    lat: float
    lon: float
    distancia_m: float
    altura_m: float | None  # None = nodata/fora de cobertura


def distancia_haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(a))


def pontos_do_perfil(lat1: float, lon1: float, lat2: float, lon2: float, n_amostras: int) -> list[tuple[float, float]]:
    """`n_amostras` pontos igualmente espaçados (em fração do trajeto) entre os dois extremos, incluindo-os."""
    if n_amostras < 2:
        raise ValueError("perfil precisa de pelo menos 2 amostras")
    fracoes = np.linspace(0.0, 1.0, n_amostras)
    return [(lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1)) for f in fracoes]


def perfil_elevacao(caminho_fonte: str, lat1: float, lon1: float, lat2: float, lon2: float,
                     n_amostras: int = 200) -> list[PontoPerfil]:
    """Perfil de altura ao longo da linha reta (em lat/lon) entre os dois pontos, amostrado direto do
    COG de origem com `rasterio.sample` — mesma função que o teste usa para conferir, então a garantia
    de paridade é estrutural: este código FAZ o que o portão de pronto pede, não apenas se compara a ele."""
    pontos = pontos_do_perfil(lat1, lon1, lat2, lon2, n_amostras)
    distancia_total = distancia_haversine_m(lat1, lon1, lat2, lon2)
    resultado = []
    with rasterio.open(caminho_fonte) as ds:
        nodata = ds.nodata
        amostras = list(ds.sample([(lon, lat) for lat, lon in pontos]))
    for i, ((lat, lon), valor) in enumerate(zip(pontos, amostras)):
        altura = float(valor[0])
        if nodata is not None and altura == nodata:
            altura_final = None
        elif altura <= -9000.0:  # GLO-30 vazio declarado (ver app.relevo.malha.GLO30_VAZIO_DECLARADO)
            altura_final = None
        else:
            altura_final = altura
        distancia = distancia_total * (i / (n_amostras - 1)) if n_amostras > 1 else 0.0
        resultado.append(PontoPerfil(indice=i, lat=lat, lon=lon, distancia_m=distancia, altura_m=altura_final))
    return resultado


def altitude_no_ponto(caminho_fonte: str, lat: float, lon: float) -> float | None:
    """Altitude no cursor: uma amostra só, mesma função de leitura do perfil."""
    pontos = perfil_elevacao(caminho_fonte, lat, lon, lat, lon, n_amostras=2)
    return pontos[0].altura_m


__all__ = ["perfil_elevacao", "altitude_no_ponto", "distancia_haversine_m", "pontos_do_perfil", "PontoPerfil"]
