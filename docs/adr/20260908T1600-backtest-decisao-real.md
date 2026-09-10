# Backtest contra decisão real (item L3-09-backtest-decisao-real)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L3L6_CONCEITO.md` (motor multicritério), item
L3-01-e-combinacao (a favorabilidade), item L3-19-multiescala (a grade e a execução).

## Contexto

O motor diz onde DEVERIA ser bom. A pergunta que o cliente faz em seguida é: "e onde as pessoas já
escolheram?". O motor de LT da casa já fazia isso à mão; este item o traz para a plataforma como pergunta
sobre uma execução.

## Decisão

1. **Quatro medidas, na ordem do item**: percentil das escolhas no ranking; nulo por permutação (N sorteios de
   igual número de unidades na mesma grade); AUC (Mann-Whitney com postos médios, empate contando meio) com
   p-valor de uma cauda `(1 + #{nulo ≥ observado}) / (N + 1)` (correção de continuidade: um p-valor por
   permutação nunca é 0); e preferência revelada por fator.
2. **Preferência revelada é SINAL e ORDEM, nunca peso**: `evitamento = 1 − (fração das escolhas na metade alta
   do fator ÷ fração do nulo na mesma metade)`, com a metade alta definida pela mediana DA GRADE. Positivo =
   evitou, negativo = procurou. O relatório não tem campo de peso, e o teste garante que não passe a ter: quem
   escolhe peso é o usuário (regra do motor).
3. **As duas ressalvas do item saem SEMPRE no relatório, não em rodapé**: o backtest mede concordância com a
   decisão passada e não acerto futuro; e fatores de distância se confundem entre si e com a escolha. Quando a
   camada de escolhas é mais nova que a decisão, entra a terceira, em maiúsculas: ANACRÔNICO.
4. **AUC indefinida é dita, não maquiada**: escolhas = todas as unidades não dão 0,5 nem 1,0 — não existe
   AUC. O relatório devolve `auc: null` com a frase que a tela mostra, e continua devolvendo o percentil, que
   ainda faz sentido. Escolha que não cai em nenhuma célula vira `n_fora`, que aparece no relatório.
5. **Unidade sem nota sai das duas contas** e o número entra nas ressalvas: comparar contra célula sem
   favorabilidade seria comparar com nada.
6. **A rota não grava e não lê fora do inquilino**: as escolhas entram por camada hospedada do próprio
   inquilino ou por lista de pontos. O dado aberto do teste (galpões e vias do OpenStreetMap na base da casa)
   é lido pela FIXTURE, como a casa leria qualquer dado antes de trazê-lo — o papel da plataforma não tem, e
   não deve ter, acesso ao schema de outra frente.

## Consequências

- Medido sobre dado aberto real (602 galpões OSM com área > 5.000 m² numa janela de 30 km × 22 km, grade de
  500 m, modelo de um fator "proximidade de via arterial"): AUC 0,718, percentil mediano 74,8, p-valor 0,002
  contra 500 permutações. É sinal de verdade, e é só isso: um fator só, e distância confunde.
- Calibragem que fecha o portão: escolhas geradas pelo próprio modelo dão AUC 1,000; escolhas ao acaso dão
  0,517 numa tirada e 0,4993 na média de 20, com desvio medido de 0,0145 (o teórico é 0,014).
- O p-valor é de UMA cauda: um modelo que erra sistematicamente (AUC 0,0) recebe p ≈ 1, não p ≈ 0.
- Sem tela nesta fatia: o relatório é JSON pronto para a tela do motor (item L3-01-g).
