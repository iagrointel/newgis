# T2 — plano (gerente) · trilhas paralelas

| trilha | item | área tocada | papéis | colide com |
|---|---|---|---|---|
| A | L0-02-tenant-auth | db/migracoes/003+, app/auth*, web/login, tests | arquiteto+dados → backend+frontend → testador → adversário → cronista | B só em app/main.py (ordem: quem comita primeiro) |
| B | L0-05-jobs | db/migracoes (jobs), app/jobs*, worker plat-worker :8153, web/tarefas, tests | arquiteto → backend+frontend → testador → adversário → cronista | A em app/main.py |
| P | decomposição do backlog (>200 itens) | laco/decomposicao/*.json + *_CONCEITO.md → estado.json | 7 decompositores → gerente (merge, validação de dependências) | nenhum |

Regra de conceito (pedido do dono 05/09): nenhuma trilha entra em 30 (construir) antes de o `L0_CONCEITO.md` existir e o
ADR do item o citar — para não refazer. As trilhas A e B começam pelo ADR (20) esperando esse arquivo.

## Portões (literais)
- L0-02: ver estado.json (inclui cláusulas herdadas do T1: SECURITY DEFINER checa inquilino; EXECUTE só plat_app;
  middleware grava plat.log_acesso; limiares no ADR: senha ≥ 8 com letra e número, bloqueio 5/15 min, expiração
  configurável de sessão/token, MFA TOTP por usuário).
- L0-05: job de 5 min com progresso em tempo real, cancelável, sobrevive a reinício (retoma ou marca falha, nunca some);
  1 worker por padrão com limite de RAM declarado; tela Tarefas por inquilino; teste automatizado.

## Medições previstas
A: teste cruzado A→B em TODAS as rotas do OpenAPI (0 × 200); tempo de login; e2e login/2FA/usuários com captura.
B: job sobrevivente a `systemctl restart plat-worker`; latência de progresso; RSS do worker; cancelamento ≤ 2 s.

## O que NÃO se faz no T2
Catálogo (L0-03), ingestão (L0-04), qualquer tela de mapa. SSO (L0-08) fica fora: só login local + TOTP + token.
