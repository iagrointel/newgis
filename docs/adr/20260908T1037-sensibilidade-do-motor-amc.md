# Sensibilidade do motor multicritério: Sobol global e tornado local (item L3-02-b)

Estado: aceito. Contexto: item L3-02-b do laço PLATAFORMA ENTERPRISE, linha L3 (motor AMC).

## Decisão

1. **Duas leituras, não uma.** O índice de Sobol (global) varre pesos e parâmetros de transformação ao
   mesmo tempo e enxerga interação; o tornado um-fator-por-vez (local) é o que o usuário lê na tela e é
   cego a interação. As duas saem no mesmo relatório, com o método escrito ao lado de cada uma.
2. **Amostragem e estimadores.** Amostra de Saltelli sobre a sequência de Sobol de `scipy.stats.qmc`
   (dependência já instalada, nada novo). Primeira ordem pelo estimador de Saltelli 2010, total pelo de
   Jansen 1999. N declarado em toda saída, obrigatoriamente potência de 2, e semente gravada: mesma
   semente, mesmo resultado bit a bit. O custo é N·(g+2) recombinações, e é por isso que a análise é um
   tipo de job (`amc.sensibilidade`), como o sorteio do item L3-02-a.
3. **Intervalo por reamostragem (bootstrap) das LINHAS da amostra**, não por avaliação nova da função:
   o intervalo custa memória, não tempo de modelo.
4. **Irrelevante é o índice TOTAL abaixo de 0,01**, nunca o de primeira ordem. A terceira variável do
   Ishigami prova por que: efeito próprio zero, efeito total 0,24 por interação.
5. **A validação é a função de Ishigami**, cujos índices têm forma fechada. É o que separa "o estimador
   está certo" de "o modelo é assim": o teste compara contra o valor analítico, não contra si mesmo.
6. **Índice de GRUPO** (`grupos=`) porque a mesma camada pode entrar mais de uma vez no modelo. Somar o
   índice total de cada cópia conta a interação entre elas duas vezes; o índice do grupo conta uma vez.
7. **Comparar fator único com fator repartido exige alargar a faixa das cópias por √n**
   (`faixa_de_copias`): duas metades sorteadas de forma independente na mesma faixa relativa têm metade
   da variância do peso somado, e o índice cairia por causa da conta, não do modelo.
8. **Regra de linguagem**, herdada do item L3-02-a e obrigatória em toda saída: o que se mede é a
   dependência do MODELO ao peso escolhido pelo usuário, nunca a importância real do fator no
   território. Um fator decisivo na realidade sai com índice baixo se o dado dele quase não varia na
   área de estudo. Não existe aqui nenhuma noção de peso ótimo.

## Consequências

- O relatório é um dicionário serializável (sem `NaN`), pronto para a tela e para o PDF de explicação.
- Com combinador que normaliza pela soma dos pesos, só o peso relativo conta: o índice de primeira
  ordem sai baixo por construção e o relatório avisa que o número a ler é o total.
- Parâmetro de transformação entra pela função que o chamador passa, sem este módulo precisar conhecer
  a lista de transformações do item L3-01-d — que ainda não está em master.
