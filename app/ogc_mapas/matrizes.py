"""TileMatrixSet do WMTS (item L2-04-i). Só `GoogleMapsCompatible` (OGC 07-057r7, anexo E.4): é o que
QGIS, ArcGIS Pro e AGOL entendem sem configuração, e é a mesma grade dos tiles XYZ do visualizador —
assim um tile do WMTS e um tile do mapa da casa cobrem exatamente a mesma caixa.

Números da especificação, não inventados: origem no canto superior esquerdo do mundo em EPSG:3857
(-20037508.342789244, 20037508.342789244), tile de 256 px, `pixelSpan` do nível 0 = 156543.033928041 m,
e o denominador de escala do OGC usa o pixel padronizado de 0,28 mm (`pixelSpan / 0.00028`).
"""

from __future__ import annotations

# semieixo maior do WGS 84 esférico usado pelo EPSG:3857 (a mesma constante do PostGIS/PROJ)
RAIO = 6378137.0
LIMITE = 20037508.342789244
TAMANHO_TILE = 256
PIXEL_OGC_M = 0.00028  # metro por pixel padronizado (OGC 07-057r7, 6.1)
ZOOM_MAX = 22
IDENTIFICADOR = "GoogleMapsCompatible"
CRS_TILE = "EPSG:3857"


def pixel_span(z: int) -> float:
    """Metros por pixel no nível `z` (2 * LIMITE / (256 * 2^z))."""
    return (2 * LIMITE) / (TAMANHO_TILE * (2 ** z))


def denominador_escala(z: int) -> float:
    return pixel_span(z) / PIXEL_OGC_M


def matrizes(z_min: int = 0, z_max: int = ZOOM_MAX) -> list[dict]:
    """Uma entrada por nível: identificador, denominador de escala, canto superior esquerdo e o número
    de tiles em cada direção (2^z x 2^z, a grade quadrada do GoogleMapsCompatible)."""
    saida = []
    for z in range(z_min, z_max + 1):
        saida.append({
            "identificador": str(z),
            "denominador_escala": denominador_escala(z),
            "canto_superior_esquerdo": (-LIMITE, LIMITE),
            "largura_tile": TAMANHO_TILE,
            "altura_tile": TAMANHO_TILE,
            "colunas": 2 ** z,
            "linhas": 2 ** z,
        })
    return saida


def caixa_do_tile(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Caixa (minx, miny, maxx, maxy) do tile em EPSG:3857. `y` cresce para o SUL (linha da matriz WMTS,
    igual ao XYZ do OSM/Google — a diferença de convenção com o TMS é justamente esta)."""
    n = 2 ** z
    passo = (2 * LIMITE) / n
    minx = -LIMITE + x * passo
    maxy = LIMITE - y * passo
    return (minx, maxy - passo, minx + passo, maxy)


def valido(z: int, x: int, y: int, z_min: int = 0, z_max: int = ZOOM_MAX) -> bool:
    if not (z_min <= z <= z_max):
        return False
    n = 2 ** z
    return 0 <= x < n and 0 <= y < n


def tiles_da_caixa(caixa: tuple[float, float, float, float], z: int) -> list[tuple[int, int]]:
    """Tiles (x, y) do nível `z` que tocam a caixa em 3857 — usado pelo job de pré-renderização."""
    n = 2 ** z
    passo = (2 * LIMITE) / n
    minx, miny, maxx, maxy = caixa
    x0 = max(0, int((minx + LIMITE) // passo))
    x1 = min(n - 1, int((maxx + LIMITE) // passo))
    y0 = max(0, int((LIMITE - maxy) // passo))
    y1 = min(n - 1, int((LIMITE - miny) // passo))
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
