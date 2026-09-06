"""Item L3-01-b: escolha do CRS de trabalho e declaração da distorção de área (decisão A7), sem banco.

O que se prova: (1) o CRS é o UTM SIRGAS 2000 da zona do CENTRÓIDE, e o EPSG bate com um cálculo independente
(zona = floor((lon+180)/6)+1, sul 31960+zona, norte 31954+zona); (2) a distorção de área declarada bate com uma
medição feita por outro caminho (pyproj.Geod para a área geodésica × shapely no plano projetado); (3) área que
cruza duas zonas UTM não é recusada em silêncio nem escondida: a ficha diz quais zonas cobre e avisa; (4) fora da
cobertura brasileira do SIRGAS 2000 a escolha falha em vez de devolver um CRS qualquer.
"""

import math

import pyproj
import pytest
from shapely.geometry import Polygon
from shapely.ops import transform

from app.amc import crs as crs_mod


def _pontos(poligono: Polygon):
    return [(float(x), float(y)) for x, y in poligono.exterior.coords]


def _ficha(poligono: Polygon) -> dict:
    p = _pontos(poligono)
    c = poligono.centroid
    return crs_mod.ficha_crs(p, poligono.bounds, (c.x, c.y))


def _area_geodesica_m2(poligono: Polygon) -> float:
    geod = pyproj.Geod(ellps="GRS80")
    area, _ = geod.geometry_area_perimeter(poligono)
    return abs(area)


@pytest.mark.parametrize(
    "lon,lat,srid,zona,hemisferio",
    [
        (-49.30, -16.70, 31982, 22, "S"),   # Goiás
        (-38.50, -12.97, 31984, 24, "S"),   # litoral nordeste
        (-60.02, -3.10, 31980, 20, "S"),    # Amazonas (sul da linha)
        (-60.02, 2.82, 31974, 20, "N"),     # Roraima (norte da linha)
    ],
)
def test_srid_bate_com_calculo_independente(lon, lat, srid, zona, hemisferio):
    zona_independente = int(math.floor((lon + 180.0) / 6.0)) + 1
    esperado = (31960 + zona_independente) if lat < 0 else (31954 + zona_independente)
    assert (srid, zona, hemisferio) == crs_mod.srid_utm_sirgas(lon, lat)
    assert esperado == srid
    assert pyproj.CRS.from_epsg(srid).name.startswith("SIRGAS 2000")


def test_fora_da_cobertura_falha_em_vez_de_devolver_qualquer_crs():
    # zona 14S, zona 31N e zona 25N: nenhuma na cobertura brasileira do SIRGAS 2000 (17S-25S, 18N-22N)
    for lon, lat in ((-100.0, -10.0), (0.0, 10.0), (-30.0, 5.0)):
        with pytest.raises(ValueError):
            crs_mod.srid_utm_sirgas(lon, lat)


def test_distorcao_declarada_bate_com_medicao_independente():
    """A ficha diz a distorção de área em %; aqui ela é remedida por outro caminho: área geodésica (pyproj.Geod,
    GRS80) contra a área do MESMO polígono projetado no CRS escolhido (shapely). A diferença relativa tem de cair
    dentro da faixa declarada (mínimo/máximo), com folga de 0,01 ponto percentual para o arredondamento da ficha."""
    poligono = Polygon([(-49.30, -16.70), (-49.20, -16.70), (-49.20, -16.60), (-49.30, -16.60)])
    ficha = _ficha(poligono)
    projetar = pyproj.Transformer.from_crs(4326, ficha["srid_trabalho"], always_xy=True).transform
    area_plano = transform(projetar, poligono).area
    medida_pct = (area_plano / _area_geodesica_m2(poligono) - 1.0) * 100.0
    assert ficha["distorcao_area_min_pct"] - 0.01 <= medida_pct <= ficha["distorcao_area_max_pct"] + 0.01
    assert ficha["distorcao_area_max_abs_pct"] >= abs(medida_pct) - 0.01
    assert ficha["pontos_amostrados"] >= 5 and "areal_scale" in ficha["metodo"]


def test_area_que_cruza_duas_zonas_declara_as_zonas_e_avisa():
    """Refutação do adversário: área a cavalo entre a zona 22S e a 23S (meridiano −48°). O conjunto continua num
    CRS único (o do centróide) — mas a ficha diz quais zonas a área cobre, marca `cruza_zonas_utm` e escreve o
    aviso. Nada disso pode ficar escondido."""
    poligono = Polygon([(-49.0, -16.0), (-47.0, -16.0), (-47.0, -15.0), (-49.0, -15.0)])
    ficha = _ficha(poligono)
    assert ficha["cruza_zonas_utm"] is True
    assert ficha["zonas_utm_cobertas"] == [22, 23]
    assert any("cruza" in a for a in ficha["avisos"])
    assert ficha["srid_trabalho"] == crs_mod.srid_utm_sirgas(*poligono.centroid.coords[0][:2][::1])[0]
    # a distorção cresce longe do meridiano central e a ficha mostra isso em vez de esconder
    assert ficha["distorcao_area_max_abs_pct"] > 0.05


def test_area_pequena_no_meridiano_central_tem_distorcao_pequena_e_negativa():
    """Sanidade do sinal: no meridiano central do UTM o fator de escala é 0,9996, logo a área no plano é MENOR que
    a geodésica (distorção negativa, ≈ −0,08 %). Se isto inverter, o sinal da ficha está trocado."""
    mc = crs_mod.meridiano_central(22)
    poligono = Polygon([(mc - 0.01, -16.0), (mc + 0.01, -16.0), (mc + 0.01, -15.98), (mc - 0.01, -15.98)])
    ficha = _ficha(poligono)
    assert -0.09 < ficha["distorcao_area_max_pct"] < -0.07
    assert ficha["cruza_zonas_utm"] is False and ficha["avisos"] == []


def test_zonas_utm_cobertas_nao_perde_as_zonas_do_meio():
    """Achado 3 do laudo (06/09/2026): a ficha montava `zonas_utm_cobertas` como {zona(xmin), zona(xmax),
    zona(centróide)}, então uma área larga perdia as zonas do MEIO e o aviso contava zona a menos. Aqui a área vai
    de −60° a −42° (quatro zonas) e de −66° a −36° (seis)."""
    largo = Polygon([(-60.0, -20.0), (-42.0, -20.0), (-42.0, -19.0), (-60.0, -19.0)])
    ficha = _ficha(largo)
    assert ficha["zonas_utm_cobertas"] == [21, 22, 23, 24]
    assert ficha["cruza_zonas_utm"] is True
    assert "cruza 4 zonas UTM (21, 22, 23, 24)" in ficha["avisos"][0]

    ainda_maior = Polygon([(-66.0, -12.0), (-36.0, -12.0), (-36.0, -11.0), (-66.0, -11.0)])
    assert _ficha(ainda_maior)["zonas_utm_cobertas"] == [20, 21, 22, 23, 24, 25]
