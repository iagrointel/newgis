"""Adversário de linha L2 (parte 2), item `L2-09-b-cena-extrusao-slides` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

Portão (LITERAL): "cena da demo ... roda a ≥ 30 fps ou limiar declarado (medido)". A evidência
commitada com o fechamento do item (`tests/medidas/L2-09-b-cena-extrusao-slides.json`, mesma
linhagem do commit `33b6f3ce` citado no ledger) registra `fps_cena_demo = 8,3` quadros/s — bem
abaixo de 30 — sob SwiftShader (renderizador por software, sem GPU real, `WEBGL_debug_renderer_info`
no próprio JSON). Não há "limiar declarado" em lugar nenhum do repositório para este item: nenhuma
ADR (`docs/adr/20260908T0620-documento-de-cena-3d.md`), nenhum handoff, nenhum campo do
`laco/estado.json` menciona um teto alternativo aceito para SwiftShader. A cláusula, portanto, não
tem como ter passado — e a própria nota de fechamento do item ("fps e cota do terreno NAO medidos")
contradiz o número que o JSON de medidas efetivamente registra, o que por si só é um sinal de
descontrole entre o que foi medido e o que foi contado ao gerente.

Bônus: `laco/estado.json` (o rastreador mestre desta trilha) marca `"estado": "pendente"` para
`L2-09-b-cena-extrusao-slides" — o item nunca chegou a ser marcado fechado na fonte de verdade que o
próprio time mantém, apesar do brief do gerente citar `ENTREGUE · commit 33b6f3ce`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMMIT_FECHAMENTO = "33b6f3ce"
FPS_MINIMO = 30.0


def _json_no_commit(commit: str, caminho: str) -> dict:
    saida = subprocess.run(
        ["git", "show", f"{commit}:{caminho}"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(saida)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "portão de L2-09-b exige >=30 fps 'ou limiar declarado'; a medida commitada no fechamento "
        "(33b6f3ce) registra 8,3 fps sob SwiftShader e não existe, em ADR/handoff/estado.json, "
        "nenhum limiar alternativo declarado para este caso — a cláusula não tem como ter passado."
    ),
)
def test_fps_da_cena_atende_o_portao_ou_ha_limiar_declarado():
    medida = _json_no_commit(COMMIT_FECHAMENTO, "tests/medidas/L2-09-b-cena-extrusao-slides.json")
    fps = medida["medidas"]["fps_cena_demo"]["valor"]

    limiar_declarado_em = [
        p
        for p in (
            RAIZ / "docs/adr/20260908T0620-documento-de-cena-3d.md",
        )
        if p.exists() and "limiar" in p.read_text(encoding="utf-8").lower() and "fps" in p.read_text(
            encoding="utf-8"
        ).lower()
    ]

    assert fps >= FPS_MINIMO or limiar_declarado_em, medida
