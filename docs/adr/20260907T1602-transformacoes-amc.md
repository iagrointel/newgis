# ADR 20260907T1602 — Biblioteca de transformações do motor multicritério (valor bruto → favorabilidade)

Data: 07 de setembro de 2026. Item L3-01-d-transformacoes. Decisão de conceito já fixada em
`laco/decomposicao/L3L6_CONCEITO.md` (A4): a transformação é um documento JSON, tipo + parâmetros,
16 tipos. Esta ADR registra o que a implementação decidiu para fechar o portão de pronto.

## Contexto

O esquema (`docs/esquemas/amc_modelo.v1.json#/$defs/transformacao`) já listava os 16 tipos desde o
item L3-01-a — `categoria`, `faixas`, `linear`, `degraus` e as 12 funções contínuas do Rescale by
Function do ArcGIS Pro. O executor (`app/amc/executor.py`, item L6-04) implementava só `linear`,
com um comentário explícito dizendo que o resto ficava para este item. Faltava: (1) uma segunda
implementação em SQL, para materializar sem trazer a coluna inteira para o Python; (2) prova de que
as duas batem; (3) prova de que a curva reproduz o motor logístico real (CBRE) onde ele já faz a
mesma conta; (4) documentação com fórmula e gráfico.

## Decisão 1 — a fórmula das funções contínuas é DECLARADA, não engenharia reversa

A Esri documenta, para o Rescale by Function (Pro 3.4), o PROPÓSITO de cada função e o NOME dos
parâmetros (Midpoint/Spread, Mean multiplier/Std multiplier, Shift/Exponent, etc — verificado em
`doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/the-transformation-functions-
available-for-rescale-by-function.html`, 07/09/2026), mas não publica a fórmula fechada — é
comportamento de produto fechado. Duas tentativas de busca (WebFetch na página de "How Rescale by
Function works" e na de Fuzzy Membership, que usa as mesmas curvas) confirmaram a ausência da
equação nas duas.

Diante disso, `app/amc/transformacoes.py` DECLARA uma fórmula concreta para cada nome — sigmoide
logística para `grande`/`pequena`/`ms_grande`/`ms_pequena`, gaussiana de expoente 2 para `gaussiana`
e de expoente 4 para `proxima` (mais estreita, como o texto da Esri pede), logística calibrada por
`y_intercepto_percentual` para `crescimento_logistico`/`decaimento_logistico`, etc — com os MESMOS
nomes de parâmetro e o MESMO efeito qualitativo que a Esri descreve (ex.: "quanto maior o spread,
mais estreita a curva"). Isto é consistente com a regra da casa citada no prompt do item:
**"transformação é escolha declarada do usuário, nunca calibrada por nós"**. A refutação exigida
(`tests/unit/test_amc_transformacoes_adversario.py`) não compara com a Esri (impossível sem o código
fechado dela) — compara duas leituras INDEPENDENTES da mesma especificação pública, que é a prova
possível aqui.

## Decisão 2 — extensão aditiva `saida_min`/`saida_max`

Vários fatores reais do motor logístico (ex.: `rod` do CBRE: "d ≤ 300 m → 100; rampa até 10 em
5 km") não têm saída em [0, 100] cheio — a rampa vai de 100 a 10, não de 100 a 0. O esquema não lista
esses campos, mas também não fecha `additionalProperties` no objeto `transformacao` — logo, gravar
`saida_min`/`saida_max` numa transformação não quebra nenhum modelo já existente (eles simplesmente
não apareciam) e nenhum validador precisa mudar. Sem eles, o comportamento é 0-100 como sempre foi.

## Decisão 3 — resolução de `metodo` (faixas) e de `media`/`desvio` (MSSmall/MSLarge) é CONGELADA antes do SQL

`faixas` com `metodo` diferente de `manual` (quantil, intervalo igual, quebras naturais) e
`ms_grande`/`ms_pequena` sem `media`/`desvio` gravados precisam de uma AMOSTRA para virar números —
uma função escalar do Postgres não vai agregar a coluna inteira a cada chamada. A solução (mesmo
padrão dos dois casos): `resolver_quebras`/`resolver_estatisticas`, em Python, calculam os números a
partir da amostra e devolvem a transformação com eles JÁ GRAVADOS (`metodo: manual`, `media`/
`desvio` presentes); é essa versão resolvida que `plat.amc_transformar_num` recebe e aplica. O
executor (`app/amc/executor.py`) resolve por fator, uma vez, antes de transformar todas as unidades
— outra execução, com outro conjunto de unidades, resolve de novo e pode dar quebras diferentes (é
esperado: quantil depende da amostra que se está olhando).

## Decisão 4 — `abaixo`/`acima` são sobre o VALOR BRUTO, nunca sobre a direção da curva

Erro pego no próprio desenvolvimento deste item: a primeira versão invertia `abaixo`/`acima` quando
`direcao = decrescente`, porque a fração já vinha invertida da curva. `abaixo` é sempre "valor menor
que `minimo`" e `acima` é sempre "valor maior que `maximo`", **independente de a curva estar subindo
ou descendo entre as duas pontas** — a direção decide só o formato da curva, não que ponta é qual.

## Decisão 5 — cobertura da reprodução do CBRE é 4 de 19 fatores, não 19 de 19, e o motivo é nomeado

Ver `tests/unit/test_amc_transformacoes_cbre.py`. Os "19 fatores" do motor logístico (ordem 1-19 em
`cbre.fatores`, README do projeto CBRE, "19 fatores" em 29/08/2026) incluem fatores que combinam
várias colunas, aplicam veto, somam bônus, ou (`gru`, `se`) têm uma coluna candidata que segue a
FORMA certa mas diverge > 0,5 numa fração relevante das células — sinal de que a coluna gravada não é
o valor que o pipeline do fator usou de fato. Reproduzir os outros 15 exigiria refazer a extração e a
combinação de cada um (fora do escopo de uma biblioteca de TRANSFORMAÇÃO de um valor já extraído).
Os 15 têm motivo nomeado no teste e em `tests/medidas/L3-01-d-transformacoes.json`; nenhum foi
escondido atrás de "reprovado" mudo, e a cláusula do portão é registrada como PARCIAL nomeada, não
fingida como passada.

## Consequências

- `app/amc/executor.py` agora delega toda transformação a `app.amc.transformacoes` (os 16 tipos),
  em vez de suportar só `linear` — a limitação documentada no módulo foi removida.
- Quem materializar favorabilidade em massa (fora do executor, ex. um job de recálculo de camada
  inteira) usa `plat.amc_transformar_num`/`plat.amc_transformar_cat` diretamente em SQL, sem trazer
  a coluna para o Python.
- Achar a coluna certa para `gru`/`se` no pipeline do CBRE fica pendente para quem tocar aquele
  projeto — não é um item de trabalho desta trilha (motor territorial genérico), é uma investigação
  específica do produto CBRE.
