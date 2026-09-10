# ADR: área suja e validação incremental (item L4-03-d-areas-sujas-e-validacao)

## Contexto

O item L4-03-a entregou a avaliação de regra em TEMPO de escrita (`sem_regra`/`terminal_errado`,
`POST .../applyEdits`) e uma validação em lote que rederiva a rede INTEIRA (`POST .../validar`). A
*utility network* da Esri não reavalia tudo a cada edição: toda feição tocada marca um polígono de
"dirty area" (`dirty-areas-in-a-utility-network.htm`) e `Validate Network Topology`
(`validate-network-topology.htm`) reconstrói só dentro dessas áreas, gravando o que sobra como
*error features* (`about-error-features.htm`, `manage-error-features.htm`) — uma camada, não um
log. Um traçado que começa numa área suja é avisado ou recusado
(`dirty-areas-in-a-trace-network.htm`). Este item traz essa mecânica para `plat.rede`.

## Decisão

1. **Área suja = polígono envolvente por FEIÇÃO editada**, não por lote (`app/rede_utilidades/
   areas_sujas.py`): um `applyEdits` com N feições tocadas grava até N linhas em
   `plat.rede_area_suja`, cada uma com a `versao` de edição do lote (`plat.rede.versao_edicao`,
   contador monotônico, uma unidade por `applyEdits` bem-sucedido — não por feição). Feição sem
   geometria não gera área (não há envelope possível). Feição APAGADA recebe a área calculada
   ANTES do `DELETE` (a geometria já não existe depois), com `feicao_id NULL`. `BUFFER_M = 2,0 m`:
   um ponto isolado também precisa virar polígono visível no mapa, e a Esri não declara a margem
   exata — 2 m é a mesma ordem de grandeza da tolerância de coincidência do item L4-03-a (0,5 m)
   com folga para o buffer não desaparecer no arredondamento de ponto flutuante.
2. **`limpa_em` é soft-delete**: a validação marca a data em vez de apagar a linha — "quantas vezes
   esta área foi suja" fica auditável. `apenas_ativas`/`limpa_em IS NULL` é o filtro de "visível no
   mapa" em toda leitura.
3. **Validação por extensão (`POST .../validar_extensao`) processa só o ESCOPO**: a união das áreas
   sujas ativas que tocam a extensão pedida (ou todas, se a extensão vier `null` — "validar tudo")
   vira o filtro `ST_Intersects` que restringe QUAIS feições entram nas 15 checagens
   (`app/rede_utilidades/validacao.py`). Nenhuma função de checagem varre a rede inteira por conta
   própria — é isso que faz "reconstrói só dentro da área suja" valer também para as checagens
   estruturais, não só para a derivação de conexão do item L4-03-a. `feicoes_em_escopo` e
   `feicoes_total` vão os dois na resposta: é a medida de "contagem de linhas reescritas ≪ total".
4. **15 códigos de erro, dois deles já existentes**: `sem_regra` e `terminal_errado` continuam
   lançados em tempo de escrita (L4-03-a); os outros treze (`regra_inexistente`,
   `terminal_invalido`, `terminal_obrigatorio_ausente`, `feicao_sem_conexao`,
   `sobreposicao_dispositivo`, `ciclo_tier_hierarquico`, `subrede_sem_controlador`,
   `atributo_obrigatorio_nulo`, `geometria_invalida`, `associacao_ciclo`,
   `feicao_duplicada_geometria`, `tipo_sem_regra_no_pacote`, `atributo_tipo_invalido`) só existem
   na validação — não fazem sentido bloquear um `applyEdits` isolado (ex. ciclo só aparece depois
   de duas edições separadas) e a Esri trata a mesma classe de coisas como *error feature*, não
   como recusa de edição.
5. **Erros gravados como FEIÇÃO em `plat.rede_erro`** (código, mensagem, `feicao_id`,
   `tipo_referencia`, `detalhe` jsonb, geometria, versão) — uma camada (`GET .../erros`,
   `FeatureCollection`), como a Esri pede. Revalidar uma extensão pequena SUBSTITUI só os erros das
   feições do escopo (nunca a rede inteira): `DELETE ... WHERE feicao_id = ANY(escopo)` antes de
   inserir os novos, mais os erros de âmbito de rede (`feicao_id NULL`) substituídos por código.
6. **Traçado sobre área suja é comporta de configuração**, não hardcode: `plat.rede.
   tracado_sobre_area_suja_modo` (`avisar`/`bloquear`, padrão `avisar`, trocável por
   `PUT .../area_sujas/modo`, só `rede.administrar` — mesmo padrão de `ativar_regras` do item
   L4-03-a). `POST .../tracar` recebe uma feição existente OU uma geometria solta (o traçado real,
   L2-11-c, ainda não existe neste produto) e devolve `{cruza_area_suja, bloqueado, area_suja}`;
   bloqueado é 409 com o polígono no corpo.

## Conserto encontrado ao construir: FK composta de `regra_id` (migração 20260907T1308)

Testar `regra_inexistente` (conexão com regra que já não existe) achou um bug real do item
L4-03-a: `plat.rede_conexao`/`plat.rede_associacao` tinham `FOREIGN KEY (tenant_id, regra_id)
REFERENCES plat.rede_regra (tenant_id, id) ON DELETE SET NULL` — uma FK de DUAS colunas, e o
Postgres zera TODAS as colunas do lado referenciador num `SET NULL` composto, inclusive
`tenant_id`, que é `NOT NULL`. Qualquer reimportação de CSV que removesse uma regra ainda em uso
por uma conexão quebrava a rota inteira com `NotNullViolation` (500). A migração
`20260907T1308_rede_conserta_fk_regra_set_null.sql` troca as duas FKs para uma coluna só
(`regra_id -> rede_regra.id`), seguro porque `regra_id` só é gravado a partir de uma regra já
carregada da MESMA rede (logo do mesmo tenant) — não abre brecha entre inquilinos.

## Fronteira honesta

Com a FK corrigida, `regra_inexistente` (código 3 da lista de `validacao.py`) fica **inalcançável
pela API**: o próprio banco garante que `regra_id` é sempre NULL ou uma regra que existe, nunca um
id órfão. A checagem continua no código como validação defensiva (útil se um dia a FK for
relaxada, ou contra dado gravado por fora da API) mas `tests/api/test_areas_sujas_e_validacao.py`
não afirma tê-la provocado — o teste que existia nesse nome virou a prova do CONSERTO acima
(reimportar CSV que remove regra em uso não quebra mais e a conexão sobrevive com `regra_id`
NULL). Os outros 14 códigos são alcançáveis e têm teste.

Este item não implementa um algoritmo de traçado sobre grafo (isso é escopo de L2-11-c/rede de
rota); `POST .../tracar` é o PONTO DE PARTIDA — a checagem que um traçado de verdade chamaria antes
de rodar o algoritmo pesado, com a mesma semântica de aviso/recusa que a Esri documenta para *trace
networks*. Paridade com *Verify Network Topology* (validação sem gravar erro, só relatório) e
*Repair Network Topology* (reparo automático de erro geométrico) NÃO está neste item — ficam como
pendência nomeada em `docs/PARIDADE.md`.
