# ADR — Justiça entre inquilinos na fila de jobs (item L0-05-e-justica-entre-inquilinos)

Data: setembro de 2026. Situação: aceito.

## 1. Problema medido

A fila (`plat.job_pegar`, migração 006) escolhia o próximo job por uma ordem GLOBAL: prioridade, depois
`agendado_para`, depois `criado_em`. Com um único processo de worker, isso é o comportamento de uma fila
serial: quem chega primeiro roda primeiro, sem olhar de quem é o job. No turno 2 mediu-se o efeito: dois jobs
de 300 s de um inquilino deixaram um job de 0 s de outro inquilino esperando 10 minutos. O tempo de espera de
um inquilino passa a depender do volume de trabalho dos outros, que ele não controla e não vê.

## 2. Decisão

A primeira chave de ordenação passa a ser o TURNO do inquilino: `max(iniciado_em)` entre os jobs daquele
inquilino, com `NULLS FIRST`. Quem foi atendido há mais tempo (ou nunca foi atendido) vem primeiro. Só depois
valem prioridade, `agendado_para` e `criado_em`, que continuam ordenando a fila DENTRO de cada inquilino.
É um rodízio: com dois inquilinos e um worker, o escalonador alterna entre eles a cada retirada, então um job
curto de A espera no máximo o job de B que já está rodando — um job, não a fila inteira de B.

O turno é calculado só sobre os inquilinos que têm job pronto a rodar naquele instante (CTE `aptos`), para não
varrer a tabela inteira. Um índice parcial `(tenant_id, iniciado_em) WHERE iniciado_em IS NOT NULL` apoia esse
cálculo. Nada mais do `job_pegar` muda: o filtro de chave em série, a cota de simultâneos por inquilino
(`plat.cota_jobs_simultaneos`) e o filtro de job pesado continuam iguais, e a assinatura da função é a mesma
(a migração é `CREATE OR REPLACE`, os `GRANT` da 006/013 seguem valendo).

## 3. Alternativas descartadas

- **Rodízio ponderado por contagem de jobs atendidos.** Exige guardar um contador por inquilino e decidir o
  que fazer quando ele envelhece. O `max(iniciado_em)` já é um relógio de última atenção, está na própria
  tabela, e envelhece sozinho.
- **Uma fila por inquilino com N vagas, materializada em outra tabela.** Estrutura nova, duas fontes de
  verdade para o mesmo estado e migração de dado. A cota de simultâneos por inquilino, que já existia, cobre a
  parte de "N vagas"; faltava só a ORDEM entre inquilinos.
- **Fatia de tempo (preempção).** Interromper job em curso para dar a vez a outro inquilino exige que toda
  tarefa saiba parar e retomar. Não é o caso das tarefas de hoje, e o portão não pede isso.

## 4. Limite honesto

Com mais de um worker a justiça é estatística, não exata: cada worker decide por uma foto do instante do seu
`SELECT ... SKIP LOCKED`, então dois workers podem, no limite, atender o mesmo inquilino duas vezes seguidas.
Com um worker — o caso do portão e o da instalação padrão — a alternância é exata. O rodízio também não é
proporcional a tamanho de job: um inquilino que só manda jobs de 300 s ocupa mais máquina que um que só manda
jobs de 1 s, mesmo alternando a cada retirada. Limitar isso é assunto de cota, não de ordem.

## 5. Efeito visível: posição na fila

A leitura de job (`app/jobs/servico.py`) passa a devolver `posicao_fila` para job pendente: a posição dele na
fila DO INQUILINO, pela mesma chave que ordena a fila interna (1 = o próximo quando chegar a vez daquele
inquilino). Fora de `pendente` o campo é nulo. Não existe posição global a mostrar, porque entre inquilinos a
ordem é decidida pelo rodízio a cada retirada — mostrar um número global seria mostrar uma promessa falsa. A
tela Tarefas escreve esse número na coluna de progresso (`web/js/jobs/formato.js`).

## 6. Provas

`tests/api/jobs/test_jobs_justica.py` (fila e cota) e `tests/unit/test_jobs_posicao_fila_tela.py` (texto da
coluna, executado no mesmo motor do navegador). Medidas em
`tests/medidas/L0-05-e-justica-entre-inquilinos.json`.
