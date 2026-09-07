"""Codificadores/decodificadores de altura em RGB, em numpy puro (sem GDAL, sem reamostragem).

Cada função opera sobre um array 2D de alturas em metros (`float64`/`float32`) e devolve um array
`uint8` de forma `(altura, largura, 3)` (ou o inverso na decodificação). O nodata do array de
entrada é tratado ANTES de chamar o codificador (ver `job.py`): aqui a única regra é que um pixel
sem dado chega como `numpy.nan` e sai como preto puro `(0, 0, 0)`, que nenhuma das duas fórmulas
produz para um valor de altura real dentro da faixa aceita — então o preto puro é um marcador
inequívoco de nodata na decodificação.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------- terrain-RGB (Mapbox)
# altura = -10000 + (R*65536 + G*256 + B) * 0,1  →  passo de 0,1 m, faixa útil ≈ -10000 m a 1.667.721,5 m
TERRAIN_RGB_OFFSET = -10000.0
TERRAIN_RGB_PASSO = 0.1
TERRAIN_RGB_MAX_INTEIRO = 2**24 - 1

# ---------------------------------------------------------------------------- Terrarium (Mapzen)
# altura = (R*256 + G + B/256) - 32768  →  passo de 1/256 m, faixa -32768 m a 32768 m
TERRARIUM_OFFSET = -32768.0
TERRARIUM_PASSO_INVERSO = 256.0  # valor_inteiro = (altura - OFFSET) * PASSO_INVERSO
TERRARIUM_MAX_INTEIRO = 2**24 - 1

NODATA_RGB = (0, 0, 0)


def _empacotar(valor_inteiro: np.ndarray) -> np.ndarray:
    """Um inteiro de 24 bits (0..2^24-1) por pixel -> 3 canais uint8 (R = byte mais significativo)."""
    r = (valor_inteiro >> 16) & 0xFF
    g = (valor_inteiro >> 8) & 0xFF
    b = valor_inteiro & 0xFF
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def _desempacotar(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0].astype(np.int64)
    g = rgb[..., 1].astype(np.int64)
    b = rgb[..., 2].astype(np.int64)
    return (r << 16) | (g << 8) | b


def codificar_terrain_rgb(alturas: np.ndarray) -> np.ndarray:
    """Alturas (metros, `nan` = sem dado) -> RGB Mapbox terrain-RGB. Satura na faixa representável
    em vez de estourar (avisa a chamadora via `avisos_saturacao`, ver `job.py`)."""
    sem_dado = np.isnan(alturas)
    seguro = np.nan_to_num(alturas, nan=0.0)
    valor = np.round((seguro - TERRAIN_RGB_OFFSET) / TERRAIN_RGB_PASSO)
    valor = np.clip(valor, 0, TERRAIN_RGB_MAX_INTEIRO).astype(np.int64)
    rgb = _empacotar(valor)
    rgb[sem_dado] = NODATA_RGB
    return rgb


def decodificar_terrain_rgb(rgb: np.ndarray) -> np.ndarray:
    """RGB Mapbox terrain-RGB -> alturas (metros, `nan` onde o pixel é preto puro = nodata)."""
    valor = _desempacotar(rgb)
    alturas = TERRAIN_RGB_OFFSET + valor.astype(np.float64) * TERRAIN_RGB_PASSO
    nodata = (rgb[..., 0] == 0) & (rgb[..., 1] == 0) & (rgb[..., 2] == 0)
    alturas = np.where(nodata, np.nan, alturas)
    return alturas


def codificar_terrarium(alturas: np.ndarray) -> np.ndarray:
    """Alturas -> RGB Terrarium (Mapzen), entrada exigida pelo `convert_to_contour` do Martin."""
    sem_dado = np.isnan(alturas)
    seguro = np.nan_to_num(alturas, nan=0.0)
    valor = np.round((seguro - TERRARIUM_OFFSET) * TERRARIUM_PASSO_INVERSO)
    valor = np.clip(valor, 0, TERRARIUM_MAX_INTEIRO).astype(np.int64)
    rgb = _empacotar(valor)
    rgb[sem_dado] = NODATA_RGB
    return rgb


def decodificar_terrarium(rgb: np.ndarray) -> np.ndarray:
    valor = _desempacotar(rgb)
    alturas = TERRARIUM_OFFSET + valor.astype(np.float64) / TERRARIUM_PASSO_INVERSO
    nodata = (rgb[..., 0] == 0) & (rgb[..., 1] == 0) & (rgb[..., 2] == 0)
    return np.where(nodata, np.nan, alturas)


# ---------------------------------------------------------------------------- normal map (Mapzen "normal")
# Formato exigido pelo `convert_to_hillshade` do Martin 1.15 (lido em martin-core/src/tiles/hillshade/
# shade.rs, `Canvas::texel`): nx = R/255*2-1, ny = G/255*2-1, nz reconstruído por sqrt(1-nx²-ny²); o
# canal azul NÃO é lido pelo bake (só nx/ny/alfa importam), alfa é usado como proxy de elevação para
# o ganho de `elevation_scale` (1 = nível do mar do recorte, 0 = pico do recorte, ver `_alfa_elevacao`).
def _gradiente_metros(alturas: np.ndarray, passo_x_m: float, passo_y_m: float) -> tuple[np.ndarray, np.ndarray]:
    """dz/dx, dz/dy em metros por metro, por diferença central (Horn simplificado)."""
    dzdy, dzdx = np.gradient(alturas, passo_y_m, passo_x_m)
    return dzdx, dzdy


def _alfa_elevacao(alturas: np.ndarray) -> np.ndarray:
    """Proxy de elevação normalizado ao recorte: 0 no pico, 1 no vale (documentado no bake: `1 - alpha`
    é o proxy). Recorte sem variação (plano) devolve 0,5 constante."""
    validas = alturas[~np.isnan(alturas)]
    if validas.size == 0:
        return np.zeros_like(alturas)
    minimo, maximo = float(validas.min()), float(validas.max())
    faixa = maximo - minimo
    if faixa < 1e-6:
        return np.full_like(alturas, 0.5)
    normalizado = (alturas - minimo) / faixa
    return 1.0 - normalizado


def codificar_normal_map(alturas: np.ndarray, passo_x_m: float, passo_y_m: float) -> np.ndarray:
    """Alturas -> RGBA normal-map Mapzen. `passo_x_m`/`passo_y_m` é a resolução do pixel EM METROS
    (não em graus — quem chama já projetou ou convertido por latitude, ver `job.py::_passo_em_metros`).
    """
    dzdx, dzdy = _gradiente_metros(np.nan_to_num(alturas, nan=0.0), passo_x_m, passo_y_m)
    # normal de uma superfície z=f(x,y): (-dz/dx, -dz/dy, 1), normalizada.
    nx, ny, nz = -dzdx, -dzdy, np.ones_like(dzdx)
    comprimento = np.sqrt(nx**2 + ny**2 + nz**2)
    comprimento = np.where(comprimento < 1e-9, 1.0, comprimento)
    nx, ny, nz = nx / comprimento, ny / comprimento, nz / comprimento
    r = np.clip(np.round((nx + 1.0) / 2.0 * 255.0), 0, 255).astype(np.uint8)
    g = np.clip(np.round((ny + 1.0) / 2.0 * 255.0), 0, 255).astype(np.uint8)
    b = np.clip(np.round((nz + 1.0) / 2.0 * 255.0), 0, 255).astype(np.uint8)
    alfa = np.nan_to_num(_alfa_elevacao(alturas), nan=0.0)
    a = np.clip(np.round(alfa * 255.0), 0, 255).astype(np.uint8)
    return np.stack([r, g, b, a], axis=-1)


__all__ = [
    "codificar_terrain_rgb", "decodificar_terrain_rgb",
    "codificar_terrarium", "decodificar_terrarium",
    "codificar_normal_map",
    "TERRAIN_RGB_OFFSET", "TERRAIN_RGB_PASSO",
]
