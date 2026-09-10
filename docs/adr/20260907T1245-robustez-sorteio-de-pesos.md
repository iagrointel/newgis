# Robustez do motor multicritério por sorteio de pesos (Monte Carlo) — item L3-02-a

Data: 07/09/2026.

## Contexto

O item L3-01-e entregou o combinador puro (`app.amc.combinacao.combinar`), 1,49 ms por recálculo em
4.346 unidades × 19 fatores. O item L3-02-a usa esse combinador N vezes com pesos sorteados para medir
**sensibilidade** do resultado ao peso escolhido pelo usuário — nunca para achar um "peso ótimo": não
existe otimização aqui, só a pergunta "o quanto o resultado se mexe se o peso mudar dentro de uma faixa
declarada".

Decisões de conceito que este item obedece (`laco/decomposicao/L3L6_CONCEITO.md`):

- A9: agregados por unidade (mínimo, média, máximo, desvio, frequência no top-k e no decil superior) +
  semente gravada; nunca N × unidades armazenado. Dirichlet no simplex ou faixa ± k % declarada.
- A6: veto e restrição nunca entram no sorteio — são objetos separados do peso, fixos em todos os N
  sorteios, e a unidade vetada é excluída da classificação por construção.
- A8: robustez roda como JOB (`amc.robustez_pesos`), porque N=1.000 sorteios em milhares de unidades
  passa do orçamento de uma requisição síncrona, ainda que cada sorteio isolado seja barato.

## Decisão

`app/amc/robustez.py` (puro, sem I/O, sem banco): `sortear_pesos()` e `simular_robustez()`. A combinação
em si é sempre `app.amc.combinacao.combinar` (item L3-01-e), chamada uma vez por sorteio — este módulo
não reimplementa a combinação.

**Invariância de ordem** (a refutação do item exige que permutar a ordem dos fatores e reexecutar com a
mesma semente dê o mesmo resultado): o sorteio de peso acontece numa ORDEM CANÔNICA derivada só dos IDs
dos fatores (`np.argsort` dos IDs, nunca da posição de entrada) e só depois é remapeado de volta para a
ordem em que o chamador passou `pesos_base`/`ids_fatores`/`fatores`. Isso torna o sorteio de peso por ID
idêntico bit a bit independentemente da ordem de entrada. A NOTA final agregada (soma ponderada) pode
diferir na última casa decimal sob permutação porque soma de ponto flutuante não é perfeitamente
associativa — por isso a comparação de nota no teste do adversário usa tolerância 1e-9, e a comparação
de frequência/estabilidade (derivada de RANKING, não de soma) permanece exata.

**Vetos nunca sorteados**: `fracao_vetada` é parâmetro fixo, aplicado identicamente em todos os N
sorteios. A classificação (top-k, decil superior) marca a unidade vetada com nota `-inf` ANTES de
ordenar, então a exclusão do topo é garantida por construção, não pela nota calculada ficar baixa —
testado com uma unidade que teria a nota MÁXIMA de todo o conjunto sem o veto.

**Métodos de sorteio**: `dirichlet` (concentracao=None cobre o simplex inteiro; concentracao>0 concentra
ao redor do peso base) e `faixa` (cada peso em `[base·(1−k), base·(1+k)]`, independente por fator, sem
precisar somar 1 — o combinador já normaliza pela soma dos pesos presentes).

**Job**: `app/amc/tarefas.py` registra `amc.robustez_pesos` (`pesado=True`, `timeout_s=120`). O
resultado (agregados + semente, nunca a matriz N × unidades) vai para `job.resultado` (jsonb genérico,
migração 004) — sem tabela nova, porque A9 já manda guardar só agregados.

## Alternativas descartadas

- Guardar cada sorteio (N × unidades): rejeitado por A9 (custo de armazenamento sem uso — o produto
  final é o resumo, não a trajetória).
- SMAA-2 / Sobol (citados em A9 como próximos passos): fora do escopo deste item; ficam para item
  futuro quando houver necessidade de "que pesos fariam esta unidade ganhar" — este item entrega só o
  sorteio de sensibilidade em torno do peso escolhido.

## Medido

`tests/medidas/L3-02-a-monte-carlo-pesos.json`: 1.000 sorteios em 5.000 unidades × 8 fatores, como job
(`amc.robustez_pesos`, `ContextoJob` sem banco), em 0,767 s — 78× dentro do limite de 60 s, medido com
carga de 1 min 12,94 (12 núcleos): passou com folga mesmo sob disputa de máquina, então conta como
medido (regra do brief comum das trilhas, seção "cláusula de desempenho").
