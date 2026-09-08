"""Sombra projetada de extrusões (prismas verticais) por data e hora (item L2-09-d).

APROXIMAÇÃO DECLARADA (repetida na resposta): cada extrusão é um PRISMA VERTICAL — o polígono da base
erguido até `altura_m`; a superfície de projeção é PLANA (o relevo não curva a sombra); a posição do
Sol vem do algoritmo NOAA (`app/analise3d/sol.py`, refração de Saemundsson; aproximação de 0,01°).
A sombra de um prisma sob Sol a `elevação` com azimute `a` é a união (shapely):

  base ∪ base deslocada por L na direção da sombra ∪ (um quadrilátero por aresta, varrido pelo
  deslocamento),  onde L = altura / tan(elevação) e a direção da sombra é a + 180°.

Quando o Sol está no zênite exato (elevação 90°, tan infinito) não há sombra lateral: a união é a
própria base e `comprimento_sombra_m` = 0. Sol abaixo do horizonte (elevação <= 0) não projeta
sombra utilizável: a rota recusa com 422.
"""

import math

from shapely.affinity import translate
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union


def deslocamento_da_sombra(azimute_sol_graus: float, comprimento_m: float) -> tuple[float, float]:
    """Vetor (dx, dy) no SRID da análise: direção OPOSTA ao Sol (x = leste, y = norte)."""
    az = math.radians((azimute_sol_graus + 180.0) % 360.0)
    return (comprimento_m * math.sin(az), comprimento_m * math.cos(az))


def sombra_do_solido(
    poligono_geojson: dict, altura_m: float, azimute_sol_graus: float, elevacao_sol_graus: float
) -> dict:
    """Sombra de um prisma: GeoJSON do polígono de sombra + comprimento teórico (altura/tan elevação)."""
    if elevacao_sol_graus <= 0.0:
        raise ValueError("Sol abaixo do horizonte não projeta sombra utilizável")
    if elevacao_sol_graus >= 90.0:
        comprimento = 0.0
    else:
        comprimento = altura_m / math.tan(math.radians(elevacao_sol_graus))

    base = shape(poligono_geojson)
    if base.is_empty:
        raise ValueError("polígono vazio")
    dx, dy = deslocamento_da_sombra(azimute_sol_graus, comprimento)
    pecas = [base, translate(base, dx, dy)]
    coords = list(base.exterior.coords)
    for (x0, y0), (x1, y1) in zip(coords, coords[1:], strict=False):
        quad = [
            (x0, y0),
            (x1, y1),
            (x1 + dx, y1 + dy),
            (x0 + dx, y0 + dy),
            (x0, y0),
        ]
        pecas.append(Polygon(quad))
    sombra = unary_union(pecas)
    return {
        "sombra_geojson": sombra.__geo_interface__,
        "comprimento_sombra_m": comprimento,
        "direcao_sombra_graus": (azimute_sol_graus + 180.0) % 360.0,
    }
