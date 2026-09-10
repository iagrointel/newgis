"""Unidade da sombra projetada e da posição solar (L2-09-d).

Cláusula 4 do portão: "sombra às 12h de 21/12 em −23° com comprimento a <= 5 % da fórmula". O instante
é o MEIO-DIA SOLAR verdadeiro (o relógio UTC é derivado COM a equação do tempo — usar 12h do fuso
sem a equação erra o comprimento em ~7 %, acima da tolerância), e a fórmula é a do ponto de meio-dia:
elevação = 90° − |latitude − declinação|, comprimento = altura / tan(elevação).

O teste também declara o número da casa: a elevação que o algoritmo NOAA devolve nesse instante é
comparada com a fórmula fechada antes do comprimento, para a prova ser de geometria, não de código.
"""

import datetime
import math

import pytest

from app.analise3d.sol import posicao_solar
from app.analise3d.sombra import deslocamento_da_sombra, sombra_do_solido

LAT, LON = -23.0, -46.0  # SIRGAS UTM 23S (a mesma faixa do terreno dos testes)


def meio_dia_solar_21_dezembro() -> tuple[datetime.datetime, float]:
    """Instante UTC do meio-dia solar verdadeiro em (LAT, LON) em 21/12/2026, e a declinação do dia.

    Resolve em duas passadas: a equação do tempo muda menos de um segundo entre elas."""
    quando = datetime.datetime(2026, 12, 21, 15, 0, 0, tzinfo=datetime.UTC)  # palpite: 12h de São Paulo
    for _ in range(3):
        sol = posicao_solar(quando, LAT, LON)
        utc_min = 720.0 - sol["equacao_do_tempo_min"] - 4.0 * LON
        quando = datetime.datetime(
            2026, 12, 21, int(utc_min // 60), int(utc_min % 60), 0, tzinfo=datetime.UTC
        )
    return quando, posicao_solar(quando, LAT, LON)["declinacao_graus"]


def test_clausula_4_sombra_do_meio_dia_de_21_dezembro_a_5_porcento_da_formula(medida):
    quando, declinacao = meio_dia_solar_21_dezembro()
    sol = posicao_solar(quando, LAT, LON)

    # geometria fechada do meio-dia: elevação = 90° − |φ − δ| (o Sol cruza o meridiano do lugar)
    elevacao_formula = 90.0 - abs(LAT - declinacao)
    assert sol["elevacao_graus"] == pytest.approx(elevacao_formula, abs=0.5), (
        f"elevação {sol['elevacao_graus']:.3f}° contra a fórmula {elevacao_formula:.3f}°"
    )
    # meio-dia solar de verdade: perto do zênite o azimute é mal condicionado (a 0,44° do zênite,
    # um minuto de hora move o azimute vários graus) — a prova é o QUADRANTE: em dezembro, com a
    # declinação mais ao sul que a latitude −23°, o Sol passa ao SUL do lugar ao meio-dia
    assert 135.0 <= sol["azimute_graus"] <= 225.0

    quadrado = {
        "type": "Polygon",
        "coordinates": [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]],
    }
    altura = 50.0
    r = sombra_do_solido(quadrado, altura, sol["azimute_graus"], sol["elevacao_graus"])
    comprimento_formula = altura / math.tan(math.radians(elevacao_formula))
    desvio = abs(r["comprimento_sombra_m"] - comprimento_formula) / comprimento_formula
    assert desvio <= 0.05, f"comprimento {r['comprimento_sombra_m']:.3f} m contra a fórmula {comprimento_formula:.3f} m"
    medida("L2-09-d-analise-3d-visibilidade")(
        "clausula4_desvio_comprimento_sombra", round(desvio, 5), "fração",
        "comprimento da sombra contra altura/tan(90°-|phi-delta|) no meio-dia solar verdadeiro",
    )


def test_zenite_exato_nao_tem_sombra_lateral():
    quadrado = {
        "type": "Polygon",
        "coordinates": [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]],
    }
    r = sombra_do_solido(quadrado, 50.0, 0.0, 90.0)
    assert r["comprimento_sombra_m"] == 0.0


def test_deslocamento_aponta_para_o_oposto_do_sol():
    assert deslocamento_da_sombra(0.0, 20.0) == pytest.approx((0.0, -20.0))  # sol ao norte -> sombra ao sul
    assert deslocamento_da_sombra(180.0, 20.0) == pytest.approx((0.0, 20.0))  # sol ao sul -> sombra ao norte
    assert deslocamento_da_sombra(90.0, 20.0) == pytest.approx((-20.0, 0.0))  # sol a leste -> sombra a oeste


def test_sombra_do_quadrado_com_sol_a_45_graus_tem_a_area_esperada():
    """Sol a 45°: comprimento = altura; a união de um quadrado de 10 m com a cópia deslocada de
    (−altura, 0) tem de caber num retângulo de (10 + altura) × 10 m e conter os dois quadrados."""
    quadrado = {
        "type": "Polygon",
        "coordinates": [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]],
    }
    altura = 30.0
    r = sombra_do_solido(quadrado, altura, 90.0, 45.0)
    assert r["comprimento_sombra_m"] == pytest.approx(altura)
    assert r["direcao_sombra_graus"] == pytest.approx(270.0)
    xs = [c[0] for c in r["sombra_geojson"]["coordinates"][0]]
    ys = [c[1] for c in r["sombra_geojson"]["coordinates"][0]]
    assert min(xs) == pytest.approx(-altura) and max(xs) == pytest.approx(10.0)
    assert min(ys) == pytest.approx(0.0) and max(ys) == pytest.approx(10.0)


def test_sol_abaixo_do_horizonte_e_poligono_vazio_levantam_valueerror():
    quadrado = {
        "type": "Polygon",
        "coordinates": [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]],
    }
    with pytest.raises(ValueError):
        sombra_do_solido(quadrado, 10.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        sombra_do_solido(quadrado, 10.0, 0.0, -10.0)
    vazio = {"type": "Polygon", "coordinates": [[]]}
    with pytest.raises(ValueError):
        sombra_do_solido(vazio, 10.0, 0.0, 45.0)


def test_posicao_solar_em_conhecidos_do_ano():
    # equinócio de março, meio-dia solar no equador: Sol a pino (elevação ~90°)
    quando = _meio_dia(2026, 3, 20, 0.0, 0.0)
    sol = posicao_solar(quando, 0.0, 0.0)
    assert sol["elevacao_graus"] > 88.0
    # meio-dia solar em latitude +40° no mesmo equinócio: Sol ao SUL (azimute ~180°), elevação ~50°
    quando = _meio_dia(2026, 3, 20, 40.0, 0.0)
    sol = posicao_solar(quando, 40.0, 0.0)
    assert sol["azimute_graus"] == pytest.approx(180.0, abs=1.0)
    assert sol["elevacao_graus"] == pytest.approx(50.0, abs=0.5)
    # e em latitude −40°, ao NORTE
    quando = _meio_dia(2026, 3, 20, -40.0, 0.0)
    sol = posicao_solar(quando, -40.0, 0.0)
    assert sol["azimute_graus"] == pytest.approx(0.0, abs=1.0)


def _meio_dia(ano: int, mes: int, dia: int, lat: float, lon: float) -> datetime.datetime:
    """Instante UTC do meio-dia solar verdadeiro (mesma mecânica do teste da cláusula 4)."""
    quando = datetime.datetime(ano, mes, dia, 12, 0, 0, tzinfo=datetime.UTC)
    for _ in range(3):
        sol = posicao_solar(quando, lat, lon)
        utc_min = 720.0 - sol["equacao_do_tempo_min"] - 4.0 * lon
        quando = datetime.datetime(
            ano, mes, dia, int(utc_min // 60) % 24, int(utc_min % 60), 0, tzinfo=datetime.UTC
        )
    return quando
