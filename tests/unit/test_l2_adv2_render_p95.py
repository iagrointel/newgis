"""Adversário de linha L2 (parte 2), item `L2-12-a-motor-render-servidor` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Portão (LITERAL): "1024×768 do mapa da demo quente ≤ 1 s ... (p95 de 50, medido em tests/medidas)".
`tests/unit/test_motor_render.py::test_frio_e_quente_p95_da_demo_1024x768` tem, ele mesmo, a asserção
`assert medida["quente_p95_ms"] <= 1000`. O ponto: a evidência COMMITADA no próprio commit citado como
fechamento do item (`f2a8cb15`, `tests/medidas/L2-12-a-motor-render-servidor.json`) registra
`quente_p95_ms = 1290,2` — acima do teto — e a última nota do ledger confirma, em português claro:
"quente p95 1.290,2ms sobre o teto de 1.000ms". Ou seja: o arquivo que devia ser a PROVA de que o
portão passou é, ao ser lido, a prova de que na hora em que foi gerado o teste correspondente
levantaria `AssertionError` (a mesma asserção que este arquivo mede aqui, sobre o mesmo JSON).

Não é achado de ambiente: reexecutei a suíte ao vivo nesta rodada (`roda_teste.sh
tests/unit/test_motor_render.py::test_frio_e_quente_p95_da_demo_1024x768`) e ela passou, com a
máquina mais folgada (166,9 ms) — confirmando que a métrica É sensível a disputa de CPU da máquina
compartilhada, exatamente como o próprio ledger diagnosticou. O achado aqui é de PROCESSO, não de
código: o item foi fechado citando como prova um commit cujo artefato de medida, lido literalmente,
reprova a própria cláusula que deveria comprovar — sem um novo commit trazendo uma medida verde. Um
gate sensível a carga da máquina compartilhada sem nenhuma margem/retentativa documentada pode
repetir o mesmo furo silenciosamente a qualquer disputa de CPU no cluster."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMMIT_FECHAMENTO = "f2a8cb15"
TETO_QUENTE_MS = 1000


def _json_no_commit(commit: str, caminho: str) -> dict:
    saida = subprocess.run(
        ["git", "show", f"{commit}:{caminho}"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(saida)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "o commit citado como fechamento de L2-12-a (f2a8cb15) traz, ele mesmo, "
        "tests/medidas/L2-12-a-motor-render-servidor.json com quente_p95_ms=1290.2 > teto de 1000ms "
        "do portão literal — a mesma asserção que test_motor_render.py já faz sobre este número "
        "falharia se rodada sobre o artefato commitado; o ledger confirma o estouro em texto."
    ),
)
def test_evidencia_commitada_do_fechamento_satisfaz_o_teto_do_portao():
    medida = _json_no_commit(COMMIT_FECHAMENTO, "tests/medidas/L2-12-a-motor-render-servidor.json")
    assert medida["quente_p95_ms"] <= TETO_QUENTE_MS, medida
