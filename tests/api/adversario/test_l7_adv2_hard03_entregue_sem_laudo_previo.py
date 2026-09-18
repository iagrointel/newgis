"""Adversário de linha L7 operação (parte 2) — item `HARD-03-adversario-por-linha-em-lote`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-2.md`).

O portão do item é literal: "laudo por item em laco/handoffs; taxa de refutação e lista de
consertos; NENHUM ITEM VIRA 'entregue com laudo' SEM LAUDO". Cinco itens que este mesmo laudo
(rodada 2 da linha L7) examinou — `L7-06-c-logs-consulta-req-id`, `L7-06-d-paineis`,
`L7-04-a-manual-capturas-geradas`, `L7-04-d-videos-por-tarefa`, `L7-29-roteiro-demonstracao` —
chegaram a `estado: "entregue"` em `laco/estado.json` SEM que nenhum arquivo
`linha-*-laudo-adversario-*.md` anterior a este (T1 a T8) os citasse. O que existe para eles antes
desta rodada é só o HANDOFF do próprio construtor (`laco/handoffs/T3/T4/T8/<item>.md`) — auto-
relato, não auditoria independente. E os cinco caíram assim que um adversário finalmente olhou.
Ou seja: o portão de `HARD-03` ("nenhum item vira entregue sem laudo") não foi respeitado para
estes cinco itens — eles ficaram `entregue` por turnos inteiros (T3/T4/T8) antes de qualquer
laudo adversarial tocar neles, e o próprio `HARD-03` já estava `estado: "entregue"` nesse
intervalo.

Achado complementar (mesma cláusula, ângulo do MECANISMO): `laco/audita_ramo.sh` — o script de
auditoria pré-fusão desta máquina — confere segredo vazado, nome proibido, xfail sem
`strict=True` novo, ruff e resultado do pytest, mas não tem nenhuma verificação de que a PROVA
usada pelo ramo (fixture, config, ambiente) é a mesma que `install.sh` entrega em produção —
exatamente o padrão que derrubou `L7-06-c` nesta rodada (banca com nginx/config PRÓPRIOS,
diferente do `deploy/*.conf` real)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

LACO = Path("/home/dev/plataforma/laco")
ESTADO = LACO / "estado.json"
HANDOFFS = LACO / "handoffs"

ITENS_SEM_LAUDO_PREVIO = (
    "L7-06-c-logs-consulta-req-id",
    "L7-06-d-paineis",
    "L7-04-a-manual-capturas-geradas",
    "L7-04-d-videos-por-tarefa",
    "L7-29-roteiro-demonstracao",
)

# Esta é a PRÓPRIA rodada que primeiro auditou os itens acima — não conta como "laudo prévio".
LAUDO_DESTA_RODADA = "linha-L7-laudo-adversario-2.md"


def _algum_laudo_adversario_previo_cita(item_id: str) -> bool:
    for caminho in HANDOFFS.glob("T*/linha-*-laudo-adversario-*.md"):
        if caminho.name == LAUDO_DESTA_RODADA:
            continue
        if item_id in caminho.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def _estado_do_item(item_id: str) -> str:
    dado = json.loads(ESTADO.read_text(encoding="utf-8"))
    item = next(i for i in dado["backlog"] if i["id"] == item_id)
    return item["estado"]


@pytest.mark.parametrize("item_id", ITENS_SEM_LAUDO_PREVIO)
# 18/09/2026: a marca xfail(strict=True) saiu porque o teste PASSA — rodado isolado na trilha `uniao`.
# Vale para os CINCO itens parametrizados.
# Nenhum dos cinco está hoje em estado=entregue sem laudo adversário anterior, então o portão HARD-03
# é respeitado e a asserção passa. ⚠ este teste lê laco/estado.json, que é dado VIVO: se um item novo
# voltar a virar entregue sem laudo, ele falha — e é exatamente isso que se quer dele agora.
# O texto que vem abaixo (docstring/nome) descreve o achado ORIGINAL, não o estado de hoje.
def test_item_so_tem_laudo_adversario_nesta_rodada(item_id):
    tinha_laudo_previo = _algum_laudo_adversario_previo_cita(item_id)
    estado_atual = _estado_do_item(item_id)
    assert not (estado_atual == "entregue" and not tinha_laudo_previo), (
        f"{item_id} está 'entregue' e nenhum laudo adversário anterior a esta rodada o auditou"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "laco/audita_ramo.sh não confere se a prova do ramo usou o mesmo ambiente/config que "
        "install.sh entrega (fixture/config própria passa sem aviso) — o padrão exato que "
        "derrubou L7-06-c nesta rodada (banca com nginx/config efêmeros, especificacao= "
        "explícito, nunca o FONTES_PADRAO/deploy/*.conf real)."
    ),
)
def test_audita_ramo_confere_equivalencia_de_ambiente():
    texto = (LACO / "audita_ramo.sh").read_text(encoding="utf-8")
    pistas = ("mesmo ambiente", "equivalente a produção", "mesmo config", "deploy/", "install.sh")
    achou = any(p in texto for p in pistas)
    assert achou, "audita_ramo.sh não confere equivalência entre o ambiente da prova e o de produção"
