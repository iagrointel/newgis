"""Adversário de linha L1 imagens (parte 2, turno 9) — item
`L1-02-f-predefinicoes-de-renderizacao-e-legenda`, ENTREGUE (commit f3de4387b). Dois achados:

1. A hipótese do item promete `colormap` como "211 nomes do rio-tiler ... ou colormap explícito por
   intervalo/valor". `docs/esquemas/renderizacao-v1.json` só aceita `colormap` como STRING (nome do
   catálogo, `pattern ^[a-z][a-z0-9_]*$`, `maxLength 40`) — não existe NENHUM jeito de submeter um
   colormap explícito por intervalo/valor. Isso torna a refutação exigida pelo item ("colormap de
   70.000 entradas") impossível de testar contra a capacidade real: o teste existente
   (`test_colormap_desconhecido_recusado_422`) usa uma STRING inventada
   ("rampa-que-nao-existe-70000-entradas"), não um objeto de colormap de fato com 70 mil entradas —
   é o mesmo defeito no nome, não na capacidade.
2. Portão: "6 predefinições de fábrica ... com teste de imagem por pixel de referência". O próprio
   docstring de `tests/api/imagens/test_predefinicoes.py` admite: "a prova PIXEL A PIXEL contra a
   instância viva ... está no relatório do turno, NÃO AQUI" — ou seja, não há, no repositório, um
   teste committed e reproduzível que compare pixel a pixel contra uma imagem de referência salva.

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_predefinicoes_gate.py -q -rxX`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-f CAI: docs/esquemas/renderizacao-v1.json so aceita colormap como nome de catalogo "
    "(string, ate 40 chars); a hipotese do item promete tambem 'colormap explicito por intervalo/"
    "valor' (um objeto), que nao existe no esquema. Sem isso a refutacao exigida ('colormap de "
    "70.000 entradas') e impossivel de testar contra a capacidade real."
))
def test_esquema_aceita_colormap_explicito_por_intervalo():
    schema = json.loads((ROOT / "docs" / "esquemas" / "renderizacao-v1.json").read_text(encoding="utf-8"))
    colormap_schema = schema["properties"]["colormap"]
    tipos_aceitos = colormap_schema.get("type")
    if isinstance(tipos_aceitos, str):
        tipos_aceitos = [tipos_aceitos]
    assert "object" in (tipos_aceitos or []) or "anyOf" in colormap_schema or "oneOf" in colormap_schema, (
        f"colormap so aceita {colormap_schema} — nenhuma forma de objeto/intervalo explicito existe")


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-f CAI: o proprio docstring de tests/api/imagens/test_predefinicoes.py admite que a prova "
    "pixel a pixel contra imagem de referencia 'esta no relatorio do turno, nao aqui' — o portao "
    "exige essa prova como teste de imagem por pixel de referencia, committed e reproduzivel."
))
def test_teste_de_pixel_de_referencia_das_6_predefinicoes_esta_commitado():
    texto = (ROOT / "tests" / "api" / "imagens" / "test_predefinicoes.py").read_text(encoding="utf-8")
    assert "está no relatório do turno, não aqui" not in texto, (
        "o próprio arquivo de teste admite que a prova pixel-a-pixel de referência não está "
        "commitada, só num relatório de turno não reproduzível")
    assert any(nome in texto for nome in ("imagem_de_referencia", "pixel_de_referencia", "referencia.png")), (
        "nenhuma função/asset de imagem de referência (para as 6 predefinições de fábrica) foi "
        "encontrada no arquivo de teste do item")
