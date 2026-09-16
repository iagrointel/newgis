"""Adversário de linha L1 imagens (parte 2, turno 9) — item `L1-07-mosaico-por-colecao-e-pegadas`,
ENTREGUE (commit b22329356). O portão literal pede "mosaico de ≥ 6 cenas Sentinel-2 abertas (recortes
pequenos) registrado pela tela; tile do mosaico em z 8-14 medido (frio/quente) em
`tests/medidas/L1-07.json`". A medição commitada como prova de fechamento não bate com o portão em
dois pontos, e o arquivo nem tem o nome pedido:

1. Nome do arquivo: o portão pede literalmente `tests/medidas/L1-07.json`; o que existe é
   `tests/medidas/L1-07-mosaico-por-colecao-e-pegadas.json`.
2. Conteúdo: o próprio campo `comando` da medição diz "grade sintética 3x2 (6 cenas, 4 km/quadrante,
   20 m/px)" — cenas SINTÉTICAS geradas em memória, não "Sentinel-2 abertas" como o portão exige
   verbatim. Não há, em lugar nenhum da medição commitada, uma cena Sentinel-2 real.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_l107_gate.py -q -rxX`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEDIDAS = ROOT / "tests" / "medidas"


@pytest.mark.xfail(strict=True, reason=(
    "L1-07 CAI: o portao pede o arquivo literal tests/medidas/L1-07.json; o commit de fechamento "
    "gravou em tests/medidas/L1-07-mosaico-por-colecao-e-pegadas.json (nome diferente do exigido)."
))
def test_arquivo_de_medidas_tem_o_nome_literal_do_portao():
    assert (MEDIDAS / "L1-07.json").exists(), (
        "tests/medidas/L1-07.json (nome literal do portão) não existe; só existe "
        "tests/medidas/L1-07-mosaico-por-colecao-e-pegadas.json")


@pytest.mark.xfail(strict=True, reason=(
    "L1-07 CAI: a medicao commitada como prova de fechamento usa cenas SINTETICAS ('grade sintetica "
    "3x2', ver campo 'comando' de cada entrada em tests/medidas/L1-07-mosaico-por-colecao-e-pegadas."
    "json), nao 'Sentinel-2 abertas' como o portao exige verbatim ('mosaico de >= 6 cenas Sentinel-2 "
    "abertas')."
))
def test_medida_de_tile_usa_cenas_sentinel2_abertas_de_verdade():
    dados = json.loads((MEDIDAS / "L1-07-mosaico-por-colecao-e-pegadas.json").read_text(encoding="utf-8"))
    comandos = " ".join(v.get("comando", "") for v in dados.get("medidas", {}).values())
    assert "sintética" not in comandos and "sintetica" not in comandos.lower(), (
        f"a medição usa dado sintético, não Sentinel-2 aberto de verdade: {comandos[:200]}...")
    assert "sentinel" in comandos.lower(), comandos
