"""Adversário de linha L7 operação (parte 1) — item `L7-11-b-appliance-sem-internet`
(laudo `laco/handoffs/T9/linha-L7-laudo-adversario-1.md`).

Portão literal do item: "teste sobe o compose numa rede docker `--internal` (sem saída) e roda o e2e
inteiro: 0 pedido a host externo [...]". `docs/APPLIANCE.md` §4 já documenta, com as próprias palavras do
item, que essa cláusula **nunca rodou nesta máquina** — o que rodou foi uma prova diferente e mais fraca
(e2e contra a instalação systemd da trilha, atrás de um proxy de captura HTTP), que prova que o NAVEGADOR
não sai, não que o APPLIANCE containerizado (sem imagens construídas — ver `L7-01-a`) sobe e funciona sem
rede.

Este teste lê o próprio `docs/APPLIANCE.md` e falha se a confissão sumir sem que a prova real (subida do
perfil `appliance` numa rede `--internal`) exista de fato — a segunda metade do teste confere que a rede
`--internal` de verdade nunca foi criada por este item (nenhuma rede docker chamada como tal, e as imagens
do perfil appliance seguem ausentes, ver `L7-01-a`).

xfail(strict=True): quando o item rodar a prova de verdade (imagens construídas, rede `--internal` criada,
e2e do appliance real), a confissão em APPLIANCE.md muda e este teste passa "de verdade"."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
APPLIANCE_MD = RAIZ / "docs" / "APPLIANCE.md"


def _imagens_pendentes() -> list[str]:
    versoes = (RAIZ / "deploy" / "compose" / "VERSOES.txt").read_text()
    return [linha for linha in versoes.splitlines() if "PENDENTE" in linha]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "docs/APPLIANCE.md §4 confirma, nas próprias palavras do item, que a rede docker --internal do "
        "perfil appliance (cláusula central do portão de L7-11-b) 'Não executado nesta máquina' — as "
        "imagens do perfil appliance seguem PENDENTE em deploy/compose/VERSOES.txt (mesmo bloqueio de "
        "L7-01-a). A prova que rodou (e2e atrás de proxy de captura contra a instalação systemd da "
        "trilha) é diferente do que o portão pede."
    ),
)
def test_rede_internal_do_appliance_foi_executada():
    texto = APPLIANCE_MD.read_text()
    assert "Não executado nesta máquina" not in texto, (
        "docs/APPLIANCE.md §4 ainda confessa que a prova em rede --internal nunca rodou"
    )
    pendentes = _imagens_pendentes()
    assert not pendentes, f"imagens do perfil appliance ainda PENDENTE: {pendentes}"
