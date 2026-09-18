"""Adversário da linha L4 rede de utilidades (rodada 2) — item L4-13-integracao-telemetria.

O portão (LITERAL) tem duas cláusulas de DESEMPENHO nomeadas: "simulador de 20 sensores de trafo
(corrente por fase 5 min, temperatura, tensão 10 min) publica e a ficha do trafo mostra a última
leitura em ≤ 5 s" e "consulta de 1 mês de 20 sensores em tempo medido". A convenção da casa para
cláusula de tempo/taxa/vazão (`laco/BRIEF_WORKTREES.md` — "Cláusula de DESEMPENHO") é gravar o número
ao lado da carga da máquina em `tests/medidas/<item>.json`.

`tests/api/test_rede_medicao.py` (o arquivo de testes do item) prova idempotência, recusa de ts
futuro/unidade errada, isolamento entre inquilinos, alarme e agregação a jusante — mas nenhum teste
publica 20 sensores, nenhum mede a latência da ficha do ativo, e nenhum consulta 1 mês de leituras
medindo o tempo. `tests/medidas/L4-13-integracao-telemetria.json` não existe. A "última nota do ledger"
do item no brief também está vazia (`—`), diferente de todo item irmão desta linha, que tem nota com
número. O item está registrado como ENTREGUE sem que as duas cláusulas quantitativas do seu próprio
portão tenham sido tentadas — mesmo padrão do achado #4 da rodada 2 do adversário de L2 (cláusula do
portão nomeada, sem teste correspondente).

CONSERTO (construtor, 18/09/2026): `tests/api/test_rede_medicao_desempenho.py` simula os 20 sensores do
portão (corrente por fase + temperatura a cada 5 min, tensão a cada 10 min), semeia 30 dias × 20 sensores
(777.600 leituras) e mede as duas cláusulas — ficha de cada trafo com a leitura do ciclo em 684 ms do POST
à última ficha (teto 5 s) e consulta de 1 mês dos 20 sensores (172.780 pontos) em 1.149 ms — gravando
`tests/medidas/L4-13-integracao-telemetria.json` com carga da máquina ao lado. Este teste do adversário
perde o xfail e fica de pé como guarda: se a medida sumir ou voltar incompleta, ele reprova de novo."""

import json
from pathlib import Path

MEDIDAS = Path(__file__).resolve().parents[1] / "medidas" / "L4-13-integracao-telemetria.json"


def test_portao_de_l4_13_tem_medida_gravada_de_latencia_e_de_consulta_de_1_mes():
    assert MEDIDAS.exists(), f"{MEDIDAS} não existe: as cláusulas de desempenho do portão nunca foram medidas"
    dados = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    for chave in ("latencia_ultima_leitura_ms", "consulta_1_mes_20_sensores_ms", "carga_1min", "ram_livre_gb"):
        assert chave in dados, f"medida incompleta: falta {chave!r} em {MEDIDAS}"
