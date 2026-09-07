# ADR 20260907T1245 — explicação da nota do motor multicritério (item L3-01-f-explicacao)

## Contexto

O item pede a resposta a "por que esta unidade tem nota N": fator → valor bruto (com unidade e
fonte) → transformação aplicada → favorabilidade → peso → contribuição, soma, veto e cobertura.
O portão exige que essa explicação bata (|Δ| ≤ 0,5) com a favorabilidade já gravada em
`plat.amc_resultado` sobre 100 unidades sorteadas, sem inventar número novo.

## Decisão 1 — recalcular na hora, nunca gravar uma tabela própria de "explicação"

`app/amc/explicacao.py::montar_explicacao` lê `plat.amc_fator_bruto` e a definição/pesos
congelados da execução e refaz o cálculo do zero, chamando o MESMO combinador de
`app/amc/combinacao.py` (item L3-01-e, entregue). Não existe `plat.amc_explicacao` nem
qualquer outra tabela paralela. Consequência: a explicação nunca pode divergir do resultado
gravado por drift de um segundo caminho de código — ela É o mesmo caminho, chamado de novo. O
único jeito de a explicação divergir do gravado é o próprio motor ter mudado de versão entre a
execução e a consulta (o campo `delta` existe para tornar isso visível, não para escondê-lo).

## Decisão 2 — vocabulário duplicado entre L3-01-a e L3-01-e é traduzido, não refeito

O esquema do modelo (`docs/esquemas/amc_modelo.v1.json`, item L3-01-a) e o combinador
(`app/amc/combinacao.py`, item L3-01-e) nasceram em trilhas diferentes e escolheram nomes
diferentes para os mesmos conceitos: `soma_ponderada_normalizada` (esquema) é `soma_ponderada`
(combinador); `excluir_fator`/`unidade_nula`/`nota_pessimista` (esquema) são
`excluir`/`nulo`/`pessimista` (combinador). `MAPA_COMBINADOR` e `MAPA_POLITICA` em
`explicacao.py` fazem essa ponte num só lugar; dois testes (`test_mapa_combinador_cobre_todo_o_
enum_do_esquema`, `test_mapa_politica_cobre_todo_o_enum_do_esquema`) provam que o mapa cobre o
enum inteiro do esquema, para que um valor novo no esquema quebre o teste em vez de cair
silenciosamente em `KeyError` na rota.

## Decisão 3 — transformação contínua fora de escopo aparece declarada, nunca com número fabricado

Os quatro tipos declarativos do esquema (`categoria`, `faixas`, `linear`, `degraus`) são
implementados por inteiro aqui porque são inequívocos a partir do próprio JSON Schema. As doze
funções contínuas do Rescale by Function (item L3-01-d-transformacoes, pendente) exigem
verificação cruzada contra a documentação do ArcGIS Pro por um adversário antes de qualquer
implementação valer — fabricar a fórmula aqui, sem essa verificação, arriscaria gravar um número
errado numa explicação que pesa em decisão de negócio. Por isso um fator com transformação
contínua aparece na tabela com valor bruto, unidade e fonte, `favorabilidade_fator = None` e uma
observação nomeando a lacuna (`L3-01-d-transformacoes`), nunca um número inventado.

## Decisão 4 — contribuição por fator só existe quando o combinador é aditivo

`soma_ponderada` e `percentual` decompõem exatamente em `peso·favorabilidade / Σ peso` por fator
com dado presente (a mesma regra de presença de `combinacao._aplica_politica`, replicada aqui
para decompor por fator). Os cinco combinadores fuzzy (`minimo`, `maximo`, `produto`,
`soma_fuzzy`, `gama`) não decompõem por definição matemática — a tabela mostra a favorabilidade
de cada fator, mas `contribuicao = None` em todas as linhas, com uma observação explícita de que
a soma das contribuições não é comparável à favorabilidade da unidade. Nunca se finge uma
decomposição que a matemática do combinador não sustenta.

## Decisão 5 — a rota nunca recalcula o veto

`GET /api/amc/execucoes/{execucao_id}/unidades/{unidade_id}/explicacao`
(`app/amc/rotas.py::explicar_unidade`) lê `vetado`/`motivo` de `plat.amc_resultado` quando a
execução já tem resultado, e devolve os dois tal como gravados. A avaliação de restrição
(camada de veto) é objeto de outro item da linha L3; explicar por que uma unidade tem uma nota
não é o lugar de recalcular se ela deveria ter sido vetada. Uma unidade vetada continua
mostrando a tabela de fatores inteira — "o porquê da nota que a unidade TERIA, mesmo vetada" —
porque o portão pede "mostra fator e motivo", não só o motivo isolado.

## Decisão 6 — painel web em `/amc/explicacao/<execucao_id>/<unidade_id>`

`web/amc_explicacao.html` + `web/js/amc/explicacao_pagina.js` seguem o mesmo padrão de página do
resto do produto (`app/paginas.py`, `montarLayout`, `<plat-aviso>`, `body[data-pronto=1]`): uma
tela sem build, que busca a mesma rota e monta a tabela. O e2e
(`tests/e2e/test_amc_explicacao.py`) segue o padrão de `tests/e2e/test_mapa.py`: salta quando
`PLAT_URL_PUBLICA` da trilha não resolve (a URL de trilha é deliberadamente inválida — ver
`laco/trilha_ambiente.sh`) e roda de verdade em homologação/CI, onde a URL pública existe.

## Prova do portão

`tests/unit/test_amc_explicacao.py::test_montar_explicacao_100_unidades_sorteadas_bate_
combinacao_independente` gera 100 unidades sintéticas (seed fixa) e confere `|Δ| ≤ 0,5` contra
uma chamada independente a `combinacao.combinar`. `tests/api/amc/test_explicacao_api.py` refaz a
mesma prova sobre uma execução real da API (modelo, conjunto e execução criados pelas rotas,
fator bruto e resultado gravados direto no banco) e cobre veto, 404 de unidade sem extração e
latência ≤ 100 ms (medida só com a máquina calma; ver `tests/medidas/L3-01-f-explicacao.json`).
