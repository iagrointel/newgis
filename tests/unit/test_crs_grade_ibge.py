"""Cláusula do portão: "10 pontos do IBGE com coordenadas oficiais em SAD69 e SIRGAS 2000 transformados
pela grade com erro <= 0,05 m (teste; sem a grade o erro seria de dezenas de metros, e o teste prova a
diferença)" — item L2-17-crs-transformacoes.

Fixture `tests/dados/pontos_ibge_sad69_sirgas2000.json`: 10 pontos SAD69 transformados para SIRGAS2000
PELO SERVIÇO OFICIAL DO IBGE (ProGriD Online, `servicodados.ibge.gov.br/api/v1/progrid`, ao vivo — não
um cálculo nosso), usados como padrão-ouro (proveniência completa em `grades_ibge/PROVENIENCIA.md`,
seção "Como foram VALIDADOS"). O teste prova que `app.crs.grades` (pipeline local com o `.gsb`
vendorizado) reproduz esse resultado oficial, e que SEM a grade (mesmas coordenadas lidas como se já
fossem SIRGAS2000) o erro salta para dezenas de metros — a diferença que justifica vendorizar a grade."""

import json
import math
from pathlib import Path

import pytest

from app.crs import grades

RAIZ = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((RAIZ / "tests" / "dados" / "pontos_ibge_sad69_sirgas2000.json").read_text(encoding="utf-8"))
PONTOS = FIXTURE["pontos"]
TOLERANCIA_M = 0.05


def _erro_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """distância aproximada em metros entre dois pontos próximos (graus -> metros por escala local;
    válido para as distâncias desta prova, na casa do milímetro a poucas dezenas de metros)."""
    dlat = (lat2 - lat1) * 111_320.0
    dlon = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def test_fixture_tem_10_pontos_oficiais_do_ibge():
    assert len(PONTOS) == 10
    assert FIXTURE["fonte"].startswith("https://servicodados.ibge.gov.br")


@pytest.mark.parametrize("ponto", PONTOS, ids=[p["nome"] for p in PONTOS])
def test_grade_local_bate_com_oficial_do_ibge_dentro_da_tolerancia(ponto, medida):
    r = grades.transformar_datum_legado(ponto["sad69_long"], ponto["sad69_lat"], 4618)
    assert r["cobertura"] == "dentro_da_grade", ponto["nome"]
    erro = _erro_m(r["lat"], r["lon"], ponto["sirgas2000_lat_oficial"], ponto["sirgas2000_long_oficial"])
    assert erro <= TOLERANCIA_M, (ponto["nome"], erro)


def test_erro_maximo_entre_os_10_pontos_fica_registrado(medida):
    erros = []
    for ponto in PONTOS:
        r = grades.transformar_datum_legado(ponto["sad69_long"], ponto["sad69_lat"], 4618)
        erros.append(_erro_m(r["lat"], r["lon"], ponto["sirgas2000_lat_oficial"], ponto["sirgas2000_long_oficial"]))
    maior = max(erros)
    assert maior <= TOLERANCIA_M
    medida("L2-17-crs-transformacoes")(
        "erro_max_10_pontos_ibge_grade_sad69_m", round(maior, 6), "m",
        "venv/bin/pytest tests/unit/test_crs_grade_ibge.py::test_erro_maximo_entre_os_10_pontos_fica_registrado",
    )


def test_sem_grade_o_erro_e_de_dezenas_de_metros(medida):
    """Mesma coordenada, lida como se SAD69 já fosse SIRGAS2000 (identidade — nenhuma transformação de
    datum) — é o contraste que justifica vendorizar a grade em vez de ignorar o datum."""
    erros = []
    for ponto in PONTOS:
        erros.append(_erro_m(
            ponto["sad69_lat"], ponto["sad69_long"],
            ponto["sirgas2000_lat_oficial"], ponto["sirgas2000_long_oficial"],
        ))
    menor = min(erros)
    assert menor > 50.0, "identidade sem transformação de datum deveria errar dezenas de metros"
    medida("L2-17-crs-transformacoes")(
        "erro_min_10_pontos_sem_transformacao_de_datum_m", round(menor, 3), "m",
        "venv/bin/pytest tests/unit/test_crs_grade_ibge.py::test_sem_grade_o_erro_e_de_dezenas_de_metros",
    )
