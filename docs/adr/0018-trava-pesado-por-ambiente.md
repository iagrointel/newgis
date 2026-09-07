# ADR 0018 — Trava do job pesado amarrada ao ambiente (item F5)

## Contexto

Achado do adversário do reescritor de schema (`laco/handoffs/T4/ADVERSARIO-reescritor-schema.md`,
achado F5): `app/jobs/worker.py` regra "1 job pesado por vez" usa
`SELECT pg_try_advisory_lock(hashtext(%s))` com `LOCK_PESADO = "plat.job.pesado"`, uma STRING
CONSTANTE, passada como parâmetro da consulta.

Dois fatos do Postgres tornam isso um defeito de isolamento entre ambientes:

1. `pg_try_advisory_lock` é uma trava do **cluster inteiro**, não do schema, do banco lógico nem
   da role — o número devolvido por `hashtext(chave)` é a única coisa que distingue uma trava de
   outra.
2. `app/schema_ambiente.py` (`CursorSchemaAmbiente`) reescreve o **texto** da consulta trocando
   `plat`/`plat_trabalho` pelo schema do ambiente atual — mas `LOCK_PESADO` nunca aparece no texto
   da consulta, só como bind parameter (`%s`). Não há o que reescrever.

Resultado medido: produção, homologação e as dezenas de trilhas de teste (`laco/trilha_ambiente.sh`)
disputam a MESMA trava numérica. A regra "um pesado por vez" (por design, por AMBIENTE) virou "um
pesado por vez na máquina toda, entre todos os ambientes" — sem aviso, sem log, sem teste que
pegasse.

**Sintoma que confirmou o achado (07/09):** a fila de junção reprovou o mesmo lote em dois testes
diferentes rodando ao mesmo tempo (`tests/api/catalogo/test_busca.py`, depois
`test_compartilhamento.py`) — assinatura clássica de disputa de recurso do cluster: a falha muda
de lugar a cada rodada porque depende de qual outra trilha estava seguraNdo a trava naquele
instante, não de qual código mudou no ramo. A bisseção da fila estava (corretamente, dado os
sintomas errados) culpando ramos inocentes.

## Decisão

**A chave da trava passa a incluir o schema do ambiente**: `chave_lock_pesado(schema=None)` em
`app/jobs/worker.py` devolve `f"{schema or settings.PLAT_SCHEMA}:{LOCK_PESADO}"`; os dois pontos
que chamavam `hashtext(LOCK_PESADO)` (pegar o pesado em `_pegar`, soltar em `_soltar_pesado`) agora
chamam `hashtext(chave_lock_pesado())`.

Por que amarrar em `settings.PLAT_SCHEMA` e não inventar uma variável nova: é o MESMO valor que já
distingue produção de homologação de cada trilha (`PLAT_DSN_WORKER` deriva o papel do worker dele,
`PLAT_CANAL_JOB`/`PLAT_CANAL_WORKER` distinguem canal de notificação por ambiente do mesmo jeito).
Reusar o schema em vez de adicionar `PLAT_AMBIENTE_ID` novo evita uma quinta variável para manter
sincronizada com as outras quatro.

Por que isto não é um caso para `CursorSchemaAmbiente`/`reescrever_schema`: o mecanismo existente
resolve exatamente o problema de "texto SQL com `plat.` embutido"; um bind parameter nunca passa
pelo texto, então estender a regex não ajudaria — o conserto certo é na ORIGEM do valor (o código
Python que monta a chave), não no cursor.

Estabilidade dentro do mesmo ambiente: `settings.PLAT_SCHEMA` não muda durante a vida de um
processo `worker.py`, então a chave é constante para todas as chamadas de um mesmo worker — a
garantia original ("um pesado por vez" DENTRO do ambiente) continua de pé; só o cruzamento ENTRE
ambientes foi eliminado.

## Varredura de recursos do cluster com nome constante (mesma classe de defeito)

Levantamento em `app/` e `db/` por qualquer recurso do Postgres que é global ao cluster/banco (não
namespaced por schema) e identificado por um literal fixo:

| recurso | onde | estava com nome constante? | veredito |
|---|---|---|---|
| advisory lock "1 pesado por vez" | `app/jobs/worker.py` (`LOCK_PESADO`) | SIM — valor viaja como parâmetro, invisível ao reescritor de schema | **CONSERTADO neste item** (`chave_lock_pesado`) |
| canal `LISTEN`/`NOTIFY` `plat_job` (progresso de job por SSE) | `db/migracoes/004_jobs.sql`, `006_jobs_transicoes.sql` (`pg_notify('plat_job', ...)`); consumido em `app/jobs/eventos.py` via `settings.PLAT_CANAL_JOB` | Literal na migração, mas o literal aparece como TEXTO SQL dentro da própria migração — passa pelo reescritor de migração por ambiente (`laco/trilha_reescrever.py` e `db/reescrever_homolog.py`, ambos com `_CANAL_JOB = re.compile(r"\bplat_job\b")`) antes de a migração ser aplicada em cada schema; o app lê o nome final por `settings.PLAT_CANAL_JOB` | **JÁ ISOLADO** por um caminho diferente (reescrita da migração, não do parâmetro) — nada a fazer |
| canal `LISTEN`/`NOTIFY` `plat_worker` (acordar o worker) | mesmas migrações (`pg_notify('plat_worker', ...)`); `LISTEN {settings.PLAT_CANAL_WORKER}` em `app/jobs/worker.py`; papel `plat_worker` também usa o mesmo literal | Mesmo mecanismo do item acima (`_PAPEL_WORKER = re.compile(r"\bplat_worker\b")` cobre papel E canal, é o mesmo token) | **JÁ ISOLADO** — nada a fazer |
| papel `plat_app` / `plat_worker` (login) | migrações `CREATE ROLE`/`GRANT` | Literal na migração | **JÁ ISOLADO** pela mesma reescrita (`_PAPEL_APP`/`_PAPEL_WORKER`) |
| GUC de sessão `plat.tenant_id` / `plat.usuario_id` (`current_setting`/`set_config`) | `app/db.py`, `app/jobs/worker.py`, `app/jobs/tarefas.py` | É um nome de configuração de SESSÃO (efêmero, por conexão), não um objeto persistente do cluster — quem grava e quem lê estão na MESMA sessão/processo, nunca cruzam ambiente | **Não é este defeito** (documentado explicitamente em `app/schema_ambiente.py`, por quê fica de fora da reescrita) |
| agendamento (`plat.agenda`, "relógio das agendas") | `app/jobs/agenda.py` | Não usa lock nem canal com nome fixo — concorrência é por linha (`FOR UPDATE SKIP LOCKED` em `plat.agenda_vencidas`), já dentro do schema do ambiente | **Não é este defeito** — já isolado pela tabela ser schema-qualificada |
| eleição de líder / tarefa agendada com identificador fixo | busca em `app/`, `db/` | nenhuma ocorrência encontrada (`grep -rn "lider\|leader\|election\|pg_cron"`) | **não existe no código hoje** |

Varredura: `grep -rn "advisory" app/ db/` (achado único: `LOCK_PESADO`); `grep -rn "pg_notify\|LISTEN"
app/ db/` (canais `plat_job`/`plat_worker`, já isolados); nenhuma outra ocorrência de
`pg_try_advisory_lock`/`pg_advisory_lock`/`pg_advisory_xact_lock` na árvore.

## Prova

`tests/unit/test_worker_lock_ambiente.py`, contra dois schemas de trilha REAIS (`plat_ttrava`,
`plat_ttravb`, criados por `laco/trilha_ambiente.sh`):

- `test_chave_e_constante_hoje_colide_entre_ambientes`: caracteriza o vetor do defeito (a chave
  crua colide entre ambientes reais — é isso que a fila de junção sofreu em 07/09).
- `test_ambientes_diferentes_nao_disputam_mais_a_mesma_trava`: **vermelho antes do conserto**
  (ambiente B ficava bloqueado pela trava do ambiente A), **verde depois**.
- `test_dentro_do_mesmo_ambiente_um_pesado_por_vez_continua_valendo`: garante que a garantia
  original não afrouxou — dentro do MESMO ambiente, a segunda sessão continua bloqueada.
- `test_chave_lock_pesado_usa_schema_do_ambiente_por_padrao`: o worker real (que nunca passa o
  schema explicitamente) fica amarrado ao próprio ambiente via `settings.PLAT_SCHEMA`.

Números medidos e comandos ficam no handoff do item (`laco/handoffs/T4/F5-trava-por-ambiente.md`).

## Consequências

- Produção continua com uma única trava (schema `plat`), comportamento inalterado.
- Cada ambiente (homologação, cada trilha) ganha a própria trava — nenhum efeito colateral entre
  eles.
- Não requer migração de banco nem variável de ambiente nova.
