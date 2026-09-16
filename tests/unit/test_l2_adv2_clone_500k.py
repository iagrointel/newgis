"""Adversário de linha L2 (parte 2), item `L2-08-b-clonar-camadas-hospedadas` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Portão (LITERAL) exige, entre outras cláusulas: "5 camadas clonadas com contagem igual" e "camada de
500 mil feições em tempo medido". A própria evidência commitada pelo time
(`tests/medidas/L2-08-b-clonar-camadas-hospedadas.json`, git sha `77411ed09942`, mesma linhagem do
commit `9b73446c` citado como fechamento) registra, em texto livre no campo `nota` de CADA medida:
"camada de 500 mil feicoes nao medida" — e a contagem de camadas testadas
(`camadas_clonadas_nos_testes`) é 3, não 5.

Isto não é opinião do adversário: é o próprio artefato de prova que o time anexou ao commit de
fechamento admitindo que a cláusula de escala do portão nunca rodou. Duas ordens de grandeza faltam
entre o que foi medido (2.000 feições) e o que o portão pede (500.000)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMMIT_FECHAMENTO = "9b73446c"


def _json_no_commit(commit: str, caminho: str) -> dict:
    saida = subprocess.run(
        ["git", "show", f"{commit}:{caminho}"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(saida)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "portão de L2-08-b exige '5 camadas clonadas' e 'camada de 500 mil feições em tempo medido'; "
        "a evidência commitada (tests/medidas/L2-08-b-clonar-camadas-hospedadas.json, mesma linhagem do "
        "commit de fechamento) só cobre 3 camadas e admite, no próprio texto, 'camada de 500 mil feicoes "
        "nao medida' — a cláusula de escala nunca foi exercitada."
    ),
)
def test_clausula_de_escala_500_mil_feicoes_foi_medida():
    medida = _json_no_commit(
        COMMIT_FECHAMENTO, "tests/medidas/L2-08-b-clonar-camadas-hospedadas.json"
    )
    notas = " ".join(
        str(v.get("nota", "")) for v in medida["medidas"].values() if isinstance(v, dict)
    )
    assert "nao medida" not in notas and "não medida" not in notas, medida
    assert medida["medidas"]["camadas_clonadas_nos_testes"]["valor"] >= 5, medida
