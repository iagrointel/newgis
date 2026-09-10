# Paridade de regras de atributo com o ArcGIS Pro / Utility Network (item L4-29-regras-de-atributo-de-rede)

Documento de paridade do motor de regras de atributo de rede (`app/rede/regras.py`, migração
`20260908T1934_regras_atributo_rede.sql`, ADR `20260908T1945-regras-atributo-de-rede.md`). Compara os três
perfis do motor (`calculo`, `restricao`, `validacao`) com os três perfis de attribute rule do ArcGIS Pro
(calculation, constraint, validation) e as variáveis globais do Arcade usadas por eles.

Fontes (consultadas em 08/09/2026; a página antiga
`pro.arcgis.com/en/pro-app/latest/help/data/geodatabases/overview/attribute-rules.htm` está FORA DO AR nesta
data — redireciona para 404 —, então os fatos vêm das páginas vivas listadas):

- Constraint attribute rules — `doc.esri.com/en/arcgis-pro/latest/help/data/geodatabases/overview/constraint-attribute-rules.html`
- Validation attribute rules — `pro.arcgis.com/en/pro-app/3.5/help/data/geodatabases/overview/validation-attribute-rules.htm`
- Evaluate attribute rules (ordem de avaliação) — `pro.arcgis.com/en/pro-app/3.5/help/data/geodatabases/overview/evaluate-attribute-rules.htm`
- Attribute Rule properties (arcpy) — `doc.esri.com/en/arcgis-pro/latest/arcpy/functions/attribute-rule-properties.html`

Regra do documento: paridade ≠ identidade. Onde o motor diverge de propósito, a divergência está marcada
**[diverge — decidido]** com o motivo; onde falta por escopo do item, marca **[falta]** com quem cobre. Nada
aqui afirma comportamento do produto Esri além do que as quatro páginas acima dizem.

## 1. Os três perfis

| perfil Esri | o que a documentação Esri diz | perfil nosso | o que o motor faz | estado |
|---|---|---|---|---|
| calculation | escreve/altera atributo do feição. Duas formas: **immediate** (avalia na edição) e **batch** (avalia com a ferramenta Evaluate Rules) | `calculo` | cada regra ativa avalia UMA vez por objeto do `alvo_tipo` e grava `atributo_alvo` via `jsonb_set` quando o valor não é nulo (`aplicar_calculo`) | feito (só batch — ver §2) |
| constraint | a expressão devolve **verdadeiro = satisfeito** (a edição segue) e **falso = violação** (devolve error number + message definidos na criação e a edição é desfeita); avalia na edição, por evento `insert`/`update`/`delete`, com campos gatilho opcionais | `restricao` | `checar_restricao` responde "posso fechar esta chave?": expressão **verdadeira = RECUSA** (direção invertida de propósito, §3), **nulo não recusa** (três valores, como o SQL) e **erro de avaliação RECUSA com o código nomeado** (falha fechada) | feito (sem evento de edição — §5) |
| validation | avalia sob demanda, "at a user-specified time", com a ferramenta Evaluate Rules; violação cria **error features em error layers**, revisados no Error Inspector; indicada para dado já existente | `validacao` | `rodar_validacao` avalia em lote sob chamada explícita; item por (regra, objeto) com expressão verdadeira, com a `mensagem` da regra; erro de avaliação vira item com o código nomeado e a rodada CONTINUA; acima do teto sai `truncado: true` | feito (lista em memória, sem error layer persistente — §4) |

Ordem de avaliação: a documentação Esri diz que na edição as calculation **immediate** vêm antes das
constraint, e que batch calculation e validation vão para a ferramenta Evaluate Rules. No motor não existe
avaliação na edição: `aplicar_calculo`, `checar_restricao` e `rodar_validacao` são ações explícitas de quem
opera (ou de quem chama), nessa ordem quando a ordem importa. **[diverge — decidido]**: avaliação na edição
exige ganchos em toda escrita de `rede_objeto`; o item L4-29 entrega o motor de regras, não os ganchos.

Dentro de uma rodada a ordem é `prioridade DESC, nome` — o equivalente nosso do campo *evaluation order*
das regras Esri, mais um critério de desempate determinístico.

## 2. Calculation: immediate × batch e o ponto fixo

A documentação Esri separa calculation em **immediate** (na edição) e **batch** (ferramenta Evaluate Rules).
O motor só tem a forma batch (uma rodada explícita). E a semântica da rodada é declarada e testada:
**uma rodada avalia cada regra UMA vez por objeto — não existe ponto fixo** (ADR §3, o motivo é a refutação
do item: o adversário escreve "jusante de jusante" e o motor não entra em laço). A regra
`AtributoRede('x') + 1` avança exatamente 1 por rodada
(`tests/api/rede/test_regras_atributo.py::test_laco_autorreferente_avanca_uma_vez_por_rodada`); rodar de
novo é uma ação nova e explícita, igual à segunda passada da ferramenta Evaluate Rules.

Nulo não grava: se a expressão devolve nulo (ausência é dado — `TensaoAlimentador()` de trecho sem
alimentador), `aplicar_calculo` NÃO sobrescreve o atributo existente. A documentação Esri das calculation
que esta página cobre não afirma o comportamento para nulo; aqui o comportamento é este e está testado.
**[diverge — decidido]**: a forma Esri aceita devolver dicionário para escrever vários campos numa regra;
aqui uma regra escreve UM `atributo_alvo` (o CHECK da migração obriga `atributo_alvo` não nulo se e só se
`perfil = 'calculo'`).

## 3. Constraint: a direção do booleano e o erro nomeado

**A direção é invertida de propósito.** Esri constraint: verdadeiro = a edição passa, falso = violação com
rollback. Motor `restricao`: a expressão afirma o IMPEDIMENTO — verdadeiro = recusa ("chave não fecha
entre 13,8 kV e 34,5 kV" é literalmente a expressão
`TensaoAlimentador() >= 13.8 && TensaoAlimentador() <= 34.5`, testada em
`test_restricao_recusa_chave_na_faixa`). Motivo: com a lógica de três valores do avaliador (nulo não é
verdadeiro nem falso), "expressão verdadeira = recusa" deixa o nulo do lado SEGURO por construção — a regra
do lado da Esri exigiria negar a expressão e lembrar que `!(nulo)` ainda é nulo.

| | Esri constraint | motor `restricao` |
|---|---|---|
| violação | falso na expressão | verdadeiro na expressão |
| mensagem | error number + error message definidos na criação da regra | campo `mensagem` da regra, na recusa (`recusas[i].mensagem`) |
| erro de script | a documentação consultada não afirma | recusa com `recusas[i].erro` = código nomeado (`limite_passos`, `tipo_invalido`, …) — **falha fechada**: regra que não consegue avaliar nunca autoriza (`test_regra_que_erra_recusa_com_erro_nomeado`) |
| rollback | a edição é desfeita | o chamador pergunta ANTES de fechar; sem resposta `permitido: true` não há fechamento |
| evento de edição | `insert`/`update`/`delete` + campos gatilho | **[falta]** sem gancho de edição (§1) — o chamador decide quando perguntar |

## 4. Validation: lote sob demanda, erro nomeado e teto declarado

Mesma direção que a Esri (a página arcpy diz que validation devolve verdadeiro na violação): expressão
verdadeira vira item da lista. Divergências declaradas:

| | Esri validation | motor `validacao` |
|---|---|---|
| quando | Evaluate Rules, "user-specified time" | `rodar_validacao`, chamada explícita — igual |
| onde o erro fica | error features em error layers persistentes, revisadas no Error Inspector | lista em memória na resposta (`itens`), com `regra`, `objeto`, `mensagem` ou `erro` nomeado; **[falta]** error layer persistente (item de linha L4 ainda não reivindicado) |
| dado já existente | a página de constraint recomenda validation para inconsistências em dado existente | `rodar_validacao` corre sobre tudo que já está em `plat.rede_objeto` — igual em espírito |
| erros de script | não afirmado na página consultada | item com o código nomeado; a rodada NÃO trava (validação lista, não impede) |
| volume | não afirmado na página consultada | teto `REDE_REGRAS_ITENS_MAX` (10.000); acima disso `truncado: true` — o teto é declarado, não escondido |

## 5. Variáveis globais do Arcade

| Arcade | disponível nos perfis Esri (segundo as páginas consultadas e o sumário delas) | equivalente nosso | estado |
|---|---|---|---|
| `$feature` | a feição avaliada (atributos e geometria) | os atributos do objeto ACHATADOS no topo do contexto (`montar_contexto`) — `$tensao_kv` funciona; funções de rede leem a chave reservada `rede` | feito |
| `$originalFeature` | estado pré-edição (calculation e validation) | **[falta]** não há foto pré-edição no contexto; linhagem/histórico é o item L4-parcelas-01 (registro × parcela), não este | falta (L4-parcelas-01) |
| `$datastore` + `FeatureSetByName()` | acesso a outras classes/tabelas do mesmo armazém (calculation e validation; a página de constraint não o lista) | **[diverge — decidido]** não existe acesso a outra tabela pela linguagem. O avaliador é fechado por construção (sem rede, sem arquivo, sem SQL — `docs/EXPRESSAO.md` §6); o que vem de fora entra pelo contexto, e o motor coloca no contexto só o que é da rede: nível, subrede, alimentador, a tensão herdada do alimentador em um salto (`TensaoAlimentador()`) e a jusante já calculada (`ContarJusante()`). Vizinho arbitrário pela topologia (o "de jusante de jusante") NÃO é alcançável pela linguagem — é exatamente a refutação do item | feito (o recorte É a decisão) |
| `Expects()` / edição de geometria no script | perfis Esri (fora das páginas consultadas — não afirmado aqui) | não existe; a linguagem não edita nada, só calcula valor (o `calculo` grava pelo motor, não pela expressão) | fora do desenho |

## 6. Costura exposta: orçamento da expressão (a refutação do item)

Nem a página de constraint nem a de validation consultadas afirma orçamento de passos ou relógio por
expressão (o que existe na Esri para isso não estava acessível nesta data — nada é afirmado aqui sobre o
produto deles). No motor o orçamento é costura EXPOSTA e documentada:

- `limite_passos` e `limite_ms` são parâmetros nomeados de `aplicar_calculo`, `checar_restricao` e
  `rodar_validacao` (passar nada = sem teto além do `MAX_PROFUNDIDADE = 60` do parser e dos tetos de
  volume: `REDE_REGRA_MAX`, `REDE_REGRAS_OBJETOS_MAX`, `REDE_REGRAS_ITENS_MAX`, `REDE_REGRAS_ERROS_MAX` em
  `app/limites.py` / `docs/LIMITES.md`);
- estourar orçamento NÃO derruba a rodada: vira erro NOMEADO (`limite_passos`, `tempo_excedido`) contado em
  `erros_total` (cálculo) ou item com `erro` (validação) ou recusa com `erro` (restrição — falha fechada);
- testado por `test_laco_corta_no_orcamento_de_passos_com_erro_nomeado`
  (`aplicar_calculo(cur, limite_passos=2)` numa regra autorreferente: `erros_total == 1`, código
  `limite_passos`, `escritos == 0`) e por `test_regra_profunda_recusa_na_criacao` (70 `Se` aninhados são
  recusados NA CRIAÇÃO com `profundidade_excedida`, antes de chegar ao banco).

## 7. Resumo de estado

- feito: três perfis; direção do booleano documentada (constraint invertida de propósito, validation igual);
  erro nomeado nas três saídas; lote sob demanda; teto declarado; ordem por prioridade; nulo não grava e não
  recusa; contexto de rede com um salto de alimentador e jusante pré-calculada.
- falta (cada um com cobertor): ganchos de edição (insert/update/delete + campos gatilho); error layer
  persistente com Error Inspector; `$originalFeature` (foto pré-edição — chega com o versionamento do item
  L4-parcelas-01); regra que escreve vários campos numa passada.
- diverge de propósito: sem `$datastore`/acesso a outra tabela pela linguagem (contexto fechado); sem ponto
  fixo no cálculo (rodada única); recusa no lado verdadeiro da expressão.
