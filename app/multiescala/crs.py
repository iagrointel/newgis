"""CRS de trabalho das grades: UTM SIRGAS 2000 da zona do centróide da área de estudo.

Decisão A7 de `laco/decomposicao/L3L6_CONCEITO.md`: grade em CRS métrico, nunca em 4326 nem em Web Mercator
(que distorce área com a latitude). O motor logístico da casa usa hexágono de 250 m em EPSG:31983 e o motor de
LT usa grade de 100 m em EPSG:31984 — os dois são UTM SIRGAS 2000.

Códigos EPSG (conferidos em `spatial_ref_sys` desta instalação, 21 linhas entre 31965 e 31985):
  zona 11N..22N -> 31965 + (zona - 11)   ->  31965..31976
  zona 17S..25S -> 31977 + (zona - 17)   ->  31977..31985
Fora dessas faixas a área não é coberta pelo SIRGAS 2000 em UTM e o motor recusa, em vez de escolher uma zona
vizinha em silêncio.
"""

from app.erros import ErroAPI

ZONA_NORTE_MIN, ZONA_NORTE_MAX, BASE_NORTE = 11, 22, 31965
ZONA_SUL_MIN, ZONA_SUL_MAX, BASE_SUL = 17, 25, 31977
SRID_MIN, SRID_MAX = 31965, 31985


def zona_utm(lon: float) -> int:
    """Zona UTM de uma longitude em graus decimais (1 a 60)."""
    if not -180.0 <= lon <= 180.0:
        raise ErroAPI(422, "longitude_invalida", f"longitude fora do intervalo geográfico: {lon}")
    return min(60, int((lon + 180.0) // 6.0) + 1)


def srid_de(lon: float, lat: float) -> int:
    """EPSG do UTM SIRGAS 2000 do ponto; erro nomeado quando o ponto está fora da cobertura."""
    if not -90.0 <= lat <= 90.0:
        raise ErroAPI(422, "latitude_invalida", f"latitude fora do intervalo geográfico: {lat}")
    zona = zona_utm(lon)
    if lat >= 0:
        if not ZONA_NORTE_MIN <= zona <= ZONA_NORTE_MAX:
            raise ErroAPI(
                422, "fora_da_cobertura_sirgas",
                f"zona UTM {zona}N não tem código SIRGAS 2000 (norte vai de {ZONA_NORTE_MIN}N a {ZONA_NORTE_MAX}N)",
            )
        return BASE_NORTE + (zona - ZONA_NORTE_MIN)
    if not ZONA_SUL_MIN <= zona <= ZONA_SUL_MAX:
        raise ErroAPI(
            422, "fora_da_cobertura_sirgas",
            f"zona UTM {zona}S não tem código SIRGAS 2000 (sul vai de {ZONA_SUL_MIN}S a {ZONA_SUL_MAX}S)",
        )
    return BASE_SUL + (zona - ZONA_SUL_MIN)


def nome_do_srid(srid: int) -> str:
    """Nome legível do CRS de trabalho, montado do próprio código (sem consultar o banco)."""
    if BASE_NORTE <= srid <= BASE_NORTE + (ZONA_NORTE_MAX - ZONA_NORTE_MIN):
        return f"SIRGAS 2000 / UTM zone {srid - BASE_NORTE + ZONA_NORTE_MIN}N"
    if BASE_SUL <= srid <= BASE_SUL + (ZONA_SUL_MAX - ZONA_SUL_MIN):
        return f"SIRGAS 2000 / UTM zone {srid - BASE_SUL + ZONA_SUL_MIN}S"
    raise ErroAPI(422, "srid_fora_da_faixa", f"EPSG:{srid} não é UTM SIRGAS 2000")
