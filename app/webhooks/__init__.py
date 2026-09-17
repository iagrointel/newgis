"""Webhooks de eventos por inquilino (item L7-08-a-webhooks-eventos; ADR em docs/adr/).

Assinatura Standard Webhooks (https://github.com/standard-webhooks/standard-webhooks — a biblioteca de
referência `standardwebhooks` assina do nosso lado e verifica do lado do receptor; o portão do item exige
que a VERIFICAÇÃO seja dela). O fato que dispara é `plat.evento` (gravado na mesma transação da mudança
por `plat.evento_registrar`): um gatilho AFTER INSERT no pai particionado (migração 20260909T0345) cria
uma `plat.webhook_entrega` + um job `webhooks.entregar` para o worker de jobs que já existe (L0-05) —
nenhum segundo executador, nenhum segundo relógio. As rotas (CRUD, rotação de segredo, log de entregas,
reenvio) ficam em `rotas.py` sob o privilégio `org.integracoes` (semeado na 003 com esta finalidade na
descrição); `tarefas.py` é o job `somente_sistema` + o periódico de expurgo do log."""
