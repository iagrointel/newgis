# Regras de atributo por camada (item L2-10-d-regras-de-atributo)

Data: 08/09/2026. Estado: aceito. Par: `laco/decomposicao/L2_CONCEITO.md` C5 (uma porta de escrita; regra de
expressão na API) e C6 (linguagem de expressão própria); ADR do L2-03-a (edição transacional) e `docs/EXPRESSAO.md`.

## Contexto

O Esri chama de "attribute rules" (Pro/hosted 11.4) três coisas: cálculo imediato ao editar, restrição que recusa a
edição, e validação avaliada sob demanda ("Evaluate Rules") que produz uma camada de erros. A casa já tinha a
linguagem de expressão (L2-10-c, avaliador Python e JavaScript com vetores compartilhados) e a porta única de
escrita (L2-03-a). Faltava ligar as duas e decidir onde a regra vive e quando roda.

## Decisão

1. **A regra vive no item da camada** (`dados.regras`, `dados.campos_virtuais`, esquema v4 de `camada_vetorial`,
   migração 20260908T0715), não numa tabela nova: viaja com o item (versões, exportação, pacote), e a validação de
   forma é o JSON Schema do tipo, como todo `dados`. A validação de FUNDO (expressão, campos, ciclo) é do motor
   (`app/regras/motor.py`) e roda em `PUT /api/camadas/{id}/regras` e em qualquer `POST/PUT/PATCH /api/itens` que
   mude `dados` de uma camada — um ciclo nunca chega ao banco.
2. **Cálculo e restrição rodam no caminho único de escrita** (`app.edicao.servico._inserir/_atualizar`), depois da
   validação de tipo/domínio e antes do SQL: valem para navegador, FeatureServer, OGC, PWA e lote porque todos
   chamam `aplicar_edicoes`. Não há gatilho no banco para regra de expressão (C5: a linguagem roda em Python; sem
   plpython3u; não se executa código de usuário no banco).
3. **Gatilho por campo** (`gatilhos`): em atualização a regra só roda quando um dos campos citados veio no pedido
   ou foi calculado por outra regra no mesmo pedido (encadeamento) — `geom` conta como campo; em inserção toda
   regra do evento roda. `ordem` é respeitada literalmente (o resultado muda se a ordem mudar; testado).
4. **Ciclo é erro de configuração**, com o caminho: regra que calcula um campo que está nos próprios gatilhos, ou
   cadeia A -> B -> A por gatilho ou por uso na expressão. Campo virtual não referencia campo virtual.
5. **Validação é job** (`camadas.validar`): cursor no servidor em lotes de 5.000, erros em `e_<hex16>` ao lado da
   camada (RLS por inquilino por `plat.tabela_erros_preparar`, mesmo desenho de `plat.camada_preparar`), com a
   geometria copiada, e um item `camada_vetorial` só-leitura apontando para essa tabela — aparece no catálogo e
   no mapa como qualquer camada. Cada execução substitui a anterior; teto de 1 mi de erros por execução.
6. **Campos virtuais** são avaliados na leitura (`GET /api/camadas/{id}/feicoes`) e entram no contexto das regras;
   nunca são gravados nem aceitos como atributo. A compilação para SQL (coluna gerada, L2-10-e) fica fora: não há
   tradutor para SQL em master e a regra de expressão em Python cobre o portão.
7. **Exclusão por cliente**: `em_massa: true` no corpo de edição pula as regras marcadas `excluir_em_massa`
   (importação em massa), sem desligar as demais.

## Consequências

- Custo por edição = compilar uma vez por conteúdo (cache por hash) + avaliar as regras que dispararam; a
  cláusula "1.000 edições com 3 regras <= 2x sem regras" é medida em `tests/medidas/L2-10-d-regras-de-atributo.json`.
- 100 mil feições validadas como job com N erros conferidos por SQL; 1 mi é extrapolação linear declarada (a
  varredura é por cursor, sem carregar a tabela em memória), não medição.
- WFS-T não existe em master: a refutação "edita pelo WFS Transaction" fica pendente e, quando entrar, herda as
  regras por construção (chama `aplicar_edicoes`).
- Sem tela nesta fatia (a configuração é pela API; a tela de regras é item de L5/L6 com o editor de camada).
