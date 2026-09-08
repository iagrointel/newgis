# ADR 20260907T1013 — combinador do motor multicritério (item L3-01-e-combinacao)

Contexto: o ADR 0001 (Parte A do `L3L6_CONCEITO.md`, decisões A3/A5/A6/A9) já fixou a forma da
combinação — escala 0-100 real com `NULL` para ausente, padrão `Σ w·f / Σ w` sobre os fatores COM
dado, veto como objeto separado do peso, pesos escolhidos pelo usuário, nunca medidos. Este item
implementa isso em código, dos dois lados que o produto precisa: servidor (Python/numpy, para
extração em lote e para o adversário) e navegador (JavaScript puro, para a interatividade de mover
peso descrita em A2 — recombinação em milissegundos, sem viagem ao servidor).

## Decisão

`app/amc/combinacao.py` expõe uma função pura `combinar(fatores, pesos, ...)` — não abre banco, não
lê arquivo, não usa relógio — que devolve um `Resultado` com `fav` (favorabilidade, `nan` onde não há
nota), `vetado`, `cobertura`, `motivo`, e a frase fixa `aviso_pesos = "pesos escolhidos pelo usuário,
não medidos"`. `web/js/amc/combinacao.js` é a segunda implementação, escrita à mão a partir da mesma
definição (não é transpilada, não importa o Python) — a equivalência entre as duas é o que os testes
provam, não uma garantia de projeto.

Oito combinadores declarados (`COMBINADORES`): `soma_ponderada` (padrão, o mesmo que o motor
logístico faz em SQL), `percentual` (paridade com o Weighted Overlay da Esri, pesos que fecham 100,
arredondado ao inteiro — perde precisão, por isso nunca é o padrão), `media_geometrica` (anula a nota
quando um fator é zero, o comportamento do "ranking original" do motor logístico), e os quatro fuzzy
do Fuzzy Overlay (`minimo`, `maximo`, `produto`, `soma_fuzzy`, `gama`) — estes cinco últimos ignoram o
peso por definição matemática e o resultado registra essa observação para nunca parecer que um peso
digitado pelo usuário foi silenciosamente descartado.

Três políticas de dado ausente (`POLITICAS_AUSENTE`): `excluir` (padrão — o fator sai da conta e a
cobertura cai), `nulo` (a unidade inteira fica sem nota se faltar qualquer fator) e `pessimista` (o
ausente vira nota 0, declarada como estimativa, nunca como medição). Veto é fração `[0,1]` que
multiplica a nota por `(1 − fração)`; fração 1 zera e grava o motivo; unidade sem nenhum dado
continua sem nota mesmo vetada — o veto marca, não inventa número.

## Por que os dois lados são escritos à mão, e não gerados um do outro

Custo de mudar depois: baixo por arquivo, alto de confiança — se o JavaScript fosse transpilado do
Python (ou vice-versa), um teste que os compara provaria apenas que o transpilador funciona, não que
a definição matemática está certa nos dois lugares onde o produto realmente calcula. A cláusula do
item exige que a verificação seja "independente": `tests/unit/test_amc_combinacao_equivalencia.py`
escreve uma TERCEIRA implementação (não importa `combinar`, recomputa da definição) e compara as
três aos pares. Preço: qualquer correção de fórmula tem de ser feita em três lugares e as três
suítes rodadas de novo; aceito porque o produto nunca teria como provar a paridade de outro jeito.

## Desempenho medido (item exige ≤ 50 ms servidor / ≤ 20 ms navegador em 4.346 × 19)

`tests/unit/test_amc_combinacao_desempenho.py` mede antes de gravar: `os.getloadavg()[0]` e
`MemAvailable` de `/proc/meminfo`; acima de carga 8 (12 núcleos) o teste pula e marca a cláusula como
NÃO MEDIDA em vez de gravar um número sob disputa. Medido em 07/09/2026 com carga de 1 min 5,97 e
10,45 GB de RAM livre: mediana de 30 chamadas sobre 4.346 unidades × 19 fatores — **1,49 ms no
servidor** (numpy) e **1,63 ms no navegador** (node, `performance.now()`, o mesmo relógio do
browser) — ambos com folga de mais de 10× sobre o limite. Números em
`tests/medidas/L3-01-e-combinacao.json`, com a carga e a RAM ao lado de cada um: número de
desempenho sem isso ao lado não vale como prova (regra do item).

## O que fica de fora deste item

Explicação por unidade (fator → transformação → contribuição, item L3-01-f), tela e presets
(L3-01-g/h), exportação do método (L3-01-i) e a paridade formal com o motor logístico existente
(L3-01-j) dependem deste combinador mas não são construídos aqui — o `Resultado.como_dicionario()`
já expõe tudo que essas telas precisam (pesos normalizados, observações, motivo por unidade) para
não obrigar a remexer neste módulo quando chegarem.
