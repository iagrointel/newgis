# ADR 20260907T2200 — duas tabelas de subrede: `rede_subrede` (controlador) e `rede_subrede_bdgd` (importação)

## Contexto

Dois itens da linha L4 criaram, em ramos separados, uma tabela `plat.rede_subrede` com o mesmo nome e
conteúdo diferente:

- `L4-04-a-controladores-e-tiers` (migração `20260907T2031`): subrede no sentido do *subnetwork controller*
  da Esri — `tier_id`, `nome`, `estado` (`limpa`/`suja`), `resumo`. É o nome que o portão de pronto do item
  no `estado.json` cita textualmente.
- `L4-01-c-importador-bdgd` (migração `20260906T2126`): hierarquia de agrupamento LIDA DO ARQUIVO BDGD —
  `nivel` 1 a 4 (subestação → alimentador → transformador), `codigo_externo` (COD_ID da SUB/CTMT/UNTRMT),
  `pai_id` com gatilho de nível estrito.

Na junção dos dois ramos a segunda migração parou com `column "tier_id" does not exist`: `CREATE TABLE IF
NOT EXISTS` encontrou a tabela do outro item já criada.

## Decisão

A tabela do controlador fica com o nome `plat.rede_subrede` (é o nome do portão do item e o termo de
paridade com a Esri). A tabela da importação BDGD passa a se chamar `plat.rede_subrede_bdgd`, com os
índices, chaves estrangeiras, gatilho e função renomeados na mesma migração. As colunas `subrede_id` de
`plat.rede_no` e `plat.rede_aresta` continuam com o nome que tinham e apontam para `rede_subrede_bdgd`.

## Consequência e fronteira honesta

As duas tabelas descrevem o MESMO conceito de negócio por dois caminhos (o que o arquivo declara e o que o
traçado calcula) e hoje não conversam: nada liga uma linha de `rede_subrede_bdgd` ao controlador
correspondente em `rede_subrede`. Unificá-las é decisão de desenho de quem coordena a linha L4, não desta
junção; até lá, o nome com sufixo é o que impede que uma sobrescreva a outra.
