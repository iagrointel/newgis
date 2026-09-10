# SMAA-2 simplificado no motor multicritério (item L3-02-c)

O motor multicritério responde "qual é a nota desta unidade com o peso que o usuário escolheu". O SMAA
responde a pergunta inversa: **que pesos precisariam ser verdade para esta unidade ficar em primeiro
lugar**. É a mesma matriz de fatores já extraída, recombinada com milhares de vetores de peso sorteados.

Código: `app/amc/smaa.py`. Tipo de job: `amc.smaa`. Sorteio de peso reusado de `app/amc/robustez.py`
(item L3-02-a); combinação reusada de `app/amc/combinacao.py` (item L3-01-e).

## Referência

Lahdelma, R. e Salminen, P. (2001). "SMAA-2: Reference Point Based Preference Modeling Rendering
Aggregation Method for Group Decision Making". *Operations Research* 49(3), 444-454.

Do artigo vêm as três medidas que a saída traz, com os nomes dele:

| medida | símbolo | o que é |
|---|---|---|
| índice de aceitabilidade por posição | b^r_i | fração dos vetores de peso sorteados em que a unidade i ficou na posição r |
| vetor central de pesos | w^c_i | média dos vetores de peso que puseram a unidade i em primeiro lugar, normalizada para somar 1 |
| fator de confiança | p^c_i | 1 se a unidade fica mesmo em primeiro quando a combinação é refeita com o vetor central dela, 0 se não fica |

`b^1_i` é a aceitabilidade de primeiro lugar. Como cada sorteio tem no máximo um vencedor, a soma de
`b^1` sobre todas as unidades é 1 sempre que existir, em todo sorteio, ao menos uma unidade com nota e
não vetada. A saída expõe esse total em `soma_aceitabilidade_primeiro` e conta em
`sorteios_sem_vencedor` os sorteios em que ninguém era classificável.

## O que a saída entrega

- `tabela_topo`: a tabela de aceitabilidade das 20 unidades com maior `b^1` (parâmetro `topo`), cada
  linha com a aceitabilidade nas 20 primeiras posições do ranking (parâmetro `posicoes`), o vetor
  central e o fator de confiança daquela unidade.
- `explicacao_da_unidade(i)`: a frase em português que a tela e o PDF mostram, com o **vetor central
  exibido fator a fator** ("o peso médio que a levou ao primeiro lugar é: acesso 75,0 %, declividade
  25,0 %") e o resultado de aplicar esse peso de volta.
- `semente`, `metodo`, `pesos_base_normalizados`, `combinador` e `observacoes`: o suficiente para
  reproduzir a rodada bit a bit.

Só agregados por unidade são guardados, nunca a matriz N × unidades (decisão A9 do conceito da linha).

## Caso de resposta conhecida

Três unidades, dois fatores, peso sorteado uniformemente no simplex (Dirichlet com alfa 1, que em duas
dimensões é `w1 ~ U(0, 1)`):

    A = (100, 0)    nota 100·w1
    B = (0, 100)    nota 100·(1 − w1)
    C = (49, 49)    nota 49, constante

A conta fecha sem rodar nada: A ganha quando `w1 > 0,5` e B por simetria, logo `b^1 = 0,5` para cada
uma; C nunca ganha, porque precisaria de `w1 < 0,49` e `w1 > 0,51` ao mesmo tempo; C fica em segundo
sempre que `|w1 − 0,5| > 0,01`, ou seja em 98 % dos sorteios; o vetor central de A é a média de `w` no
conjunto `{w1 > 0,5}`, que é `(0,75; 0,25)`. É esse o caso de `tests/unit/test_amc_smaa.py`, e é assim
que se confere a implementação contra a teoria e não contra ela mesma.

## Limites (leia antes de usar o número em documento)

1. **Só o peso é sorteado.** O SMAA-2 do artigo trata incerteza nos critérios e nos pesos; aqui o fator
   já extraído entra como determinístico. Toda leitura vale "sob incerteza de peso", nunca "sob
   incerteza do dado".
2. **Com combinador linear o fator de confiança é 1 por construção.** Com fator determinístico e soma
   ponderada, a região de pesos que faz uma unidade ganhar é convexa, então a média dos pesos
   vencedores cai dentro dela. O fator só separa unidades com combinador não linear (por exemplo
   `media_geometrica`). Ele é medido de verdade, recombinando — nunca assumido.
3. **Combinador que ignora peso torna o sorteio inócuo.** Mínimo, máximo, produto, soma fuzzy e gama
   não usam peso por definição: o ranking é o mesmo em todos os sorteios e a aceitabilidade só pode dar
   0 ou 1. A saída avisa em `observacoes`.
4. **Empate é desempatado pela ordem da unidade na matriz**, de forma determinística. Com peso contínuo
   o empate tem probabilidade zero, mas com fator inteiro e poucos fatores ele acontece, e aí a
   aceitabilidade depende da ordem de entrada. A saída conta os empates em `empates_no_primeiro`.
5. **A aceitabilidade é contada só até a posição declarada** (20 por padrão). Linha inteira em zero não
   quer dizer último lugar; quer dizer fora dessas posições.
6. **Veto não é sorteado.** A unidade vetada sai da classificação em todos os sorteios por construção,
   e por isso tem aceitabilidade zero em toda posição e nenhum vetor central — nunca porque a nota
   ficou baixa.
7. **A aceitabilidade descreve o espaço de pesos; não recomenda peso nenhum.** O peso continua sendo
   escolhido pelo usuário, e a saída carrega essa frase em `aviso_pesos`.
8. O resultado é uma estimativa por amostragem: com 1.000 sorteios o erro típico de uma fração perto de
   0,5 é da ordem de 0,016. Comparar duas unidades com aceitabilidades muito próximas exige mais
   sorteios, e a semente fica gravada para a rodada ser repetível.

## Medidas

`tests/medidas/L3-02-c-smaa.json`, gerado por
`PLAT_GRAVAR_MEDIDAS=1 bash laco/roda_teste.sh tests/unit/test_amc_smaa.py -q`.
