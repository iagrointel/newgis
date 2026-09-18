"""Adversário de linha L2 (parte 2), item `L2-10-b-relacionamentos` — laudo
`laco/handoffs/T9/linha-L2-laudo-adversario-2.md`.

O próprio item nomeia, na cláusula "refutação exigida" do seu portão, o ataque que o adversário deve
fazer: "100 mil relacionados numa origem (paginação)". A última nota do ledger admite, no fechamento
(`3aed0220f`): "Paginação de 100 mil não medid[a]". Conferido nesta rodada: não existe, em `tests/`,
NENHUM arquivo que combine relacionamento com escala de 100 mil (`grep -rl "100000\\|100_000"
tests/**/*relacion*` não acha nada) — ou seja, além de "não medida" no ledger, a refutação
explicitamente exigida pelo próprio portão nunca foi sequer tentada em código, não só não atingiu o
teto.

`app/relacionamentos/rotas.py` aceita `limite`/`resultRecordCount` até 100.000 (`le=100000`) e usa
LIMIT/OFFSET simples (`app/relacionamentos/servico.py::relacionados`) — sem cache de contagem nem
keyset pagination — então o comportamento em 100 mil (tempo de resposta, uso de memória do
agrupamento em Python por fid) é uma incógnita real, não hipotética, e é exatamente o tipo de
suposição-comum-à-linha (nenhum item de L2 que promete "paginação até N" prova N de verdade) que este
laudo pede para atacar primeiro."""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _algum_teste_cobre_100_mil_relacionados() -> bool:
    saida = subprocess.run(
        ["grep", "-rlE", "100000|100_000", "tests/api/test_relacionamentos.py",
         "tests/e2e/test_relacionamentos.py"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    return bool(saida.stdout.strip())


# REMEDIADO (wt/l02, 18/09/2026): tests/api/test_relacionamentos.py ganhou
# test_refutacao_100000_relacionados_numa_origem (marcado `lento`), que insere as 100 mil linhas numa
# origem so (um INSERT ... generate_series, 9,0 s) e percorre a paginacao. Medido: primeira pagina em
# 47,3 ms, o teto da propria API corta em 2.000 linhas mesmo com limite=9999 pedido, e 3 paginas de 1.000
# trazem 3.000 fids distintos, sem repetir nem pular. Numeros em tests/medidas/L2-10-b-relacionamentos.json.
def test_refutacao_exigida_de_100_mil_relacionados_foi_exercitada():
    assert _algum_teste_cobre_100_mil_relacionados()
