# 50 — Refutação (adversário), item L0-05-jobs, turno T2, trilha B

**Objetivo.** Derrubar a fila de jobs pela refutação literal do item ("adversário mata o worker no
meio de um job e reinicia: job não pode aparecer como concluído") e pelos ataques 1–10 do encargo.
Contexto próprio: li SKILL.md (P1–P9), o item em `estado.json`, o ADR 0003 e o código; NÃO li os
handoffs 20/30/31/40. Padrão de partida: achar problema.

**Veredito: PASSA.** A refutação central foi reproduzida quatro vezes (restart, kill -9 no filho,
kill -9 no worker, restart duplo) e o job NUNCA apareceu como concluído sem a execução inteira: ele
volta a `pendente` de forma visível (nunca some), reexecuta do zero e só chega a `concluido` com o
marcador que a tarefa grava no último passo. Toda tentativa de forja por SQL como `plat_app` foi
recusada. RLS cruzado falhou em 15 rotas + SSE. Limites (memória, SIGTERM, timeout, cotas, enxurrada
de NOTIFY) e a unidade systemd conferem com o ADR. Registro três fraquezas que NÃO refutam o portão.

## O que fiz (comando + saída literal)

Serviço vivo `https://plat.iagrointel.com`; login por senha com as credenciais de `tests/credenciais.txt`
(600, não copiei); observador do estado por `sudo -u postgres psql` (superusuário, enxerga sem RLS).
Worker só pelo systemd; nenhum pytest concorrente; horários registrados abaixo.

### Ataque 1 — refutação literal (20:05–20:20Z)
- **1a `sudo systemctl restart` no meio** (job de 300 s): restart devolveu em 0,5 s → `pendente`
  (`erro='worker reiniciado'`), `tentativa 1→0`, `reinicios 0→1`; worker novo repegou, `tentativa`
  voltou a 1, **passos zerados (reexecução do zero)**, `marc=0` durante toda a corrida; FINAL
  `concluido tentativa=1 reinicios=1 marc=1`, `resultado.marcador=738ce257…`, `proveniencia.reinicios=1`.
- **1b `kill -9` no filho**: → `pendente` (`morto por sinal 9`), repegado `tentativa 1→2` (kill do
  filho conta como tentativa, ADR §6) `reinicios=0`; FINAL `concluido tentativa=2 reinicios=0 marc=1`.
- **1c `kill -9` no worker (pai)**: filho morreu junto por `PR_SET_PDEATHSIG`; job ficou `rodando`
  até a ceifa por heartbeat vencido; worker novo (systemd, `NRestarts 0→1`) devolveu `reinicios=1`;
  FINAL `concluido tentativa=1 reinicios=1 marc=1`.
- **1d dois restart, o 2º ~6 s depois** (< `TimeoutStopSec=40`): `reinicios 0→1→2`; FINAL
  `concluido tentativa=1 reinicios=2 marc=1`.
- **Julgamento pedido pelo item** ("reexecutar do zero silenciosamente satisfaz o portão?"): **sim**.
  O ADR promete "reinício = reexecução" com tarefa idempotente e troca atômica; a reexecução é
  registrada (`reinicios`, `proveniencia`, `erro='worker reiniciado'`), o job nunca some nem aparece
  concluído no intervalo, e o marcador do último passo comprova a execução inteira. Não é silencioso
  no sentido de enganar.

### Ataque 2 — forja por SQL como plat_app (20:15Z)
`current_user=plat_app`, tenant 1. `UPDATE plat.job SET estado='rodando'/'concluido'` → **permission
denied for table job** (REVOKE UPDATE, migr. 006). `INSERT` já concluído → **job nasce pendente e sem
resultado** (gatilho `job_transicao`). `via_worker_ligar()` e todas as funções do worker e `SELECT
plat.worker` → **permission denied**. `SET plat.via_worker='sim'` é aceito como GUC de sessão, porém
**inócuo** (o UPDATE segue barrado pela permissão de tabela).

### Ataque 3 — forja com a senha de plat_worker (modelo de ameaça pedido; 20:18Z)
Com `PLAT_DSN_WORKER` (do `.env`, 600) e o nome do worker lido em `GET /api/jobs/{id}.worker`
(**público**): `plat.job_terminar(jid,'<nome público>','concluido',{marcador:forjado},…)` devolveu
`ok=TRUE` e o job virou `concluido` com resultado forjado **sem a execução ter terminado** (marcador
real = 0). Nome de worker inventado → `ok=FALSE`. `plat_worker` NÃO lê `plat.job` direto. Isto **não
refuta o portão**: exige o segredo do worker, que é a própria autoridade do worker. **Nota de ameaça
(fraqueza 2):** quem obtém `PLAT_DSN_WORKER` forja conclusão de qualquer job de qualquer inquilino; o
nome do worker é público; não há autenticação por-processo — a senha é o único portão.

### Ataque 4 — worker homônimo
`job_ceifar(int,text,int)` foi removida (só resta `job_ceifar(int,int)`); a ceifa devolve só job de
heartbeat vencido cujo worker dono também está sem sinal, nunca por nome; identidade `<base>:<pid>`
(migr. 012). Medida do testador reconferida: homônimo com job de 240 s → `reinicios` ficou 0.

### Ataque 5 — RLS cruzado A→B (20:16Z)
15 rotas `/api/jobs*` e `/api/agendas*` do OpenAPI vivo com sessão de `demo` sobre recursos de
`demo2`: listas não trazem o recurso de B; rotas com id → `404`; SSE de job de B com sessão de A →
`404`; SSE próprio com `Last-Event-ID` 0/gigante/`abc` reenvia só o log do próprio job; agenda de B
intacta. **0 vazamento.**

### Ataque 6 — limites (20:19–20:24Z)
3 GB → `falhou 'memória excedida (limite 256 MB)'`, worker vivo, `NRestarts=0`. Ignora SIGTERM →
`cancelado` em 40,7 s (`morto após ignorar cancelamento`). `timeout_s=5` → `falhou 'tempo esgotado'`.
3 pesados → 1 rodando, 2 pendente (1 pesado por vez). 10 000 NOTIFY em 0,02 s → worker tick 1,3 ms,
RSS estável, API 200, `NRestarts=0`; payload 8001 bytes → `payload string too long`. Cron inválido /
fuso inválido / intervalo < 15 min → 422; cota de agendas parou em 50 → 413.

### Ataque 7 — unidade x ADR §4.5
`MemoryMax=2G`, `MemoryHigh=1536M`, `KillMode=mixed`, `OOMPolicy=continue`, `TimeoutStopSec=40`,
`Restart=always`, `RestartSec=3` — todos idênticos ao ADR. **Conforme.**

### Ataque 8 — placeholder/segredo/nome de cliente
0 placeholder no escopo (`app/jobs`, `db/migracoes/004..013`, `deploy/plat-worker.service`, `web` fora
de vendor); nenhuma senha embutida (só `.env` 600, fora do git); nenhum nome de cliente. **Conforme.**

### Ataques 9/10 — ADR x código e testes que não testam
`test_jobs_reinicio.py` usa `sudo systemctl` real e confere o marcador; `test_jobs_transicoes.py`
cobre as três camadas da 006 e o expurgo. Sem promessa de ADR sem implementação nem teste oco.

## Riscos / fraquezas (não refutam o portão)
1. `plat_trabalho.passos` e `.marcadores` **sem RLS** e sem `tenant_id`: cruzamento entre inquilinos
   nas linhas de scratch (hoje só diagnóstico; risco quando tarefas reais guardarem efeito parcial ali).
2. `PLAT_DSN_WORKER` = autoridade total sobre estado de job de todos os inquilinos; nome do worker é
   público; sem autenticação por-processo.
3. `plat_app` detém DELETE em `plat.job` (confinado por RLS; nenhuma rota o expõe) — over-grant a rever.

## Pendências
- Não rodei `make check` inteiro (fila de 1 slot + backend do catálogo na mesma árvore; sem pytest
  concorrente sem flock, sem reinstalar). Reconferência foi por reprodução direta no serviço vivo.
- Paridade Esri (P4), concorrência alta e PostGIS/vetorial fora do escopo deste item.

## Para o próximo papel (gerente)
Portão passa cláusula a cláusula (ver `refutacao.json`). Deixei `plat-api` e `plat-worker` **ativos**.
Não consertei nada. Decisões para o dono / próximos itens: fechar RLS de `plat_trabalho` antes de
tarefas que gravem dado do inquilino ali (fraqueza 1); tratar `PLAT_DSN_WORKER` como segredo de
mesmo nível que a chave do servidor (fraqueza 2); revisar o grant de DELETE de `plat_app` (fraqueza 3).
