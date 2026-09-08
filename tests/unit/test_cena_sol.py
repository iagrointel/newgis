"""Posição do Sol da cena 3D (item L2-09-b-cena-extrusao-slides), cláusula "posição do sol para 3
datas/horas confere com fórmula de referência a ≤ 0,5°".

A conferência é feita contra uma SEGUNDA fórmula, escrita aqui dentro e independente da de app/cena/sol.py:
a de posição solar aproximada do Astronomical Almanac (Michalsky 1988, "The Astronomical Almanac's
algorithm for approximate solar position (1950-2050)", Solar Energy 40(3):227-235), que parte de outra
série e de outra referência de tempo sideral. Comparar a implementação com ela mesma não provaria nada;
comparar com uma segunda fórmula, sim. As duas declaram exatidão da ordem de 0,01°, bem dentro do 0,5°
que o portão pede.

Além disso, dois invariantes que nenhuma das duas pode errar: no ponto subsolar o Sol está no zênite, e
o dia juliano de 2000-01-01T12:00Z é 2451545,0 por definição da época J2000.
"""

import datetime
import math

import pytest

from app.cena.sol import dia_juliano, luz_maplibre, posicao

# (nome, latitude, longitude, instante) — três datas e horas bem separadas no ano e no globo
CASOS = [
    ("solstício de junho, meio-dia em São Paulo", -23.5505, -46.6333, "2026-06-21T12:00:00-03:00"),
    ("solstício de dezembro, fim de tarde em Manaus", -3.1190, -60.0217, "2026-12-21T17:00:00-04:00"),
    ("equinócio de março, manhã em Lisboa", 38.7223, -9.1393, "2026-03-20T09:30:00+00:00"),
]


def _almanaque(lat: float, lon: float, quando: datetime.datetime) -> tuple[float, float]:
    """Azimute e elevação pelo algoritmo do Astronomical Almanac (independente do NOAA)."""
    utc = quando.astimezone(datetime.UTC)
    n = dia_juliano(utc) - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360.0)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lamb = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lamb), math.cos(lamb))
    dec = math.asin(math.sin(eps) * math.sin(lamb))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24.0          # horas
    lmst = math.radians(((gmst + lon / 15.0) % 24.0) * 15.0)       # radianos
    ha = lmst - ra
    latr = math.radians(lat)
    seno_elev = math.sin(latr) * math.sin(dec) + math.cos(latr) * math.cos(dec) * math.cos(ha)
    elev = math.degrees(math.asin(max(-1.0, min(1.0, seno_elev))))
    az = math.degrees(math.atan2(-math.cos(dec) * math.sin(ha),
                                 math.sin(dec) * math.cos(latr) - math.cos(dec) * math.sin(latr) * math.cos(ha)))
    return (az + 360.0) % 360.0, elev


@pytest.mark.parametrize("nome,lat,lon,instante", CASOS)
def test_confere_com_a_formula_do_almanaque(nome, lat, lon, instante):
    quando = datetime.datetime.fromisoformat(instante)
    p = posicao(lat, lon, quando)
    az_ref, elev_ref = _almanaque(lat, lon, quando)
    d_elev = abs(p.elevacao - elev_ref)
    d_az = abs(((p.azimute - az_ref + 180.0) % 360.0) - 180.0)
    assert d_elev <= 0.5, f"{nome}: elevação {p.elevacao:.3f} vs {elev_ref:.3f} (Δ {d_elev:.3f}°)"
    assert d_az <= 0.5, f"{nome}: azimute {p.azimute:.3f} vs {az_ref:.3f} (Δ {d_az:.3f}°)"


def test_dia_juliano_da_epoca_j2000():
    j2000 = datetime.datetime(2000, 1, 1, 12, 0, tzinfo=datetime.UTC)
    assert abs(dia_juliano(j2000) - 2451545.0) < 1e-6


@pytest.mark.parametrize("instante", ["2026-06-21T15:00:00+00:00", "2026-12-21T15:00:00+00:00",
                                      "2026-09-08T06:00:00+00:00"])
def test_no_ponto_subsolar_o_sol_esta_no_zenite(instante):
    """Invariante: existe um ponto onde a elevação é 90°. Ele tem latitude igual à declinação e
    longitude no meridiano solar; se a conta do ângulo horário ou da equação do tempo estiver errada,
    a elevação nesse ponto deixa de ser 90°."""
    quando = datetime.datetime.fromisoformat(instante)
    p0 = posicao(0.0, 0.0, quando)
    utc = quando.astimezone(datetime.UTC)
    minutos = utc.hour * 60 + utc.minute + utc.second / 60
    lon_subsolar = -((minutos + p0.equacao_do_tempo_min) / 4.0 - 180.0)
    lon_subsolar = ((lon_subsolar + 180.0) % 360.0) - 180.0
    p = posicao(p0.declinacao, lon_subsolar, quando)
    assert p.elevacao > 89.9, (p.elevacao, p0.declinacao, lon_subsolar)


def test_luz_do_maplibre_apaga_com_o_sol_abaixo_do_horizonte():
    noite = posicao(-23.55, -46.63, datetime.datetime.fromisoformat("2026-06-21T00:00:00-03:00"))
    assert noite.elevacao < 0
    luz = luz_maplibre(noite)
    assert luz["intensity"] == 0.0
    assert luz["position"][2] == 90.0  # preso ao horizonte, nunca abaixo dele

    dia = posicao(-23.55, -46.63, datetime.datetime.fromisoformat("2026-06-21T12:00:00-03:00"))
    luz_dia = luz_maplibre(dia, 0.4)
    assert luz_dia["intensity"] == 0.4
    assert 0 < luz_dia["position"][2] < 90


def test_instante_sem_fuso_e_coordenada_fora_da_faixa_sao_recusados():
    with pytest.raises(ValueError):
        posicao(0.0, 0.0, datetime.datetime(2026, 6, 21, 12, 0))
    with pytest.raises(ValueError):
        posicao(95.0, 0.0, datetime.datetime(2026, 6, 21, 12, 0, tzinfo=datetime.UTC))
    with pytest.raises(ValueError):
        posicao(0.0, 999.0, datetime.datetime(2026, 6, 21, 12, 0, tzinfo=datetime.UTC))
