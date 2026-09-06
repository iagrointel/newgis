"""Isócrona por matriz + casco côncavo (C16/item L2-11-c-rota-matriz-isocrona; decisão do L2_CONCEITO: o
OSRM não tem serviço de isócrona nativo — a doc testada só lista route/table/nearest/match/trip/tile).
Grade de pontos ao redor do centro, tempo de cada um pedido de uma vez ao `/table` (1 fonte × N destinos),
polígono = casco côncavo (`shapely.concave_hull`) sobre os pontos alcançáveis dentro do orçamento de
tempo. Limite declarado: a grade nunca passa de `PLAT_ROTA_ISOCRONA_MAX_PONTOS` (teto de tabela do OSRM
de teste); área muito maior que o recorte de Guarulhos sai truncada pela borda do grafo (documentado)."""

import math

from shapely import MultiPoint, concave_hull
from shapely.geometry import mapping

from app import limites
from app.rede import osrm
from app.settings import settings

M_POR_GRAU_LAT = 111_320.0
VELOCIDADE_GUIA_KMH = 40.0  # estimativa inicial de raio (não é limite físico; só ponto de partida da grade)
MARGEM_RAIO = 1.5


def _m_por_grau_lon(lat: float) -> float:
    return M_POR_GRAU_LAT * math.cos(math.radians(lat))


def _raio_inicial_km(minutos: float) -> float:
    return (minutos / 60.0) * VELOCIDADE_GUIA_KMH * MARGEM_RAIO


def _resolucao_para(raio_km: float, max_pontos: int) -> float:
    """Resolução (m) tal que a grade quadrada sobre o círculo de raio `raio_km` fique <= max_pontos
    (fração círculo/quadrado ~ pi/4); nunca abaixo de 50 m nem acima de 2.000 m."""
    area_m2 = math.pi * (raio_km * 1000) ** 2
    resolucao = math.sqrt(area_m2 * (math.pi / 4) / max(max_pontos, 4))
    return min(max(resolucao, 50.0), 2000.0)


def gerar_grade(centro: list[float], raio_km: float, resolucao_m: float) -> list[list[float]]:
    lon0, lat0 = centro
    passo_lat = resolucao_m / M_POR_GRAU_LAT
    passo_lon = resolucao_m / _m_por_grau_lon(lat0)
    n = max(int(raio_km * 1000 / resolucao_m), 1)
    pontos = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dist_m = math.hypot(i * resolucao_m, j * resolucao_m)
            if dist_m <= raio_km * 1000:
                pontos.append([lon0 + j * passo_lon, lat0 + i * passo_lat])
    return pontos


def _alcancaveis(centro: list[float], grade: list[list[float]], perfil: str, orcamento_s: float):
    resultado = osrm.tabela_1_para_n(centro, grade, perfil)
    duracoes = resultado["durations"][0]
    return [grade[i] for i, d in enumerate(duracoes) if d is not None and d <= orcamento_s]


def calcular(centro: list[float], minutos: float, perfil: str, ratio: float | None = None) -> dict:
    """Devolve {poligono (GeoJSON), grade: {...}}. Duas rodadas no máximo: a 1ª com o raio-guia; se mais
    de 15 % dos pontos da BORDA da grade ainda estiverem alcançáveis (sinal de que o raio-guia subestimou
    o alcance real), a 2ª dobra o raio uma única vez (teto: a grade nunca ultrapassa
    PLAT_ROTA_ISOCRONA_MAX_PONTOS em nenhuma rodada)."""
    max_pontos = settings.PLAT_ROTA_ISOCRONA_MAX_PONTOS
    orcamento_s = minutos * 60.0
    ratio = limites.ROTA_ISOCRONA_RATIO_PADRAO if ratio is None else ratio

    raio_km = _raio_inicial_km(minutos)
    resolucao_m = _resolucao_para(raio_km, max_pontos)
    grade = gerar_grade(centro, raio_km, resolucao_m)

    alcancaveis = _alcancaveis(centro, grade, perfil, orcamento_s)

    raio_m = raio_km * 1000
    na_borda = [p for p in grade if math.hypot((p[0] - centro[0]) * _m_por_grau_lon(centro[1]),
                                                (p[1] - centro[1]) * M_POR_GRAU_LAT) >= raio_m * 0.85]
    alcancaveis_na_borda = [p for p in na_borda if p in alcancaveis]
    expandido = False
    if na_borda and len(alcancaveis_na_borda) / len(na_borda) > 0.15:
        expandido = True
        raio_km *= 2.0
        resolucao_m = _resolucao_para(raio_km, max_pontos)
        grade = gerar_grade(centro, raio_km, resolucao_m)
        alcancaveis = _alcancaveis(centro, grade, perfil, orcamento_s)

    info_grade = {
        "resolucao_m": round(resolucao_m, 1),
        "raio_km": round(raio_km, 2),
        "pontos_amostrados": len(grade),
        "pontos_alcancaveis": len(alcancaveis),
        "raio_expandido": expandido,
        "ratio_casco": ratio,
    }

    if len(alcancaveis) < 3:
        return {"poligono": None, "grade": info_grade}

    mp = MultiPoint(alcancaveis)
    casco = concave_hull(mp, ratio=ratio, allow_holes=False)
    if casco.geom_type not in ("Polygon", "MultiPolygon"):
        casco = mp.convex_hull
    return {"poligono": mapping(casco), "grade": info_grade}
