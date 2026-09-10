"""Transformação de coordenadas do serviço `/api/crs` (item L2-17-crs-transformacoes): ponto e bbox,
sempre declarando qual transformação foi usada. Datum legado (SAD69/Córrego Alegre) passa pela grade
NTv2 certa (app.crs.grades); os demais CRS curados (SIRGAS2000, WGS84, UTM, Polycônica, Web Mercator)
não têm mudança de datum — é projeção pura, feita por `pyproj.Transformer.from_crs`, a mesma máquina
que `ST_Transform` usa no Postgres (as duas falam com o mesmo PROJ 9.4.0; ver ADR 0018-crs seção 3).

Sem cache de Transformer por par de CRS aqui de propósito: `Transformer.from_crs` já é rápido (µs) e
cachear por par arbitrário (chamador escolhe os dois códigos) cresceria sem teto configurável útil."""

import math
from dataclasses import dataclass

from pyproj import Transformer

from app.crs import grades
from app.crs.grades import GRADES_POR_EPSG_ORIGEM

EPSG_SIRGAS2000 = 4674


class CRSInexistenteErro(ValueError):
    pass


class EixoSuspeitoErro(ValueError):
    """lat/long provavelmente invertidos na entrada — ver `_checar_eixos_geograficos`."""


@dataclass(frozen=True)
class ResultadoTransformacao:
    lon: float
    lat: float
    transformacao_usada: str
    cobertura: str  # "direta" | "dentro_da_grade" | "fora_da_grade_usou_parametros"


def _dentro(bounds: tuple[float, float, float, float] | None, lon: float, lat: float) -> bool:
    if bounds is None:
        return True
    w, s, e, n = bounds
    return w <= lon <= e and s <= lat <= n


def _checar_eixos_geograficos(epsg: int, lon: float, lat: float) -> None:
    """Detecta lon/lat trocados em CRS geográfico (grau). Duas checagens, na ordem:
    (1) |lat| > 90 nunca é latitude válida — se |lon| <= 90 nesse caso, a troca é óbvia.
    (2) para o Brasil (74°W-25°W, 34°S-5°N) as DUAS coordenadas cabem em [-90,90], então (1) nunca
    dispara — aqui o sinal é a ÁREA DE USO do CRS de origem (`area_of_use` do EPSG, a mesma que
    `app.crs.registro` expõe): se o ponto como veio NÃO cai na área do CRS mas o ponto TROCADO cai,
    é forte indício de eixo invertido (a alternativa seria simplesmente um ponto fora de área, que por
    si só já seria um erro de outro tipo — mas aqui distinguimos os dois porque a mensagem de erro tem
    de dizer qual é a causa provável, não só "fora de área")."""
    from app.crs.registro import obter

    d = obter(epsg)
    if not d or d.tipo != "Geographic 2D CRS":
        return
    if abs(lat) > 90 and abs(lon) <= 90:
        raise EixoSuspeitoErro(
            f"latitude {lat} fora de [-90,90] mas longitude {lon} é plausível como latitude — "
            "eixos parecem invertidos (esperado: lon, lat)"
        )
    if not _dentro(d.bounds, lon, lat) and _dentro(d.bounds, lat, lon):
        raise EixoSuspeitoErro(
            f"({lon}, {lat}) cai fora da área de uso de EPSG:{epsg} ({d.area_nome}), mas o par trocado "
            f"({lat}, {lon}) cai dentro — eixos parecem invertidos (esperado: lon, lat)"
        )


def _inversa_datum_legado(lon: float, lat: float, destino_epsg: int) -> ResultadoTransformacao:
    """SIRGAS2000 -> datum legado. Só SAD69 (4618) tem inversa suportada: `+proj=hgridshift` aceita
    `+inv` no próprio passo do pipeline, e cai nos mesmos parâmetros sem grade (invertidos) quando o
    ponto está fora da cobertura. Córrego Alegre no sentido SIRGAS2000->legado não tem consumidor nesta
    plataforma (ingestão só LÊ dado legado, nunca grava nele) — recusa explícita em vez de fingir
    suporte não testado."""
    if destino_epsg != 4618:
        raise CRSInexistenteErro(
            f"transformação SIRGAS2000 -> EPSG:{destino_epsg} (datum legado) não é suportada por este "
            "serviço no sentido inverso; ingestão só lê dado legado, nunca grava"
        )
    grade = GRADES_POR_EPSG_ORIGEM[4618][0]
    t = Transformer.from_pipeline(f"+proj=pipeline +step +inv +proj=hgridshift +grids={grade.caminho()}")
    lon2, lat2 = t.transform(lon, lat)
    if math.isfinite(lon2) and math.isfinite(lat2):
        return ResultadoTransformacao(lon2, lat2, grade.nome + " (inversa)", "dentro_da_grade")
    sem_prefixo = grades.PIPELINE_FALLBACK_SAD69[len("+proj=pipeline "):]
    t2 = Transformer.from_pipeline(f"+proj=pipeline +step +inv {sem_prefixo}")
    lon2, lat2 = t2.transform(lon, lat)
    return ResultadoTransformacao(lon2, lat2, grades.FALLBACK_NOME + " (inversa)", "fora_da_grade_usou_parametros")


def transformar_ponto(lon: float, lat: float, origem_epsg: int, destino_epsg: int) -> ResultadoTransformacao:
    _checar_eixos_geograficos(origem_epsg, lon, lat)
    if origem_epsg == destino_epsg:
        return ResultadoTransformacao(lon, lat, "identidade (mesmo CRS)", "direta")

    if origem_epsg in GRADES_POR_EPSG_ORIGEM and destino_epsg == EPSG_SIRGAS2000:
        r = grades.transformar_datum_legado(lon, lat, origem_epsg)
        return ResultadoTransformacao(r["lon"], r["lat"], r["transformacao_usada"], r["cobertura"])

    if destino_epsg in GRADES_POR_EPSG_ORIGEM and origem_epsg == EPSG_SIRGAS2000:
        return _inversa_datum_legado(lon, lat, destino_epsg)

    t = Transformer.from_crs(origem_epsg, destino_epsg, always_xy=True)
    lon2, lat2 = t.transform(lon, lat)
    if not (math.isfinite(lon2) and math.isfinite(lat2)):
        raise CRSInexistenteErro(f"PROJ não converteu EPSG:{origem_epsg} -> EPSG:{destino_epsg} para ({lon},{lat})")
    return ResultadoTransformacao(lon2, lat2, t.description, "direta")


def transformar_bbox(bbox: tuple[float, float, float, float], origem_epsg: int, destino_epsg: int) -> dict:
    """Transforma os 4 cantos do retângulo (não só os 2 pontos opostos — em projeções não conformes o
    envelope transformado não é o mesmo que transformar só min/max) e devolve o envelope resultante,
    junto com a transformação usada em cada canto (deveria ser a mesma para os 4; se não for, é sinal
    de que o bbox atravessa a borda de uma grade — a rota devolve isso explícito, não escondido)."""
    xmin, ymin, xmax, ymax = bbox
    cantos = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    resultados = [transformar_ponto(lon, lat, origem_epsg, destino_epsg) for lon, lat in cantos]
    lons = [r.lon for r in resultados]
    lats = [r.lat for r in resultados]
    transformacoes = sorted({r.transformacao_usada for r in resultados})
    return {
        "bbox": (min(lons), min(lats), max(lons), max(lats)),
        "transformacoes_usadas": transformacoes,
        "cobertura_uniforme": len(transformacoes) == 1,
    }
