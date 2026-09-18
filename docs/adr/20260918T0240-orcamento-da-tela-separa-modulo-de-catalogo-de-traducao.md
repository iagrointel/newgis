# O orçamento de 400 kB por tela mede MÓDULO; o catálogo de tradução passa a ter orçamento próprio

Item L0-03-f-tela-conteudo. Estado: aceito.

## Contexto

O ADR 0001 seção 11.2 item 4 diz: "módulo próprio ≤ 60 kB (...) quando a soma dos módulos de uma tela
passar de 400 kB, o item que causou isso reavalia esta seção em ADR novo". Este é esse ADR.

A tela `/conteudo` reprova o orçamento: o e2e mede **511 kB**. A medição é feita no navegador somando o
`decodedBodySize` de tudo que a navegação buscou sob `/static/js/`. Medido em 18/09/2026, o que compõe
esses 511 kB é:

| parte | kB | o que é |
|---|---|---|
| 48 módulos ES da tela (grafo de `import` a partir de `catalogo/conteudo.js`) | 314,6 | código |
| `/static/js/i18n/pt-BR.json` | 193,9 | catálogo de tradução do PRODUTO INTEIRO (3.619 chaves) |

Nenhum módulo isolado passa dos 60 kB (o maior é `catalogo/item.js`, 35,4 kB). O que estourou o teto não
foi a tela crescer: foi o catálogo de tradução morar em `web/js/i18n/` e, por isso, cair dentro do filtro
`/static/js/` da medição. O catálogo é o mesmo arquivo em TODA tela do produto e cresce a cada item novo
do laço — com a regra escrita como está, um item que só acrescenta texto traduzido empurra todas as telas
para fora do orçamento, e a tela que reprovar primeiro é a que por acaso for medida.

Dois erros opostos a evitar: (a) manter a conta como está e deixar o número dizer uma coisa que ninguém
controla no item — o orçamento vira ruído e o próximo agente o ignora; (b) tirar o catálogo da conta e
declarar a tela em dia — isso apaga 193,9 kB que o usuário baixa de verdade, e é mover a trave.

## Decisão

1. O orçamento de **400 kB por tela vale para os MÓDULOS** (o grafo de `import` da tela). É o número que o
   item da tela controla e é o que a regra sempre quis dizer: "quando um módulo passar do orçamento,
   divide-se" só faz sentido sobre código.
2. O **catálogo de tradução ganha orçamento próprio e explícito: 220 kB**, medido à parte e gravado à
   parte em `tests/medidas/`. Hoje está em 193,9 kB. Quando passar de 220 kB, a saída NÃO é subir o teto:
   é partir o catálogo por tela (carregar só as chaves da tela, com o comum à parte), que é trabalho de um
   item próprio da trilha de interface e não cabe dentro do item de uma tela.
3. As duas medidas continuam sendo tomadas no NAVEGADOR, na mesma navegação, e as duas reprovam o e2e.
   Nenhuma sai do laudo: quem lê `tests/medidas/L0-03-f-tela-conteudo.json` vê os dois números e a soma.

## Consequência medida

`/conteudo` em 18/09/2026: módulos 314,6 kB (teto 400), catálogo 193,9 kB (teto 220), soma 508,5 kB. A
tela passa nos dois orçamentos e o total que o usuário baixa continua publicado, sem maquiagem.

## O que fica de fora, e por quê

`web/js/base/i18n.js` busca o catálogo com `cache: 'no-store'`, então os 193,9 kB voltam do servidor a
cada navegação, não só na primeira. É desperdício real e está NOMEADO aqui, mas mudar política de cache de
um arquivo servido pelo nginx mexe em como toda tela do produto revalida tradução — é item próprio, com
e2e de tradução velha depois de um deploy, e não uma linha solta dentro do item de uma tela.
