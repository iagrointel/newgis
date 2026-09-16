"""Adversário de linha L2 (parte 2), item `L2-09-a-terreno-terrain-rgb-relevo` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Portão (LITERAL) tem 5 cláusulas. A evidência commitada com o fechamento do item
(`tests/medidas/L2-09-a-terreno-terrain-rgb-relevo.json`, mesma linhagem do commit `1ff4f57` citado
no ledger) já vem com `resultado` explícito por cláusula — e diz, para 2 das 5, `"nao medida"`:
"cena com terreno + hillshade + contornos a >=30fps (playwright) ou limiar declarado" e "e2e com
captura em 3 inclinações". A própria nota de fechamento do item admite o mesmo ("Martin
hillshade/contornos, front MapLibre e e2e fps ficam pendentes"). O item está marcado ENTREGUE com
3/5 do seu próprio portão literal — não é leitura torta do adversário, é o campo `resultado` do JSON
que o time anexou como prova."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMMIT_FECHAMENTO = "1ff4f57"


def _json_no_commit(commit: str, caminho: str) -> dict:
    saida = subprocess.run(
        ["git", "show", f"{commit}:{caminho}"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(saida)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L2-09-a tem 5 cláusulas no portão literal; a evidência commitada com o fechamento "
        "(tests/medidas/L2-09-a-terreno-terrain-rgb-relevo.json) marca 2 delas 'nao medida' "
        "(hillshade/contornos do Martin integrados + e2e de fps em 3 inclinações) — o próprio "
        "ledger confirma ('Martin hillshade/contornos, front MapLibre e e2e fps ficam pendentes')."
    ),
)
def test_todas_as_clausulas_do_portao_foram_medidas():
    medida = _json_no_commit(
        COMMIT_FECHAMENTO, "tests/medidas/L2-09-a-terreno-terrain-rgb-relevo.json"
    )
    nao_medidas = [c["clausula"] for c in medida["clausulas"] if c["resultado"] != "passou"]
    assert not nao_medidas, nao_medidas
