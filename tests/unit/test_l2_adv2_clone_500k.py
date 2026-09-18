"""Adversário de linha L2 (parte 2), item `L2-08-b-clonar-camadas-hospedadas` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Portão (LITERAL) exige, entre outras cláusulas: "5 camadas clonadas com contagem igual" e "camada de
500 mil feições em tempo medido". A evidência commitada pelo time no fechamento
(`tests/medidas/L2-08-b-clonar-camadas-hospedadas.json`, linhagem do commit `9b73446c`) registrava, em
texto livre no campo `nota` de CADA medida: "camada de 500 mil feicoes nao medida" — e a contagem de
camadas testadas (`camadas_clonadas_nos_testes`) era 3, não 5. Duas ordens de grandeza faltavam entre
o medido (2.000 feições) e o pedido (500.000). Refutação correta na época; o remédio está abaixo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MEDIDA = RAIZ / "tests" / "medidas" / "L2-08-b-clonar-camadas-hospedadas.json"


def _algum_teste_cobre_500_mil() -> bool:
    saida = subprocess.run(
        ["grep", "-lE", "500_000|500000", "tests/api/test_migracao_clonar.py"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    return bool(saida.stdout.strip())


# REMEDIADO (wt/l208bcl51a7, 18/09/2026): tests/api/test_migracao_clonar.py ganhou
# test_escala_do_portao_5_camadas_e_500_mil_feicoes (marcado `lento`): 5 camadas servidas pelo PRÓPRIO
# FeatureServer da plataforma (Point, LineString, Polygon, Point e Point com 500.000 feições semeadas
# num INSERT ... generate_series), cada uma clonada por um job próprio, todas com contagem_igual e
# hash_amostra_igual. A fonte própria fecha a cláusula de escala sem a credencial de terceiro (D20);
# 500 mil de um serviço PÚBLICO hospedado segue fora da fronteira. Números no JSON de medidas.
def test_clausula_de_escala_500_mil_feicoes_foi_medida():
    assert _algum_teste_cobre_500_mil()
    medida = json.loads(MEDIDA.read_text(encoding="utf-8"))
    notas = " ".join(str(v.get("nota", "")) for v in medida["medidas"].values() if isinstance(v, dict))
    assert "nao medida" not in notas and "não medida" not in notas, medida
    assert medida["medidas"]["camadas_clonadas_nos_testes"]["valor"] >= 5, medida
    assert medida["medidas"]["segundos_clone_500_mil_feicoes"]["valor"] > 0, medida
