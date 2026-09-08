# Laço PLATAFORMA ENTERPRISE — ponto de retomada

Objetivo: construir e entregar em produção a plataforma SIG própria (pilha aberta) que substitui o
ArcGIS Enterprise. Pedido do dono em 05/09/2026: sem limite de tokens/tempo, sem placeholder, sem
perguntas no meio, arrasta-e-solta em tudo, rede de utilidades incluída.

- `estado.json` — estado vivo (objetivo, produto, guardrails, papéis, backlog (501 itens em 05/09 após decomposição: L0 68 · L1 65 · L2 100 · L3 34 · L4 65 · L5 61 · L6 32 · L7 76; conceitos em decomposicao/*_CONCEITO.md) com portão de
  pronto e refutação, ledger, decisões do dono D18-D21, placar). Gerado por `gera_estado.py` UMA vez;
  depois só o turno edita.
- `driver.sh` — cron */30: integridade, órfãos, varredura de placeholder, saúde, pytest rápido e
  AUTOTURNO (lança `claude -p` com a skill quando não há turno ativo há 90 min). Log: `driver.log`.
- Skill do turno (o "loop engineering prompt"): `~/.claude/skills/plataforma-enterprise/SKILL.md`.
- `handoffs/T<turno>/` — comunicação entre papéis, só por arquivo.
- `PAINEL.md` — placar e fronteira (o que ainda não faz), escrito pelo cronista a cada turno.
- Produto: `/home/dev/plataforma/enterprise/` (git). Schema `plat`, role `plat_app`, portas 8150-8159,
  unidades `plat-*`.

Retomar à mão: alias `plataforma` (sessão a44f35ad) e digitar `/plataforma-enterprise`; ou esperar o driver.
Parar: `estado.json` → `"estado": "PAUSADO"` (o driver e a skill param no passo 1).

## Trilhas em worktree e base por trilha (06/09/2026, 2ª sessão)

Uma segunda sessão passou a trabalhar no MESMO laço em **git worktrees separados**, para não disputar
a árvore com os agentes do gerente:

    /home/dev/plataforma/wt/{garage,stac,valida,amc}   ramos wt/*
    /home/dev/plataforma/laco/BRIEF_WORKTREES.md       regras que todo agente de trilha lê primeiro
    /home/dev/plataforma/laco/merge_wt.sh <nome>       traz o ramo para master por fast-forward
    /home/dev/plataforma/laco/marcar_item.py <id> <estado> "<nota>" [sha]   grava no estado.json

**O gargalo era o flock do pytest, não a máquina.** Toda trilha esperava a mesma fila porque todas
escreviam no schema `plat`. Conserto:

    bash /home/dev/plataforma/laco/trilha_ambiente.sh <nome>
    set -a; source /home/dev/plataforma/laco/var/trilha/<nome>.env; set +a
    venv/bin/pytest tests/unit tests/api -q      # SEM flock

Cria `plat_t<nome>`/`plat_trabalho_t<nome>`, papéis, linha no pg_hba (reload, nunca restart), aplica
todas as migrações reescritas (`trilha_reescrever.py`, mesma máquina do `make homolog`) e semeia os
admins de plataforma/demo/demo2 com credenciais próprias. Apagar ao fim:
`DROP SCHEMA plat_t<nome> CASCADE; DROP SCHEMA plat_trabalho_t<nome> CASCADE`.

Isso exigiu dois consertos no produto: **c311aa7** (as 12 conexões cruas da suíte usavam
RealDictCursor e ignoravam PLAT_SCHEMA) e o conserto de `CursorSchemaAmbiente` para tratar **bytes**
(qualquer `execute_values` furava o isolamento) — este último vem no merge do wt/amc.

⛔ Armadilhas medidas em 06/09, não repetir:
- rodar a suíte contra `plat` SEM exportar PLAT_SECRET faz login falhar e a política de bloqueio
  TRAVA o admin real por 15 min, para todas as sessões (aconteceu 3 vezes; ver D37/D40).
- toda escrita no `estado.json` passa por `flock /home/dev/plataforma/laco/.estado.lock` — travar só
  o próprio arquivo não protege de quem não trava (uma escrita foi perdida assim).
- número de migração NUNCA se reserva: recontar com `ls db/migracoes | tail -1` no instante do merge.
- em árvore compartilhada, `git add <arquivo>` sempre; `git commit -m` sem pathspec já varreu arquivos
  de outro agente.

**Medido em 06/09 sobre o custo de rodar isto:** os agentes gastam **1,1 % do tempo em CPU local**
(32,7 mi s de relógio contra 359 mil s de CPU, 20 processos) — máquina mais rápida não acelera agente,
só muda quantos cabem. O teto é RAM e depois a cota da API. Fechar 13 sessões paradas devolveu
5,5 GB de RAM e 3,7 GB de troca (ver /home/dev/SESSOES_FECHADAS_20260906.md, com id de retomada de
cada uma). Teto combinado entre as duas sessões: 4 agentes cada.
