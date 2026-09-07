# ADR 20260907T1617 — Restrição como objeto próprio do motor multicritério

## Contexto

O motor AMC (`app/amc/`) já distinguia FATOR (pesado, escolhido pelo usuário) de RESTRIÇÃO (veto, objeto
separado do peso — decisão A6 de `laco/decomposicao/L3L6_CONCEITO.md`) desde o esquema do modelo
(`docs/esquemas/amc_modelo.v1.json`, `$defs.restricao`) e desde `app.amc.combinacao.combinar` (que já
recebe `fracao_vetada`/`motivo_veto`) e `app.amc.robustez.simular_robustez` (que já trata essa fração
como fixa em todo sorteio Monte Carlo). O que faltava — o item L3-04-restricoes — era o módulo que
PRODUZ essa fração e esse motivo a partir da definição declarada da restrição: a avaliação em si.

`app.amc.explicacao` já documentava a lacuna na própria docstring: "os campos de veto, que este item lê
e não recalcula (a avaliação de restrição é outro item)".

## Decisão

1. **Módulo novo `app/amc/restricao.py`**, no mesmo estilo dos demais extratores (`vetorial.py`,
   `zonal.py`): função pública `avaliar(cur, unidades, feicoes, restricao)` que devolve
   `{unidade_id: {"vetada": bool, "fracao_intersectada": float|None}}` para UMA restrição, e
   `compor(unidades_ids, avaliacoes)` que junta várias por OU.

2. **Buffer é sempre geográfico.** `regra.tipo == "intersecta"` com `buffer_m > 0` usa
   `ST_DWithin(geometria::geography, geometria::geography, buffer_m)`; sem buffer (ou buffer 0), usa
   `ST_Intersects` puro sobre a geometria em graus — não há reprojeção nem escolha de zona UTM para esta
   regra, porque a distância geodésica correta já sai de `geography` sem custo de decisão adicional.
   `regra.tipo == "fracao_area_minima"` usa `ST_Area(geometria::geography)` para a fração — o mesmo
   padrão que `app.amc.crs` já documenta para a área das unidades ("área das unidades sempre geodésica").
   Nenhuma das duas regras depende do `srid_trabalho` do conjunto de unidades: diferente de
   `app.amc.vetorial` (que projeta para UTM antes de medir), a restrição não precisa de área/comprimento
   em metros planos — só de comparação binária (toca/não toca, fração ≥ limiar), e a `geography` do
   PostGIS já resolve isso sem escolha de projeção.

3. **Composição por OU é sempre binária.** A fração vetada final de uma unidade é 0,0 (nenhuma restrição
   vetou) ou 1,0 (ao menos uma vetou) — nunca um valor intermediário. Restrição veta, não pesa; não
   existe "meio veto" que deixasse passar metade da nota. O motivo gravado é o da PRIMEIRA restrição, na
   ordem declarada no modelo, que vetou aquela unidade — nunca empilha motivos de restrições diferentes
   na mesma unidade (decisão de produto: um motivo por unidade é o que o relatório mostra; a contagem
   por restrição, separada, é que diz quantas restrições bateram no total).

4. **Frase do relatório vem só do metadado `base`.** `frase_motivo` nunca infere: `base == "norma"` gera
   "a norma veda: ..." (com `base_legal` entre parênteses quando declarada); `base == "precaucao"` gera
   "vetamos por precaução: ...". Isto é regra de linguagem dura da casa: nunca dizer que a lei proíbe
   quando o veto é escolha de precaução da equipe.

5. **Camada vazia nunca veta em silêncio.** `avaliar` levanta `ErroRestricao('camada_vazia', ...)` antes
   de qualquer consulta — zero unidades vetadas por falta de feição na área é indistinguível, para quem
   lê o resultado, de zero unidades vetadas porque nenhuma realmente se sobrepõe. A refutação do item
   (adversário: buffer 0, buffer negativo, camada vazia) cobra exatamente essa distinção.

6. **Escopo declarado, não fingido.** Só três dos quatro tipos de `regra` do esquema são avaliados aqui:
   `intersecta`, `fracao_area_minima`, `atributo_igual`. `valor_raster` levanta `ErroRestricao
   ('regra_nao_suportada', ...)` com mensagem explícita — a mesma prática de `app.amc.executor._transformar`
   (que só suporta a transformação `linear` e diz isso em vez de fingir suportar as outras).

## Consequências

- `app.amc.robustez` e `app.amc.combinacao` não mudaram nenhuma linha: já sabiam consumir `fracao_vetada`
  fixa. Isso confirma que a decisão A6 original (restrição como objeto separado do peso) já tinha a forma
  certa antes de existir quem a preenchesse.
- Quem for integrar isto ao executor completo (`app.amc.executor`, hoje limitado a fatores do acervo com
  transformação linear) precisa ler a camada da restrição do mesmo jeito que já lê a camada de um fator
  (`_ler_camada_acervo`) e chamar `restricao.avaliar` uma vez por restrição declarada no modelo, na ordem
  do documento, antes de chamar `combinacao.combinar` — não foi feito aqui porque o portão deste item
  pede a avaliação em si, testada isoladamente contra recomputação independente, não a integração no job
  de execução (que arrasta o mesmo limite honesto já documentado no executor: só fatores do acervo, só
  extratores de vetor 1:1, só transformação linear).
- `valor_raster` fica como dívida declarada, não escondida: um item futuro que precisar dele vai
  encontrar o erro explícito, não um resultado fabricado.
