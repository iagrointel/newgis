"""CRS de trabalho do conjunto de unidades (decisão A7 do L3L6_CONCEITO): UTM SIRGAS 2000 da zona do centróide da área
de estudo, sempre gravado (`srid_trabalho`) e sempre declarado com a distorção de área medida por pyproj sobre pontos
da própria área — nunca escondido. Fora da cobertura do SIRGAS 2000 / UTM (zonas 17S-25S e 18N-22N, EPSG 31977-31985 e
31972-31976) a API recusa com 422. Cálculo puro (sem banco): pyproj 3.7 `Proj.get_factors` dá o fator de escala de
área (`areal_scale`) ponto a ponto; distorção = (areal_scale − 1) × 100 %."""

import math

import pyproj

# EPSG do SIRGAS 2000 / UTM: sul 17S..25S = 31977..31985 (31960 + zona); norte 18N..22N = 31972..31976 (31954 + zona)
ZONAS_SUL = range(17, 26)
ZONAS_NORTE = range(18, 23)
AMOSTRA_MAX = 400  # pontos da área usados na medição da distorção (vértices + cantos do bbox + centróide)


def zona_utm(lon: float) -> int:
    return int(math.floor((lon + 180.0) / 6.0)) + 1


def srid_utm_sirgas(lon: float, lat: float) -> tuple[int, int, str]:
    """(srid, zona, hemisfério) para o ponto; ValueError fora da cobertura brasileira do SIRGAS 2000 / UTM."""
    z = zona_utm(lon)
    if lat < 0:
        if z not in ZONAS_SUL:
            raise ValueError(f"zona UTM {z}S fora da cobertura SIRGAS 2000 (17S a 25S)")
        return 31960 + z, z, "S"
    if z not in ZONAS_NORTE:
        raise ValueError(f"zona UTM {z}N fora da cobertura SIRGAS 2000 (18N a 22N)")
    return 31954 + z, z, "N"


def meridiano_central(zona: int) -> float:
    return -183.0 + 6.0 * zona


def _amostra(pontos: list[tuple[float, float]], bbox: tuple[float, float, float, float],
             centroide: tuple[float, float]) -> list[tuple[float, float]]:
    xmin, ymin, xmax, ymax = bbox
    base = [centroide, (xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax),
            (xmin, centroide[1]), (xmax, centroide[1]), (centroide[0], ymin), (centroide[0], ymax)]
    if len(pontos) > AMOSTRA_MAX:
        passo = max(1, len(pontos) // AMOSTRA_MAX)
        pontos = pontos[::passo]
    return base + list(pontos)


def ficha_crs(pontos: list[tuple[float, float]], bbox: tuple[float, float, float, float],
              centroide: tuple[float, float]) -> dict:
    """Escolhe o CRS pela zona do centróide e mede a distorção de área nos pontos da área (A7). Devolve a parte da
    ficha do conjunto que descreve o CRS: srid, nome, zona, hemisfério, meridiano central, distorção mínima/máxima
    em % (assinada: > 0 = a área no plano é maior que a geodésica), zonas UTM cobertas pela área e aviso quando ela
    cruza mais de uma zona ou se afasta mais de 3° do meridiano central."""
    lon0, lat0 = centroide
    srid, zona, hemisferio = srid_utm_sirgas(lon0, lat0)
    crs = pyproj.CRS.from_epsg(srid)
    proj = pyproj.Proj(crs)
    escalas = []
    for lon, lat in _amostra(pontos, bbox, centroide):
        f = proj.get_factors(lon, lat)
        if math.isfinite(f.areal_scale):
            escalas.append(f.areal_scale)
    dist_min = (min(escalas) - 1.0) * 100.0
    dist_max = (max(escalas) - 1.0) * 100.0
    xmin, _ymin, xmax, _ymax = bbox
    zonas = sorted({zona_utm(xmin), zona_utm(xmax), zona})
    mc = meridiano_central(zona)
    afastamento = max(abs(xmin - mc), abs(xmax - mc))
    avisos = []
    if len(zonas) > 1:
        avisos.append(
            f"a área cruza {len(zonas)} zonas UTM ({', '.join(str(z) for z in zonas)}); todo o conjunto usa a zona "
            f"{zona}{hemisferio} do centróide, com a distorção de área declarada acima"
        )
    if afastamento > 3.0:
        avisos.append(f"a área chega a {afastamento:.2f}° do meridiano central {mc:.0f}° (mais de 3°): a distorção de "
                      f"área cresce com o afastamento; a área geodésica de cada unidade não depende disso")
    return {
        "srid_trabalho": srid,
        "crs_nome": crs.name,
        "zona_utm": zona,
        "hemisferio": hemisferio,
        "meridiano_central": mc,
        "centroide": [round(lon0, 6), round(lat0, 6)],
        "distorcao_area_min_pct": round(dist_min, 4),
        "distorcao_area_max_pct": round(dist_max, 4),
        "distorcao_area_max_abs_pct": round(max(abs(dist_min), abs(dist_max)), 4),
        "pontos_amostrados": len(escalas),
        "zonas_utm_cobertas": zonas,
        "cruza_zonas_utm": len(zonas) > 1,
        "avisos": avisos,
        "metodo": "pyproj Proj.get_factors(lon, lat).areal_scale em vértices da área + cantos do bbox + centróide; "
                  "área das unidades sempre geodésica (ST_Area(geography), GRS80)",
    }
