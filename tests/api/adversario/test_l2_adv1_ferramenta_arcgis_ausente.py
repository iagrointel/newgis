"""Adversário de linha L2 (parte 1) — hipótese transversal nº 1 do laudo (ver
`laco/handoffs/T9/linha-L2-laudo-adversario-1.md`): quatro itens desta linha (`L2-04-servicos-esri-ogc`,
`L2-04-b-featureserver-catalogo-metadados`, `L2-04-c-featureserver-query`,
`L2-04-d-featureserver-edicao-anexos`) têm, no PRÓPRIO texto do portão ou da refutação exigida, a cláusula
"adversário roda o cliente Python `arcgis` (Esri) ... e lista toda chamada que quebra". Nenhum dos quatro
ledgers registra essa cláusula como cumprida — todos dizem, em uma variação ou outra, "pacote não
instalado" / "teste do parceiro, PENDENTE (D20)".

Este teste prova a causa objetivamente: o pacote `arcgis` da Esri não existe nem no Python do sistema nem
no venv da casa (`venv/bin/python -c "import arcgis"` → `ModuleNotFoundError`), então a refutação nunca
PODE ter sido executada nesta máquina — não é uma lacuna de agenda, é uma ferramenta ausente. Achado
colateral (registrado no laudo, não testado aqui por não ser o alvo do item): `python3-qgis` (bindings
Python do QGIS, `from qgis.core import QgsApplication`) ESTÁ instalado e inicializa sem X (`QgsApplication(
[], False)`) — a desculpa "QGIS não instalado / sem ambiente gráfico", repetida em mais de um ledger desta
linha, é falsa para a metade headless da verificação (abrir camada/WFS/FeatureServer por API do PyQGIS não
exige tela); só a verificação de UI (captura de tela) exigiria ambiente gráfico de verdade.

xfail(strict=True): o teste PASSARIA (a importação funcionaria) se alguém instalasse o pacote — quando
isso acontecer, o teste falha "de verdade" (por sucesso), sinal para apagar este xfail e cobrar a
refutação de verdade nos quatro itens."""

from __future__ import annotations

import importlib.util

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "refutação exigida de L2-04-servicos-esri-ogc/L2-04-b/L2-04-c/L2-04-d ('adversário roda o cliente "
        "Python arcgis e lista toda chamada que quebra') nunca foi executável nesta máquina: o pacote "
        "`arcgis` não está instalado (nem no venv da casa, nem no Python do sistema). Os quatro itens estão "
        "marcados ENTREGUE com essa cláusula do próprio portão declarada PENDENTE/D20, nunca derrubada nem "
        "reconhecida como bloqueio ativo."
    ),
)
def test_l2_04_pacote_arcgis_esta_disponivel_para_a_refutacao_exigida():
    assert importlib.util.find_spec("arcgis") is not None, "pacote `arcgis` (Esri) não instalado nesta máquina"
