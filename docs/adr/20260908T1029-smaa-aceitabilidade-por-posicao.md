# ADR — SMAA-2 simplificado: aceitabilidade por posição, vetor central e fator de confiança

Estado: aceito. Item `L3-02-c-smaa` (linha L3, motor multicritério).

## Contexto

O item L3-02-a entregou o sorteio de pesos e o resumo de sensibilidade por unidade (mínimo, média,
máximo, desvio, frequência no top-k). Falta a pergunta inversa, prevista na decisão A9 do conceito da
linha: "que pesos fariam esta unidade ganhar". No vocabulário do SMAA-2 (Lahdelma e Salminen, 2001)
isso é o índice de aceitabilidade por posição, o vetor central de pesos e o fator de confiança.

## Decisão

1. **Módulo separado, sorteio reusado.** `app/amc/smaa.py` não reimplementa nem o sorteio nem a
   combinação: chama `app.amc.robustez.sortear_pesos` (item L3-02-a) e `app.amc.combinacao.combinar`
   (item L3-01-e). Se o sorteio mudar, os dois produtos mudam juntos, e a invariância de ordem dos
   fatores conquistada no L3-02-a vale aqui de graça (há teste que a exercita).
2. **Job próprio (`amc.smaa`), não rota síncrona.** Mesma razão da decisão A8 para a robustez: N
   sorteios em milhares de unidades passa do orçamento de uma requisição. A API existente de jobs já
   entrega criação, progresso, cancelamento e leitura do resultado — não se acrescenta rota nova.
3. **Fator de confiança MEDIDO, não assumido.** Com combinador linear e fator determinístico a região
   de pesos vencedores é convexa e o fator daria 1 sempre; poderia ser escrito como constante. Não é:
   a combinação é refeita com o vetor central de cada unidade que ganhou ao menos uma vez, o que custa
   uma combinação por unidade vencedora e passa a separar de verdade quando o combinador é não linear.
   Constante disfarçada de medida é a pior coisa que se pode pôr num produto que se diz auditável.
4. **Contagem até a posição 20, tabela das 20 melhores.** Guardar aceitabilidade em todas as posições é
   uma matriz unidade × unidade; o produto mostra tabela do topo. O recorte é parâmetro (`posicoes`,
   `topo`) e a saída declara qual foi usado, para ninguém ler "zero em toda posição" como "último".
5. **Empate desempatado pela ordem da unidade na matriz**, sempre, para que a soma da aceitabilidade de
   primeiro lugar seja exatamente 1 (cada sorteio tem um vencedor só) e o resultado seja reproduzível.
   O número de sorteios com empate no primeiro lugar vai na saída.
6. **Só agregados por unidade** (A9): aceitabilidade por posição, vetor central, fator de confiança,
   média da nota e semente. Nunca N × unidades.

## Alternativas descartadas

- Guardar cada sorteio para calcular a aceitabilidade depois: A9 já decidiu contra, por memória.
- Estimar o vetor central resolvendo o poliedro de pesos vencedores em vez de tirar a média dos
  sorteios: é exato, mas exige programação linear por unidade e só funciona com combinador linear; a
  média sobre os sorteios vale para qualquer combinador e é o que o artigo de 2001 propõe.
- Escrever o fator de confiança como 1: ver decisão 3.

## Consequências

O resultado é uma estimativa por amostragem, com a semente gravada. Os limites (incerteza só no peso,
fator de confiança degenerado com combinador linear, recorte de posições, empate por ordem) estão
escritos em `docs/AMC_SMAA.md` e viajam dentro da própria saída, no campo `limites`.
