# Contribuir de fora (modelo híbrido)

Trabalho feito em outra máquina ou por outra ferramenta entra por git e passa pelos MESMOS portões que o trabalho
feito no servidor. O servidor puxa o remoto, enfileira o ramo na fila de junção, roda a suíte inteira por lote, e
o ramo só chega a `master` se passar e se um adversário independente não o derrubar.

## O contrato de um ramo externo
1. Nome do ramo: `wt/<id-do-item>` (ex.: `wt/L2-03-a-api-edicao-transacional`), um item por ramo, criado de `master`.
2. Um agente ou pessoa por ramo. Commit por arquivo nomeado. Rodapé `Item: <id>` em todo commit.
3. O item vem de `laco/estado.json`: leia `hipotese`, `portao_de_pronto` e `refutacao`. O portão é literal: cada
   cláusula vira teste ou medida gravada em `tests/medidas/<item>.json`. Cláusula não provada fica escrita como
   fronteira, nunca como entregue.
4. Migração nova: `db/migracoes/YYYYMMDDTHHMM_<nome>.sql`, idempotente, com RLS por inquilino em toda tabela que
   tenha `tenant_id`, e `REVOKE ... FROM PUBLIC` antes de qualquer `GRANT EXECUTE`. Nunca renomear migração existente.
5. Sem placeholder (`TODO`, mock, rota com dado fixo), sem nome de cliente ou parceiro, sem segredo, sem `venv`.
6. Recurso partilhado (fila, trinco, schema de dados, contador, porta, tarefa agendada, permissão) SEMPRE com dimensão
   de inquilino ou de ambiente. Foi o padrão de quase tudo que caiu em 06/09/2026.
7. Repasse em `laco/handoffs/T<turno>/<item>.md`: o que foi construído, cláusula → prova (comando e saída), o que ficou
   de fora e por quê, comandos para o adversário reproduzir.

## O que o servidor faz com o ramo
`laco/puxa_github.sh` busca o remoto, cria o worktree local para cada `wt/*` novo e o põe na fila
(`laco/fila_merge.sh entrar`). A fila junta em lote com a suíte inteira; se o lote quebra, a bisseção devolve só o
ramo culpado com o registro do erro. Depois de entrar em `master`, um adversário ataca o item; achado vira teste
`xfail(strict=True)` e o item volta para conserto. `STATUS.md` e o painel refletem o resultado.
