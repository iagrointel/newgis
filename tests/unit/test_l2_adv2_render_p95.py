"""Adversário de linha L2 (parte 2), item `L2-12-a-motor-render-servidor` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`, CORRIGIDO nesta rodada.

O achado do T9 era de PROCESSO: o item foi fechado citando como prova o commit `f2a8cb15`, cujo artefato
de medida (`tests/medidas/L2-12-a-motor-render-servidor.json`) registrava `quente_p95_ms = 1290,2` —
acima do teto de 1.000 ms do portão literal. A mesma asserção que `test_motor_render.py` faz sobre esse
número falharia se rodada sobre o artefato commitado. A causa raiz tinha duas pernas, e as duas foram
fechadas (18/09/2026):

1. a medida era gravada no disco NO MEIO do teste, ANTES das asserções — uma rodada reprovada deixava o
   arquivo vermelho na árvore, pronto para ser commitado como "prova". Agora a escrita em
   `test_motor_render.py::test_frio_e_quente_p95_da_demo_1024x768` acontece DEPOIS das asserções;
2. o gate é sensível à carga da máquina compartilhada e não tinha margem/retentativa documentada — agora
   tem: cada tentativa registra a carga do instante como NÚMERO, p95 estourado sob carga alta (> 1 por
   CPU) dispara espera + re-medida (até 3 tentativas, todas públicas em `tentativas` no JSON), e p95
   estourado sob carga baixa reprova na hora, sem retentar.

Este arquivo é a GUARDA que impede o furo de se repetir em silêncio: em vez de um xfail permanente sobre
o commit histórico (f2a8cb15 nunca vai ficar verde — história não se reescreve), o teste lê a evidência
COMMITADA em HEAD e exige que ela satisfaça o portão literal, com a carga e as tentativas registradas.
Qualquer commit futuro que trouxer uma medida vermelha, sem carga ou sem o rastro de tentativas reprova
aqui — a "prova" que reprova a cláusula não passa mais despercebida.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EVIDENCIA = "tests/medidas/L2-12-a-motor-render-servidor.json"
TETO_QUENTE_MS = 1000
TETO_FRIO_MS = 3000
N_QUENTE_PORTAO = 50  # portão literal: "p95 de 50"


def _evidencia_commitada() -> dict:
    saida = subprocess.run(
        ["git", "show", f"HEAD:{EVIDENCIA}"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(saida)


def test_evidencia_commitada_satisfaz_o_teto_do_portao():
    medida = _evidencia_commitada()
    assert medida["quente_p95_ms"] <= TETO_QUENTE_MS, medida
    assert medida["frio_p95_ms"] <= TETO_FRIO_MS, medida
    assert medida["n_quente_ok"] >= N_QUENTE_PORTAO, medida


def test_evidencia_commitada_registra_carga_e_tentativas():
    """A margem documentada do gate sensível a carga tem de estar visível no artefato: carga do instante
    como número (sem ela ninguém distingue "o motor piorou" de "a máquina estava lotada") e a lista de
    tentativas, cada uma com a própria carga (a retentativa é pública, nunca um descarte silencioso)."""
    medida = _evidencia_commitada()
    for chave in ("carga_1min", "carga_5min", "carga_15min"):
        assert isinstance(medida.get(chave), (int, float)), medida
    assert medida.get("tentativas"), medida
    for tentativa in medida["tentativas"]:
        assert isinstance(tentativa.get("carga_1min"), (int, float)), tentativa
        assert "quente_p95_ms" in tentativa and "n_quente_ok" in tentativa, tentativa
