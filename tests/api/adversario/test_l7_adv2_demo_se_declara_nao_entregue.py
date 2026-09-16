"""Adversário de linha L7 operação (parte 2) — item `L7-29-roteiro-demonstracao`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`).

`docs/DEMO.md` tem um bloco gerado automaticamente de `laco/PAINEL.md` (marcadores
`<!-- gerado de laco/PAINEL.md:inicio -->` / `:fim`, regenerado por
`venv/bin/python docs/gerar_demo.py --preencher`) com a lista "Não faz ainda" — exatamente a
cláusula do próprio portão ("lista 'o que não faz ainda' gerada do PAINEL.md"). Essa lista, hoje,
inclui o PRÓPRIO item `L7-29-roteiro-demonstracao` entre os "71 de 76 itens não entregues". O
artefato que É o produto do item declara, no seu próprio conteúdo gerado, que o item que o produziu
não está entregue.

Confirma, por outro ângulo, o que `laco/estado.json` já registra para este item: `estado` (campo de
topo) é `"entregue"`, mas o `bloqueio` do próprio registro diz "parcial porque o roteiro só cobre
L0+L2 (dependências L7-01-c/L3-01/L4-02/L5-01/L6-01 abertas...)" — e uma dessas dependências,
`L7-01-c-dado-demonstracao`, já está na lista de refutados desta linha (artefato ausente em master,
auditoria HARD-03 07/09)."""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DEMO = RAIZ / "docs" / "DEMO.md"

import pytest


def _lista_nao_faz_ainda() -> str:
    texto = DEMO.read_text(encoding="utf-8")
    inicio = texto.find("<!-- gerado de laco/PAINEL.md:inicio -->")
    fim = texto.find("<!-- gerado de laco/PAINEL.md:fim -->")
    assert inicio != -1 and fim != -1, "marcadores do bloco gerado de PAINEL.md não encontrados"
    return texto[inicio:fim]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "docs/DEMO.md tem, no próprio bloco gerado de laco/PAINEL.md, o item "
        "L7-29-roteiro-demonstracao listado entre os 'não entregues' — o artefato que é o produto "
        "do item declara que o item não está entregue. Item L7-29-roteiro-demonstracao."
    ),
)
def test_demo_nao_se_lista_como_nao_entregue():
    bloco = _lista_nao_faz_ainda()
    assert "L7-29-roteiro-demonstracao" not in bloco, (
        "docs/DEMO.md lista o próprio L7-29-roteiro-demonstracao como 'não entregue' no bloco "
        "gerado de PAINEL.md"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "L7-29-roteiro-demonstracao depende de L7-01-c-dado-demonstracao (declarado em "
        "laco/estado.json), item já refutado nesta linha (artefato ausente em master, HARD-03 "
        "07/09: 0 plat demo/demo_semear/dado_demonstracao em master). O passo 1 do roteiro real "
        "('Antes de começar... Deixe o catálogo sem nenhum conteúdo pré-carregado', docs/DEMO.md) "
        "confirma que a plataforma não tem carga de demonstração embutida, contradizendo a "
        "hipótese do item ('abre com o dado demo')."
    ),
)
def test_roteiro_nao_depende_de_dependencia_ja_refutada():
    # Referência fixa e portável ao arquivo do laço (fora deste worktree; só leitura).
    caminho_estado = Path("/home/dev/plataforma/laco/estado.json")
    assert caminho_estado.exists(), "laco/estado.json inacessível para conferir a dependência"
    import json

    dado = json.loads(caminho_estado.read_text(encoding="utf-8"))
    item = next(i for i in dado["backlog"] if i.get("id") == "L7-29-roteiro-demonstracao")
    dependencias = item.get("dependencias", [])
    assert "L7-01-c-dado-demonstracao" not in dependencias, (
        "L7-29-roteiro-demonstracao ainda depende de L7-01-c-dado-demonstracao, já refutado "
        "(artefato ausente em master)"
    )
