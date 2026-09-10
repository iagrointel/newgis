# Localizar regiões sobre a favorabilidade (item L3-05-localizar-regioes)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L3L6_CONCEITO.md` (motor multicritério), item
L3-01-e-combinacao (a favorabilidade que entra aqui), item L3-19-multiescala (a grade e a execução).
Referência de paridade: Locate Regions do ArcGIS Pro, página lida em 08/09/2026 (`docs/PARIDADE.md`).

## Contexto

O motor multicritério responde "quanto vale cada célula". A pergunta seguinte, que o usuário faz sempre, é
"então ONDE ficam as N áreas que eu devo olhar". Isso não é limiar nem top-N de células soltas: pede regiões
CONTÍGUAS, com área alvo, tamanho mínimo e máximo, distância entre elas e um compromisso entre a forma da
região e a utilidade das células.

## Decisão

1. **Crescimento de região por fila de prioridade**, uma semente por bloco da grade (a célula de maior
   favorabilidade do bloco), em número declarado. Sementes proporcionais à favorabilidade sem espalhamento
   devolveriam N vezes o mesmo pico — o bloco é o que garante candidatas distintas.
2. **Prioridade = `(1 − c)·utilidade + c·forma`**, `c = compromisso/100`. `forma` é a distância à semente na
   MÉTRICA da forma-alvo (euclidiana para círculo, Chebyshev para quadrado, hexagonal para hexágono),
   normalizada pelo raio da forma de área FINAL. Normalizar pelo raio CORRENTE foi a primeira versão e está
   errado: nas primeiras células o raio é ~0,5 e o termo satura, o crescimento perde a forma — medido,
   compacidade 0,61 contra 0,95 com o raio final.
3. **Compacidade medida em célula, não em perímetro**: fração das células da região que cabem na forma-alvo de
   mesma área centrada no centróide. O perímetro de uma forma digitalizada é uma escada e faria um disco
   perfeito "perder" compacidade; a medida em célula dá 1,0 para o disco e é o que o portão do item exige.
4. **Fechar buraco nunca engole veto**: com `sem_ilhas` (o `NO_ISLANDS` da referência), o buraco é preenchido e
   depois intersectado com as células que têm dado — mais estrito que a referência.
5. **A área alvo é respeitada por convergência**: fechar buracos ACRESCENTA células, então o crescimento é
   repetido com o alvo descontado do excedente (no máximo 5 voltas). Sem isso a área estourava 7,4 % com
   `sem_ilhas` ligado; com isso fica em 0 %.
6. **Determinismo**: o único sorteio é o desempate entre células de mesma favorabilidade, com gerador semeado
   (`semente_aleatoria`). Mesma semente, resposta idêntica — a refutação do item.
7. **A rota é síncrona e não grava nada**: localizar regiões é uma pergunta sobre a execução. O teto de células
   por chamada é declarado (`REGIOES_CELULAS_MAX = 4.000.000`); a grade de 1 milhão roda em 3,4 s (N = 3) e
   9,1 s (N = 10), medidos. Quem quiser guardar a resposta cria um item com o GeoJSON devolvido.

## Consequências

- A distância entre regiões é medida entre CENTRÓIDES, não entre bordas: é o que a implementação faz e o que a
  documentação diz; a referência não define qual das duas usa.
- Quatro dos oito métodos de avaliação da referência e três das sete formas: os do item. O que falta está
  nomeado na tabela de paridade, não escondido.
- `Resolution of the Growth` é aceito e validado, mas hoje não muda o resultado (o crescimento é sempre na
  resolução da grade). Está declarado como "parcial (declarado, sem efeito)" na paridade.
- Não há tela nesta fatia: a rota devolve GeoJSON pronto para o mapa; a tela do motor é o item L3-01-g.
