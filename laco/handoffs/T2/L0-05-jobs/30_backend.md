# T2 · trilha B · L0-05-jobs · 30_backend (backend)

## Objetivo

Construir no repositório `/home/dev/plataforma/enterprise` a fila de jobs do ADR 0003: migração `004_jobs.sql`, pacote
`app/jobs/*` (registro por decorador, fila SKIP LOCKED + LISTEN/NOTIFY + heartbeat, worker com processo filho isolado,
cancelamento, reinício que recoloca órfão, cron, cotas, gancho gpu), rotas `/api/jobs`, `/api/agendas`, SSE e páginas
`/tarefas`, unidade `plat-worker` instalada e ativa, tipo de diagnóstico real (`prova.progresso`) e testes do portão.

Portão do item (literal): "job de 5 min mostra progresso em tempo real, pode ser cancelado, sobrevive a reinício do
serviço (retoma ou marca falha, nunca some); 1 worker por padrão com limite de RAM declarado; tela Tarefas por
inquilino; teste automatizado". Refutação: "adversário mata o worker no meio de um job e reinicia: job não pode aparecer
como concluído".

## O que fiz

Commits (só arquivos meus por caminho; nos compartilhados com a trilha A o índice recebeu "HEAD + meus trechos" por
`git hash-object`/`update-index`, nunca as linhas dela):

| commit | conteúdo |
|---|---|
| `cab32da` | `db/migracoes/004_jobs.sql`; `app/jobs/{__init__,registro,contexto_job,filho,worker,agenda,periodicos,tipos_prova,tipos}.py`; `app/settings.py` (PLAT_WORKER_*, PLAT_GPU_*, PLAT_JOBS_DIR, PLAT_JOB_MAX_REINICIOS, PLAT_RELOGIO_TESTE, `servicos()["worker"]`); `app/log.py` (+3 campos `job_id`, `tipo`, `pid_filho`); `requirements.txt` (croniter 6.2.4, python-dateutil 2.9.0.post0, six 1.17.0); `.env.exemplo`; `.gitignore` (`var/`); `Makefile` (`worker`, `e2e-worker`); `tests/unit/test_jobs_registro.py`, `tests/unit/test_cron.py`, `tests/unit/test_settings.py` (1 linha) |
| `52d7a3b` | `app/jobs/{contexto,servico,eventos,rotas}.py`; `app/saude.py` (campo `fila`); `docs/openapi.json` (regenerado); `tests/jobs_sessao.py`; `tests/api/jobs/{conftest,test_jobs_fila,test_jobs_cancelamento,test_jobs_memoria,test_jobs_rls,test_jobs_agenda,test_jobs_sse,test_jobs_progresso,test_jobs_reinicio}.py`; `tests/api/test_saude.py`; `tests/medidas/L0-05-jobs.json` |
| `674798d` | `deploy/plat-worker.service`; `install.sh` (chaves no `.env` novo e existente, passo `h2`, conferência `workers_vivos` no passo `j`) |
| `431ba0c` | `install.sh`: inquilinos `demo`/`demo2` com `cota_jobs_dia = 100000` (a suíte esgotou os 1.000 do padrão no mesmo dia) |

O que está construído, em uma linha por peça:

1. **Migração 004** (idempotente; funções `CREATE OR REPLACE`, gatilhos e políticas com `DROP ... IF EXISTS`): `plat.job`,
   `job_log`, `worker` (sem RLS, `REVOKE ALL FROM plat_app`), `agenda`, `plat_trabalho` (+ `passos`, `marcadores`); RLS
   `p_job`/`p_job_log`/`p_agenda`; gatilhos `job_estado_final_imutavel` (estado final não muda: `check_violation`),
   `job_notificar` (`plat_job` para o navegador; `plat_worker` em pendente novo e em cancelamento) e `job_log_notificar`;
   funções SECURITY DEFINER `job_pegar`, `job_pid`, `job_heartbeat`, `job_terminar`, `job_devolver(..., p_max_reinicios,
   p_proveniencia)`, `job_ceifar(p_limite_s, p_worker, p_max_reinicios)`, `worker_*`, `fila_estado`, `cota_jobs_simultaneos`,
   `cota_jobs_dia`, `cota_agendas`, `jobs_no_dia`, `agenda_vencidas(p_agora)`, `agenda_enfileirar(10 parâmetros: os limites
   do tipo vêm do registro)`, `agenda_registrar_fim`, `agenda_periodica_sincronizar`, `jobs_expurgar`; todas com `REVOKE
   EXECUTE FROM PUBLIC` + `GRANT` só a `plat_app` (conferido em `pg_proc.proacl`). Inquilino `plataforma` só garantido
   (`ON CONFLICT DO NOTHING`, sem `ativo`/`config`): quem o governa é a 003 da trilha A (superadmin vive nele).
2. **Registro** `@tarefa(nome, descricao, parametros, pesado, memoria_mb, timeout_s, tentativas, chave, executor, versao,
   threads_blas, perfil_minimo, ferramentas)`: recusa na importação nome repetido/fora do padrão, `memoria_mb` fora de
   `[128, PLAT_WORKER_MEMORIA_MB]`, leve > 1024, `executor='gpu'` sem `pesado` ou sem `PLAT_GPU_SSH` (mensagem nomeia a chave).
3. **Filho** (`filho.py`): `prctl(PR_SET_PDEATHSIG, SIGKILL)`, `OPENBLAS/OMP/MKL_NUM_THREADS = threads_blas`,
   `RLIMIT_DATA = memoria_mb`, `app.db._pool = None`, SIGTERM vira flag, fds do pai fechados, códigos 0/3/4/5/1, sempre `os._exit`.
4. **Worker** (`worker.py`, `python -m app.jobs.worker`): conexão própria autocommit + `LISTEN plat_worker`; laço por
   `select()` ≤ 1 s que também acorda por **self-pipe de SIGCHLD/SIGTERM** (`signal.set_wakeup_fd`); fork por job com pipe;
   heartbeat 10 s; cancelamento por escalonamento (30 s SIGTERM, +10 s SIGKILL); `timeout_s`; "1 pesado por vez" por
   `pg_try_advisory_lock(hashtext('plat.job.pesado'))`; ceifa (`job_ceifar(60)`, `worker_ceifar(90)`) e relógio das
   agendas a cada 30 s; partida devolve os jobs com `worker = meu nome`; parada devolve (`reinicios += 1`), SIGTERM ao
   filho, 20 s, SIGKILL, desregistra; `/saude` em `127.0.0.1:8153` atendido no próprio laço (sem thread: fork com thread
   é armadilha). Proveniência gravada no fim (também no caminho de retentativa).
5. **Agenda** (`agenda.py`): croniter + `zoneinfo`; 5 campos; intervalo mínimo 15 min; `tick(con, agora)` em transação
   explícita (SKIP LOCKED entre workers + UNIQUE como segunda trava); ocorrência enfileirada = a mais recente vencida;
   cota do dia pula e avança; tipo não registrado pula e avança; `PLAT_RELOGIO_TESTE` só em `dev`.
6. **Periódico** `jobs.expurgo` (`30 3 * * *` America/Sao_Paulo, inquilino `plataforma`, sincronizado na partida).
7. **Tipos de diagnóstico** (`tipos_prova.py`, todos `perfil_minimo='editor'`): `prova.progresso(duracao_s, passos, chave)`
   com efeito parcial em `plat_trabalho.passos` (apagado na limpeza, inclusive em `Cancelado`) e marcador gravado só no
   último passo; `prova.memoria(mb)` (memoria_mb 256, tentativas 1); `prova.falha(definitiva)`;
   `prova.ignora_cancelamento`; `prova.pesado`; `prova.tempo_esgotado` (timeout_s 5).
8. **API** (`rotas.py`, modelos pydantic em toda rota): as 13 rotas da seção 9 do ADR + `GET /tarefas` e `/tarefas/{id}`
   (via `app.paginas.servir("tarefas.html")`). Sessão pela dependência da trilha A `autenticado("jobs.executar")`;
   `jobs.gerir_todos` (admin) vê o inquilino inteiro, os demais só os próprios; erros D18 pelo tratador global de
   `app.erros` (`ErroServico` herda de `ErroAPI`); `contexto.py` é só o adaptador `Auth → Sessao`.
9. **SSE** (`eventos.py`): thread `LISTEN plat_job` por processo iniciado na 1ª conexão; fan-out por `job_id` em filas
   asyncio; primeiro evento `estado`, `log` com `id`, `fim` no estado final; `Last-Event-ID` (inclusive `0`) reenvia o
   log; keepalive 15 s; 30 min; 10 conexões por usuário por processo (429); `X-Accel-Buffering: no`.
10. **Unidade** `deploy/plat-worker.service` (Restart=always, TimeoutStopSec=40, KillMode=mixed, OOMPolicy=continue,
    MemoryHigh=1536M, MemoryMax=2G) e `install.sh` passo `h2`; instalação executada às **15:19:49 UTC de 05/09/2026**.

## Evidência (comando + saída literal)

Migração e permissões:

```
$ sudo bash db/migrar.sh
igual      003_identidade_acesso
aplicada   004_jobs (157 ms)
migracoes: aplicadas 1 · reaplicadas 0 · iguais 3 · pendentes 0
$ sudo -u postgres psql -d iagro_sat -Atc "select proname, proacl from pg_proc where pronamespace='plat'::regnamespace and proname like 'job%' ..."
job_pegar|{postgres=X/postgres,plat_app=X/postgres}          # sem =X (PUBLIC) em nenhuma função do worker
job_terminar|{postgres=X/postgres,plat_app=X/postgres}
fila_estado|{postgres=X/postgres,plat_app=X/postgres}
```

Instalação (uma vez, ao final):

```
$ date -u; sudo bash install.sh plat.iagrointel.com 8150
2026-09-05T15:19:44Z
== h. systemd plat-api        /saude local respondeu 200 em 2 s      Active: active (running) since Sat 2026-09-05 15:19:48 UTC
== h2. systemd plat-worker    /saude do worker respondeu 200 em 2 s  Active: active (running) since Sat 2026-09-05 15:19:49 UTC
== j. conferência pública     https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow · Strict-Transport-Security: max-age=31536000
== instalado em 7 s: https://plat.iagrointel.com (serviços plat-api :8150 e plat-worker :8153)
$ curl -s https://plat.iagrointel.com/saude | ...
{'ultima_migracao': '004_jobs', 'servicos': {..., 'worker': 'ok'}, 'fila': {'pendentes': 4, 'rodando': 0, 'workers_vivos': 1, 'ultimo_heartbeat': '2026-09-05T15:24:41Z'}}
$ curl -s http://127.0.0.1:8153/saude
{"worker": "iagrosat-db-sp", "pid": 2793319, "versao": "0.1.0", "git_sha": "1668d7659f03", "processos": 1, "rodando": [], "pesado_em_curso": false, "ultimo_tick_ms": 1.4, "rss_kb": 40464, "em": "2026-09-05T15:20:06.651Z"}
$ systemctl show plat-worker -p MemoryPeak -p NRestarts        (15:24 UTC, depois de 3 rodadas da suíte)
NRestarts=0 MemoryPeak=93622272
$ sudo journalctl -u plat-worker --since 15:19 -o cat | grep -m1 "worker iniciado"
{"ts": "2026-09-05T15:19:49.967+00:00", "nivel": "INFO", "msg": "worker iniciado: nome=iagrosat-db-sp processos=1 porta=8153 tipos=7 orfaos_devolvidos=0", "logger": "plat.worker"}
$ sudo journalctl -u plat-worker --since 15:19 -o cat | grep -c '"ERROR"'
0
```

Suíte do item contra o `plat-worker` do systemd (cada teste dispara jobs reais na unidade):

```
$ PYTHONNOUSERSITE=1 venv/bin/pytest tests/api/jobs tests/api/test_saude.py tests/unit/test_jobs_registro.py tests/unit/test_cron.py -m "not lento" -q
15:25:40
.....................................................................    [100%]      # 69 passed
15:26:25
$ venv/bin/ruff check app tests
All checks passed!
```

Medidas (`tests/medidas/L0-05-jobs.json`, gravado por `PLAT_GRAVAR_MEDIDAS=1`, git 1668d76 na hora da gravação; o testador regrava):

```
cancelamento_s: 0.428 s          POST /api/jobs/{id}/cancelar em prova.progresso rodando até estado=cancelado
jobs_vazios_por_min: 3180.8      100 prova.progresso(duracao_s=0) criados pela API e concluídos por 2 workers (plat-worker 1 processo + worker extra 2 processos)
rss_worker_kb: 40768 kB          VmRSS do pai do worker em :8153/saude depois do job de memória
latencia_progresso_s: 1.005 s    menor diferença heartbeat_em (filho) -> evento estado no cliente SSE (carimbo com 1 s de granularidade)
sse_primeiro_evento_publico_s: 0.025 s   GET https://plat.iagrointel.com/api/jobs/{id}/eventos até o primeiro evento estado (nginx + uvicorn)
```

Prova de fumaça dos caminhos de morte (worker em primeiro plano, antes do install):

```
prova.progresso concluido 100 | prova.falha(definitiva) falhou "falha definitiva de prova" | prova.memoria(600) falhou "memória excedida (limite 256 MB)"
{"msg": "job terminou: concluido (código 0)"} {"msg": "job terminou: falhou (código 4)"} {"msg": "job terminou: falhou (código 5)"}
marcadores 1 · tabelas/linhas de trabalho sobrando 0
```

Medições que mudaram o desenho (comando e saída no scratch da sessão, reproduzíveis):

```
# custo do DDL neste servidor (3 rodadas; catálogo com 3,2 mil objetos, disco a 98 %):
rodada 0: pool+ctx 11 | drop+create 540 | log 4 | insert 1 | progresso 2 | marcador 1 | drop 7 ms
rodada 1: pool+ctx 13 | drop+create 1030 | log 5 | insert 2 | progresso 3 | marcador 1 | drop 8 ms
fork+exit ms: [3.2, 2.9, 2.7, 2.3, 2.4]
commit_ms mediana=0.2 p95=0.6 · connect_ms ≈ 8 · POST /api/jobs ≈ 6 ms · servico.criar 2 ms
# antes do self-pipe de SIGCHLD: "job iniciado 15:11:05.637 -> terminou 15:11:06.661" (1,02 s por job vazio: o pai só via a saída do filho no timeout do select);
# depois: 20 jobs vazios com 1 processo em 8,5 s -> 141/min; com 2 workers (3 processos) 3.180/min.
```

## Riscos

1. **Dependência da trilha A não comitada.** `app/jobs/contexto.py` e `rotas.py` importam `app.auth.sessao`, `app.erros` e
   `app.paginas`; a linha `rotas_jobs` está dentro do `app/main.py` reescrito por ela (`ROUTERS`). Num checkout de
   `52d7a3b` sem o commit da trilha A, `import app.main` falha (`cannot import name 'paginas'`) — verificado numa worktree.
   A árvore de trabalho está coerente e instalada; o gerente fixa a ordem (A comita `app/auth`, `app/erros`,
   `app/paginas`, `app/main.py`, `app/db.py` e regenera `docs/openapi.json` — hoje o arquivo comitado já traz as rotas dela).
2. **Suíte inteira não está verde por causas fora do item**: `make sem-marcador` reprova `app/auth/sessao.py:309`
   (o nome da constante dos métodos HTTP de escrita, linha 309, contém em maiúsculas a sequência que a expressão de marcadores procura); `pytest` inteiro não coleta por `tests/api/test_log.py` (novo, da A)
   ter o mesmo nome base de `tests/unit/test_log.py`; ignorando esse arquivo, os erros restantes são todos em
   `tests/api/test_{cruzado,eu,grupos,log_acesso,login,plataforma,sessao,usuarios}.py` (fixtures dela). No meu escopo,
   0 falhas. `tests/unit/test_instalador.py::test_hsts...` reprova por mudança dela em `deploy/nginx.conf`.
3. **Sessão de teste compartilhada**: a suíte da trilha A troca a senha do admin `demo` e apaga as sessões dele; rodada
   ao mesmo tempo que a minha, os meus testes recebem 401 no meio (aconteceu uma vez). Não rodar as duas juntas.
4. **`X-Accel-Buffering` não chega ao cliente** pela URL pública: o nginx o consome (está na lista padrão de
   `proxy_hide_header`). O teste confere o cabeçalho direto em `:8150` e o efeito (primeiro evento em 0,025 s) pelo nginx.
   O ADR 0003 seção 5 diz "chega"; corrigir a frase no cronista.
5. **Desvios do ADR, com motivo**: (a) efeito parcial de `prova.progresso` em linhas de `plat_trabalho.passos`, não em
   tabela por job — DDL mede 0,5–1 s aqui e escondia a vazão; regra escrita na 004 para autores de tipos; (b) inquilino
   `plataforma` sem `ativo=false` (a 003 o exige ativo com 2FA); (c) `job_devolver` ganhou `p_proveniencia` e
   `job_ceifar`/`job_devolver` `p_max_reinicios`; `agenda_enfileirar` tem 10 parâmetros; funções extras `job_pid`,
   `jobs_no_dia`, `agenda_registrar_fim`, `agenda_periodica_sincronizar`, `jobs_expurgar`; (d) `prova.progresso` não tem
   parâmetro `pesado` (é propriedade do tipo; `prova.pesado` cobre) e existe `prova.tempo_esgotado`; (e) perfil mínimo do
   tipo continua sendo checado (`403 perfil_insuficiente`), além do privilégio `jobs.executar` da rota; (f) 422 de query
   inválida (`limite=x`) sai do tratador global da A (`validacao`), e os meus (`estado_invalido`, `ordenar_invalido`,
   `data_invalida`, `parametros_invalidos` com `detalhe` por campo) do serviço.
6. **Cota de demonstração**: `demo`/`demo2` ficam com `cota_jobs_dia = 100000` pela semeadura do `install.sh`; produção
   continua com 1.000 (o teste `test_cota_diaria_de_jobs_413` prova o 413 com cota 0 em `demo2`).
7. **Sobrecarga de função**: `CREATE OR REPLACE` não substitui assinatura diferente; a 004 comitada já traz o
   `DROP FUNCTION IF EXISTS plat.job_devolver(uuid, text, text, boolean, int, int)` do rascunho. Antes do commit a 004 foi
   reaplicada apagando a linha de `plat.versao_migracao` (arquivo ainda não publicado); depois do commit é imutável.
8. **RAM**: `MemoryPeak` da unidade 93,6 MB durante 3 rodadas da suíte (limite 2G); `free -g` = 3 GB disponíveis no install.
9. **Advisory lock após queda do banco**: reconexão do worker zera `lock_pesado`; um pesado já em execução segue e um
   segundo pode começar até ele terminar (janela rara, documentada no worker).
10. Durante o desenvolvimento um `pkill -f` com o padrão presente na própria linha de comando matou o meu shell
    (armadilha da casa); o worker de desenvolvimento passou a ser gerido por arquivo de PID e foi encerrado antes do
    install (`pgrep -af jobs.worker` = só o do systemd).

## Pendências

- Trilha A: comitar `app/main.py` com a linha `rotas_jobs` (já está lá), `app/db.py`, `app/auth`, `app/erros`,
  `app/paginas`; regenerar `docs/openapi.json` depois do merge (`make openapi`); renomear a constante dos métodos de escrita em `app/auth/sessao.py` (marcador),
  `tests/api/test_log.py` (nome base) e o teste do HSTS.
- Testador: reinício real (`sudo systemctl restart plat-worker`, `kill -s KILL`) e o job de 5 min — arquivos prontos,
  marcados `lento` (comandos abaixo); `MemoryPeak` da unidade; regravar `tests/medidas/L0-05-jobs.json` com `make medidas`
  (só o item: `PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/jobs`).
- Frontend (31, já comitado em 1668d76): contrato mantido; `GET /api/jobs/tipos` traz `parametros_schema`; `/tarefas/{id}`
  servido por `paginas.servir`.
- Cronista: ADR 0003 seção 5 (cabeçalho consumido pelo nginx), seção 6 (efeito parcial em linhas), seção 7 (`plataforma`
  governado pela 003); `docs/PARIDADE.md` é do papel esri.
- Decisão do dono: nenhuma nova.

## Para o próximo papel (testador)

Pré-condição: `systemctl is-active plat-api plat-worker` = `active active`; `curl -s https://plat.iagrointel.com/saude`
com `"workers_vivos": 1`. Não rodar junto com a suíte da trilha A (risco 3).

```
cd /home/dev/plataforma/enterprise
# rápido (69 testes, ~45 s; cria ~150 jobs em demo/demo2 e um worker extra temporário em :18159 que morre no fim)
PYTHONNOUSERSITE=1 venv/bin/pytest tests/api/jobs tests/api/test_saude.py tests/unit/test_jobs_registro.py tests/unit/test_cron.py -m "not lento" -q
# lentos do portão (5 min de job + reinícios por systemctl; exige sudo -n; ~12 min)
make e2e-worker                      # = venv/bin/pytest -m lento tests/api/jobs
#   test_jobs_progresso.py: job de 300 s / 60 passos pelo SSE (>= 60 estados crescentes, heartbeat <= 10 s, marcador)
#   test_jobs_reinicio.py: restart no meio (reinicios=1, tentativa=1), kill -9 no pai (PDEATHSIG + ceifa na partida), 5 x kill -9 -> falhou "devolvido 5 vezes"
#   test_jobs_cancelamento.py::test_tarefa_que_ignora_a_flag_e_morta_em_30_mais_10_s
# medidas do item (regrava tests/medidas/L0-05-jobs.json)
PLAT_GRAVAR_MEDIDAS=1 PYTHONNOUSERSITE=1 venv/bin/pytest tests/api/jobs
# reinício manual e observação
sudo systemctl restart plat-worker; sudo journalctl -u plat-worker -o cat -n 20 | jq .
sudo systemctl kill -s KILL plat-worker      # Restart=always sobe de novo em 3 s; o job volta a pendente com reinicios += 1
systemctl show plat-worker -p MemoryPeak -p NRestarts -p MainPID
curl -s http://127.0.0.1:8153/saude | jq .
# criar um job à mão (cookie de sessão via tests/jobs_sessao.py)
PYTHONNOUSERSITE=1 venv/bin/python -c "from tests import jobs_sessao as j; from app.settings import settings; c=j.conectar(settings.PLAT_DSN); print(j.criar_sessao(c,'demo','admin')[0])"
curl -s -b plat_sessao=<token> -H 'Content-Type: application/json' -d '{"tipo":"prova.progresso","parametros":{"duracao_s":300,"passos":60}}' https://plat.iagrointel.com/api/jobs | jq .id
curl -N -b plat_sessao=<token> https://plat.iagrointel.com/api/jobs/<id>/eventos
```

O que o adversário vai tentar e onde está a defesa: matar o pai no meio (`PDEATHSIG` mata o filho; `job_ceifar(60,
meu_nome)` na partida devolve; marcador só no último passo → nunca `concluido` sem execução inteira); `UPDATE` de um job
final (gatilho `job_estado_final_imutavel`); ler `plat.worker` como `plat_app` (`InsufficientPrivilege`); job de outro
inquilino em toda rota (404 por RLS); estourar memória (`RLIMIT_DATA` → código 5 → `falhou`, worker segue, `NRestarts=0`).

---

Resumo em 8 linhas:
1. Fila própria em SQL entregue e instalada: `004_jobs.sql` (RLS, gatilhos, 19 funções SECURITY DEFINER só para `plat_app`), `app/jobs/*`, unidade `plat-worker` ativa desde 15:19:49 UTC (`NRestarts=0`, pico 93,6 MB, 0 erros no journal).
2. Cada job roda num filho com `PDEATHSIG`, `RLIMIT_DATA`, BLAS em 1 thread; cancelamento cooperativo medido em 0,428 s; memória excedida → `falhou` com o worker vivo; tempo esgotado, falha definitiva e retentativa 2/4 s com traceback no log.
3. Reinício: `job_devolver` (reinicios += 1, tentativa intacta), ceifa na partida por nome do worker, teto de 5 devoluções → `falhou`; marcador gravado só no último passo prova "nunca concluído sem execução inteira" (testes `lento` prontos para o testador).
4. Vazão 3.180 jobs vazios/min com 2 workers (portão ≥ 600) depois de dois achados medidos: CREATE TABLE custa 0,5–1 s neste servidor (efeito parcial foi para linhas em `plat_trabalho.passos`) e o pai só via a saída do filho no timeout do select (self-pipe de SIGCHLD).
5. API: 13 rotas do ADR + `/tarefas`, SSE com `Last-Event-ID`, `/saude` com `fila`; sessão e erros D18 pela trilha A (`autenticado("jobs.executar")`, `ErroAPI`) — `contexto.py` virou adaptador de 49 linhas.
6. 69 testes do item passam em 45 s contra o worker do systemd (fila, cancelamento, memória, RLS A→B em toda rota, agendas com dois relógios, SSE local e público); lint verde; medidas em `tests/medidas/L0-05-jobs.json`.
7. Commits só por caminho (`cab32da`, `52d7a3b`, `674798d`, `431ba0c`); `app/main.py` (reescrita da A com a minha linha `rotas_jobs`), `app/db.py` e o `openapi.json` final ficam com a trilha A, que ainda não comitou — HEAD só importa com o commit dela.
8. Fora do item e a reportar ao gerente: `sem-marcador` reprova `app/auth/sessao.py` (a constante dos métodos de escrita, linha 309, casa com a expressão de marcadores), `tests/api/test_log.py` colide com `tests/unit/test_log.py`, e a suíte da A invalida a sessão de `demo` se rodar junto com a minha.

---

## Correção T2 (achados do testador; commit `ad2ea29`; reinstalado às 15:59:37 UTC de 05/09/2026)

**Achado 1 — transição forjada.** `plat_app` com contexto de inquilino levava um job `pendente → rodando → concluido`
com resultado forjado por SQL: o gatilho da 004 só protegia o estado final. Correção em `db/migracoes/006_jobs_transicoes.sql`
(a 004 aplicada não foi editada), três camadas verificáveis por `tests/api/jobs/test_jobs_transicoes.py`:

1. **Role própria `plat_worker`** (LOGIN, sem BYPASSRLS, sem privilégio de tabela): única com EXECUTE em `job_pegar`,
   `job_pid`, `job_heartbeat`, `job_terminar`, `job_devolver`, `job_ceifar`, `worker_*`, `agenda_vencidas`,
   `agenda_enfileirar`, `agenda_periodica_sincronizar`, `jobs_no_dia`; `plat_app` perde o EXECUTE nelas. O processo pai
   conecta por `PLAT_DSN_WORKER` (settings, `.env.exemplo`; `install.sh` gera a senha, faz `ALTER ROLE` a cada execução e
   acrescenta a linha no `pg_hba.conf`). O filho continua `plat_app` dentro do inquilino do job.
2. **`REVOKE UPDATE ON plat.job FROM plat_app`**: a API cancela por `plat.job_cancelar(id, usuario)` e o filho reporta
   por `plat.job_progresso(id, worker, pct, mensagem)` (só progresso/mensagem/heartbeat do job rodando deste worker e
   deste inquilino); `linhas_log` contado por gatilho SECURITY DEFINER.
3. **Gatilho `plat.job_transicao`** (BEFORE INSERT OR UPDATE): job nasce `pendente` e limpo; entrar em `rodando`/
   `concluido`/`falhou` ou mudar `resultado`/`tentativa`/`reinicios`/`worker`/`iniciado_em`/`proveniencia`/`processo_pid`
   exige `plat.via_worker = 'sim'`, ligado e desligado só dentro das funções do worker (`via_worker_ligar/desligar`
   sem EXECUTE para `plat_app` — a 001 dá EXECUTE por privilégio padrão a toda função nova, o REVOKE tem de ser explícito;
   foi o primeiro teste a reprovar).

**Achado 2 — marcadores acumulando.** `plat.jobs_expurgar` passa a apagar marcadores e passos órfãos de `plat_trabalho`
(devolve `marcadores_apagados`, `passos_apagados`) e só roda no contexto do inquilino `plataforma` (`insufficient_privilege`
fora dele). Antes da correção: 1.371 marcadores, 11 órfãos.

Evidência:

```
$ sudo bash db/migrar.sh                       aplicada   006_jobs_transicoes
$ psql ... proacl                              job_pegar|{postgres=X/postgres,plat_worker=X/postgres}  job_terminar|{...,plat_worker=X/postgres}
                                               job_cancelar|{...,plat_app=X/postgres}  job_progresso|{...,plat_app=X/postgres}
                                               via_worker_ligar|{postgres=X/postgres}  job_transicao|{postgres=X/postgres}
                                               plat.job relacl: {postgres=arwdDxt/postgres,plat_app=ard/postgres}   # sem w (UPDATE)
$ psql ... pg_stat_activity                    plat_app|1 plat_worker|1                                             # o pai é plat_worker
$ sudo journalctl -u plat-worker --since 15:42 -o cat | grep -c '"ERROR"'   → 0   (os 6 erros anteriores, 15:40, eram do worker antigo
                                               sem EXECUTE entre a aplicação da 006 e o reinício com PLAT_DSN_WORKER)
$ venv/bin/pytest tests/api/jobs tests/api/test_saude.py tests/unit/test_jobs_registro.py tests/unit/test_cron.py tests/unit/test_settings.py -m "not lento" -q
15:58:04  ......................................................................................  [100%]   # 86 passed
15:58:51
$ venv/bin/ruff check app tests              All checks passed!
$ sudo bash install.sh plat.iagrointel.com 8150     (15:59:30 → 15:59:37 UTC)
senha de plat_worker alinhada ao .env · linha de plat_worker já existe em pg_hba.conf · /saude do worker respondeu 200 em 2 s
https://plat.iagrointel.com/saude → ultima_migracao 006_jobs_transicoes · fila {'pendentes': 0, 'rodando': 0, 'workers_vivos': 1} · worker ok
```

Testes novos/alterados: `test_jobs_transicoes.py` (UPDATE forjado pendente→rodando e →concluido = `permission denied`;
INSERT já concluído/com tentativa = recusado pelo gatilho; `plat_app` sem EXECUTE em 7 funções do worker;
`plat_worker` sem SELECT em `plat.job`/`plat.usuario`; `job_progresso` ignora outro nome de worker; `job_cancelar` em
estado final devolve o estado; expurgo apaga órfãos e é idempotente); `test_jobs_cancelamento.py` (UPDATE de estado
final agora é `permission denied`, não `check_violation`); `test_jobs_agenda.py` (relógio pela role do worker);
`test_saude.py` (`006_jobs_transicoes`). ADR 0003 com "alterado em T2" nas seções 2.2, 5, 6, 7 e 11.

Limite escrito (também no ADR): RLS por GUC continua sendo o limite de tudo o que é `plat_app` — quem tem a senha da
role escolhe o inquilino; a separação nova é entre quem executa tarefas (`plat_app`, no inquilino) e quem muda estado de
job (`plat_worker`). Observação de operação: com `PLAT_WORKER_PROCESSOS=1` a fila é serial; os testes `lento` do
testador (job de 600 s + `kill -9`) ocupam o único slot e a suíte rápida não pode rodar ao mesmo tempo (aconteceu:
9 jobs pendentes esperando; foram cancelados como restos de teste antes da rodada final).

---

## Integração T2 com a identidade (commits `ffedc05`, `90d03c0`, `7824846`; `plat-api` reiniciado às 16:28:09 UTC)

O que a trilha A esperava e foi entregue: (a) as 17 rotas de `/api/jobs*` e `/api/agendas*` declaram `x-auth: S/T` e
`x-privilegio: jobs.executar` no OpenAPI (a dependência aceita token com escopo `jobs:executar`; `admin:inquilino`
cobre); (b) `tests/api/eventos_esperados.py` com as 9 rotas de escrita e a migração `007_jobs_eventos` com o
vocabulário `jobs/criar`, `jobs/cancelar`, `agendas/criar|atualizar|apagar|pausar|retomar` — toda rota de escrita
registra o evento por `plat.evento_registrar` no contexto do inquilino; (c) `tests/api/cruzado_casos.py`: a preparação
cria um job pendente (agendado para 2099) e uma agenda em B, e os 17 casos provam 404 nos alvos de B e 2xx só sobre o
próprio chamador sem dado de B (job criado em A é cancelado e a agenda apagada logo depois); (d) `test_saude` compara
com a última migração em disco, sem citar nome; (e) `008`: reinício/ceifa não consomem tentativa (retomada volta ao
mesmo número; medido: um restart às 16:14:49 deixava `tentativa 2`); (f) `010`: as três funções de gatilho da 004
sem EXECUTE para PUBLIC/plat_app (achado de `test_funcoes_seguras`).

`make check` inteiro — as 5 falhas da rodada de 16:28 (409 testes, fase `teste`) e de quem eram:

| teste | causa | dono |
|---|---|---|
| `test_jobs_agenda::test_cinco_falhas_seguidas_pausam_a_agenda` | o `tick` enfileira toda agenda vencida, inclusive de outra sessão de teste rodando ao mesmo tempo | B — corrigido (`90d03c0`: conta só os jobs da própria agenda) |
| `test_jobs_agenda::test_cota_de_agendas_413_e_rls` | a preparação cruzada da A cria uma agenda em `demo2` na mesma rodada; cota fixa em 1 colidia | B — corrigido (cota = o que B já tem + 1) |
| `test_jobs_cancelamento::test_cancelar_rodando_em_ate_2_s` | `tentativa == 2` porque outra sessão reiniciou o `plat-worker` no meio (journal 16:14:49) e a retomada consumia tentativa | B — corrigido (`008`) |
| `test_cruzado::test_rota_nao_cruza[GET-/api/privilegios]` | digest de B mudou durante um GET: outra sessão escrevendo em `demo2` ao mesmo tempo | A / concorrência |
| `test_usuarios::test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga` | `possui_grupos` em vez de `ultimo_admin` (usuário com grupos da preparação cruzada de outra rodada) | A |

Rodadas seguintes: às 17:15 a reinstalação destrutiva do adversário caiu no meio (218 erros "banco em erro" — inválida);
às 17:18, 9 falhas: 6 × `503 /saude` + `test_migracoes` porque a `009_inquilino_apagar.sql` estava em disco sem
aplicar (A), `test_funcoes_seguras` (B, corrigido em `010`) e SSE não monotônico porque o `make medidas` do testador
reiniciou o worker (concorrência). A máquina esteve com 2–3 `pytest` de outras sessões ao mesmo tempo o tempo todo;
a partir de 17:40 toda rodada minha vai sob `flock /home/dev/plataforma/laco/.pytest.lock`.

## Correção T2 (2) (achado do testador; commit `9be9c6a`; `plat-worker` reiniciado às 17:40:36 UTC)

**Achado.** Worker lançado fora do systemd sem `PLAT_WORKER_NOME` usava o nome padrão (hostname) e `job_ceifar(60,
nome)` na partida do homônimo devolvia os jobs do worker vivo (job d80551e2 às 17:17: `reinicios=1`, progresso a 0, nada
no journal). Não foi worker meu: o de desenvolvimento morreu antes do install das 15:19 (`pgrep` só mostra o MainPID do
systemd e o filho dele); o cenário é reproduzível por qualquer processo com o mesmo nome-base.

**Correção.** (1) Identidade única por processo: `nome = <PLAT_WORKER_NOME ou hostname>:<pid>`, registrada em
`plat.worker` com heartbeat de 10 s; `job.worker` e a proveniência guardam essa identidade; `/saude` do worker expõe
`worker` e `nome_base`. (2) `012_jobs_identidade_worker.sql`: `job_ceifar(p_limite_s, p_max_reinicios)` devolve só job
com `heartbeat_em` vencido cujo worker dono também não deu sinal em `plat.worker` no mesmo prazo; a assinatura com nome
foi removida (`DROP FUNCTION`); a partida do worker chama a ceifa sem nome. Consequência escrita: restart limpo devolve na
hora (SIGTERM → `job_devolver`), `kill -9` é recolhido pela ceifa em até ~90 s (60 s de limite + tick de 30 s) — os
testes de reinício passam a esperar 150 s. (3) `013_jobs_execute_reafirma.sql`: depois da reinstalação destrutiva
mediu-se que **todas** as funções do worker tinham EXECUTE para `plat_app` de novo — a `011_catalogo.sql:893` (trilha do
catálogo, sem commit) faz `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app` e desfaz a 006; a 013 reafirma o
contrato e é idempotente. **Pedido à trilha do catálogo: trocar o grant global por grants explícitos por função**
(regra escrita na 013); a rede de segurança é `test_jobs_transicoes::test_plat_app_nao_executa_as_funcoes_do_worker`.
Observação: a `011_catalogo` está DIVERGENTE no banco (editada depois de aplicada), o que trava `migrar.sh` para todos;
apliquei 012/013 com `PLAT_MIGRACOES` apontando para uma cópia sem a 011 (o próprio script, nada manual).

**Testes** (`tests/api/jobs/test_jobs_identidade.py`): sobe um segundo worker com o MESMO nome-base do dono do job em
execução (fábrica `iniciar_worker`, sempre encerrada no fim) e prova que o job não muda de dono, não volta a zero e
termina `concluido` com `reinicios 0`, `tentativa 1`, proveniência com a identidade; `job_ceifar(30)` com o dono vivo
devolve 0 e não existe mais assinatura de 3 argumentos.

Evidência:

```
$ sudo -u postgres psql ... job_ceifar → p_limite_s integer, p_max_reinicios integer | {postgres=X/postgres,plat_worker=X/postgres}
$ sudo systemctl restart plat-worker   (17:40:36 UTC) → /saude: {"worker": "iagrosat-db-sp:3157352", "nome_base": "iagrosat-db-sp", ...}; journal 0 ERROR
$ sudo -u postgres psql ... funções de estado com plat_app=  → 0   (depois da 013; antes: 7 de 7)
$ flock laco/.pytest.lock venv/bin/pytest tests/api/jobs tests/api/test_saude.py tests/api/test_funcoes_seguras.py tests/unit/test_jobs_registro.py tests/unit/test_cron.py -m "not lento" -q
17:51:05 → 17:52:31   0 falhas (só pontos)
```

**`make check` inteiro depois da correção (2), sob `flock`, 17:52–17:56 UTC — não fica verde por causas fora do item:**

| fase | resultado | de quem |
|---|---|---|
| `lint` | reprova: 126 erros de ruff, todos em `app/catalogo/` e `tests/api/catalogo/` (não comitados) | trilha do catálogo |
| `sem-marcador` | passa | — |
| `teste` (`-m "not lento"`) | **492 passaram**, 13 falharam, 5 erros, 1 pulado (145 s): `tests/api/catalogo/*` 9 (catálogo, sem commit); `test_cabecalhos::test_referrer_policy_em_toda_rota` 7 (cabeçalho `Referrer-Policy` do nginx — trilha A); `test_migracoes::test_migrar_duas_vezes` (a `011_catalogo` está DIVERGENTE no banco); `tests/unit/test_busca_sintaxe.py` (catálogo). **No meu escopo (jobs, cron, registro, saúde, settings, transições, identidade): 0 falhas.** | — |
| `e2e` | não rodou nesta rodada: o e2e do catálogo (`tests/e2e/test_conteudo.py`, sem `flock`) ocupava a máquina; os `lento` da fila (job de 5 min, reinício, kill -9, 40 s do cancelamento forçado) foram medidos pelo testador da trilha e os arquivos estão em `tests/api/jobs/test_jobs_{progresso,reinicio,cancelamento}.py` | testador |

Para o gerente: o P3 do item exige que a trilha do catálogo comite (ou tire da árvore) `app/catalogo`, `tests/api/catalogo`,
`011_catalogo.sql` (e a reaplique sem divergência) e troque o `GRANT ... ON ALL FUNCTIONS` da 011 por grants explícitos;
e que a trilha A resolva o `Referrer-Policy`. Nada disso é editável por este papel.

---

# Correção T2 (3) — backend · L0-05-jobs · três consertos do `40_testes.md`

## Objetivo

Fechar os três defeitos que o testador deixou abertos na seção "Riscos/Pendências" do `40_testes.md`, sem afrouxar
nada do que já estava provado: (1) a semeadura do e2e dos 1.000 jobs, barrada — corretamente — pela migração 006;
(2) o perfil `visualizador`, que tomava 403 em `/api/jobs*` e deixava a tela Tarefas em "…" com 4 erros de console
(P1 reprovado para um perfil legítimo); (3) o `Cache-Control` duplicado na resposta SSE pela URL pública.

Commits (um por caminho, todos com o rodapé Co-Authored-By):

| commit | o quê |
|---|---|
| `7037009` | semeadura de demonstração (migração 014, e2e, testes de guarda, install.sh, .env.exemplo) |
| `ea77246` | privilégio `jobs.ver` (migração 015, rotas, vocabulário, ADR 0002 e 0003, testes, front só-leitura) |
| `a496cdd` | `Cache-Control` com uma origem só (nginx, middleware, ADR 0001 e 0002, teste) |

⚠ **Reinícios de serviço nesta rodada (o adversário está medindo):** `plat-worker` **não foi reiniciado nenhuma
vez** e não foi reinstalado. `plat-api` foi reiniciado **duas vezes** — **20:18:30Z** (para o processo passar a
enxergar `jobs.ver` nas rotas) e **20:20:49Z** (junto com o `nginx -s reload` do conserto 3). `nginx` recarregado
duas vezes: **20:20:49Z** e **20:22:05Z**. Nenhum `pkill`.

---

## Conserto 1 — semeadura do e2e dos 1.000 jobs (migração 014)

### O que fiz

O `test_primeira_pintura_com_mil_jobs` fazia `INSERT INTO plat.job (... estado='concluido', resultado=...)` como
`plat_app`. A 006 barra isso e **tem de continuar barrando**: era exatamente o achado 1 do testador. Em vez de
abrir exceção no gatilho, entrou uma função de demonstração com nome explícito, `plat.jobs_semear_demo`, com
**quatro guardas independentes**:

1. **interruptor de configuração, desligado por padrão** — `plat.ambiente.semear_demo` (tabela nova da 014, uma
   linha, `nome` com os mesmos valores de `AMBIENTES` em `app/settings.py`). Quem escreve é o `install.sh`, a
   partir do `.env`: `true` quando `PLAT_AMBIENTE=dev` **ou** `PLAT_SEMENTE_DEMO=sim`. Numa instalação de cliente
   as duas chaves faltam e o valor fica `false`. `plat_app` tem `SELECT` e **nada mais** (a 001 dá
   `SELECT/INSERT/UPDATE/DELETE` a `plat_app` em toda tabela nova do schema por `ALTER DEFAULT PRIVILEGES`, então
   o `REVOKE ALL ... FROM plat_app` é explícito na 014 — sem essa linha, MEDIDO, a API virava o próprio
   interruptor);
2. **inquilino de demonstração** — só `demo`, `demo2` e `zt-%`; inquilino de cliente nunca é semeado, mesmo com o
   interruptor ligado;
3. **estado terminal** — só `concluido`/`falhou`/`cancelado`. A função nunca cria job `pendente` visível ao worker
   nem `rodando`: a fila real não é alimentada por ela e nenhum resultado de execução é forjado;
4. **teto e marca** — no máximo 5.000 por chamada, sempre no inquilino do contexto, sempre com
   `parametros->>'semente_demo' = 'true'` (é por essa marca que o teste apaga o que semeou).

**A 006 não foi tocada.** O texto do gatilho `plat.job_transicao` é o mesmo, nenhum `GRANT`/`REVOKE` de `plat_app`
mudou, e nenhum caminho novo de forja foi aberto. O truque é que a função **insere o job `pendente` e limpo** — o
que o ramo de INSERT do gatilho da 006 já permite a qualquer chamador — e só então transiciona pelo **mesmo
caminho do worker** (`plat.via_worker_ligar()` dentro de `SECURITY DEFINER`, cujo `EXECUTE` `plat_app` não tem e
não passou a ter). Entre o INSERT e o UPDATE o job nasce com `agendado_para = now() + 100 anos`, para que nem por
acidente saia da fila; como tudo acontece numa transação só, o `NOTIFY` do worker só chega no commit, quando o job
já está terminal.

`EXECUTE` de `plat.jobs_semear_demo` só para `plat_app` (`postgres=X/postgres plat_app=X/postgres`, sem `PUBLIC`).

### Evidência (comando + saída literal)

```
$ ls db/migracoes | tail -1        (antes de criar)          $ bash db/migrar.sh
013_jobs_execute_reafirma.sql                                aplicada   014_jobs_semear_demo (63 ms)
                                                             migracoes: aplicadas 1 · reaplicadas 0 · iguais 12 · pendentes 0

$ sudo -u postgres psql -d iagro_sat -Atc "SELECT nome, semear_demo FROM plat.ambiente"
producao|t                       # este servidor roda a suíte com PLAT_AMBIENTE=producao; ligado por PLAT_SEMENTE_DEMO=sim

$ ... "SELECT relname, array_to_string(relacl,' ') FROM pg_class WHERE relname='ambiente' ..."
ambiente | postgres=arwdDxt/postgres plat_app=r/postgres plat_worker=r/postgres      # r = só SELECT

$ ... "SELECT proname, prosecdef, array_to_string(proacl,' ') FROM pg_proc WHERE proname='jobs_semear_demo'"
jobs_semear_demo | p_quantos integer, p_tipo text, p_parametros jsonb, p_estado text | t | postgres=X/postgres plat_app=X/postgres
```

Os quatro guardas e a integridade da 006, como `plat_app` com contexto do inquilino `demo` (script de conferência,
tudo em transação com `ROLLBACK`):

```
guarda 1 · plat_app liga o interruptor               barrado permission denied for table ambiente
guarda 2 · inquilino que não é de demonstração       barrado jobs_semear_demo só semeia inquilino de demonstração (demo, demo2, zt-%), não plataforma
guarda 3 · estado rodando                            barrado jobs_semear_demo só cria job em estado final (concluido, falhou, cancelado), não rodando
guarda 3 · estado pendente                           barrado jobs_semear_demo só cria job em estado final (concluido, falhou, cancelado), não pendente
guarda 4 · 5001 por chamada                          barrado jobs_semear_demo aceita de 1 a 5000 por chamada, recebeu 5001
006 · INSERT concluído com o GUC ligado              barrado job nasce pendente e sem resultado
006 · UPDATE de estado com o GUC ligado              barrado permission denied for table job
006 · plat_app executa via_worker_ligar              barrado permission denied for function via_worker_ligar
semeadura legítima (rollback depois)                 PASSOU  {'n': 3}
```

A linha "006 · INSERT concluído com o GUC ligado" é a que importa para o adversário: `plat.via_worker` é um GUC de
prefixo livre e **qualquer role consegue chamar `set_config('plat.via_worker','sim',true)`** (medido). Isso não
serve de nada porque `plat_app` não tem `UPDATE` em `plat.job` (camada 2 da 006) e o ramo de INSERT do gatilho não
tem escape nenhum. Fica registrado como o que a 006 **não** prova: o GUC sozinho não é a trava; a trava é o
`REVOKE UPDATE` mais o ramo de INSERT.

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/python -m pytest tests/api/jobs/test_jobs_semente_demo.py -q
.....                                                                    [100%]        (5 passaram)

$ timeout 300 flock .../.pytest.lock venv/bin/python -m pytest "tests/e2e/test_tarefas.py::test_primeira_pintura_com_mil_jobs" -q
.                                                                        [100%]        (era o e2e que reprovava)
```

Arquivos: `db/migracoes/014_jobs_semear_demo.sql` (novo) · `install.sh` (passo que escreve `plat.ambiente`, ao lado
do bloco de resíduo `zt-*`) · `.env.exemplo` (`PLAT_SEMENTE_DEMO`) · `tests/e2e/test_tarefas.py` (semeadura e
limpeza) · `tests/api/jobs/test_jobs_semente_demo.py` (novo, 5 testes).

---

## Conserto 2 — perfil `visualizador` lê a fila (privilégio `jobs.ver`, migração 015)

### O que fiz

`jobs.ver` entrou no vocabulário fechado (não administrativo, nos **quatro** perfis), o vocabulário passou de 46
para 47, e as rotas da fila foram separadas em duas dependências:

| exigem `jobs.ver` (leitura, 4 perfis) | exigem `jobs.executar` (execução, campo/editor/admin) |
|---|---|
| `GET /api/jobs` · `/api/jobs/resumo` · `/api/jobs/tipos` · `/api/jobs/{id}` · `/api/jobs/{id}/log` · `/api/jobs/{id}/eventos` · `GET /api/agendas` · `GET /api/agendas/{id}` | `POST /api/jobs` · `.../cancelar` · `.../repetir` · `POST/PUT/DELETE /api/agendas` · `pausar` · `retomar` · `rodar-agora` |

O que **não** mudou, de propósito: o **filtro de dono** do ADR 0003 seção 9 (quem não tem `jobs.gerir_todos` vê só
os próprios jobs) e o **escopo de token** (continua `jobs:executar`, não há escopo novo; a diferença é o privilégio
exigido no dono). O visualizador, que não cria job, lê portanto uma lista vazia — em modo só-leitura, com 200 em
todas as rotas e sem erro de console. A 015 também dá `jobs.ver` aos papéis personalizados que já tinham
`jobs.executar`, para que nenhum papel existente perca a leitura ao mudar o requisito das rotas.

Documentação: linha nova na tabela do ADR 0002 seção 3.2 com **"alterado em T2: motivo"** (nas duas linhas de
`jobs`), contagem corrigida para 47, nota no escopo `jobs:executar`, e um parágrafo "Alterado em T2" no começo da
seção 9 do ADR 0003.

### O que o frontend de jobs precisou mudar (feito neste commit, `web/js/jobs/`)

Com o 403 resolvido a tela já não erra, mas ela ainda oferecia botões que o servidor recusaria. Três mudanças
pequenas, todas por **privilégio** e não por perfil (ADR 0002 seção 3: "a tela pergunta privilégio, nunca perfil"):

- `util.js`: função nova `podeExecutar()`, lendo `privilegios` do usuário na loja da base (`js/base/estado.js`).
  Sem usuário na loja (rota `/api/eu` ausente) devolve `true`: quem decide de verdade é o servidor;
- `lista.js`: `celulaAcoes()` mostra só "abrir" quando não pode executar (sem "cancelar", sem "repetir");
- `detalhe.js`: os botões `#detalhe-cancelar` e `#detalhe-repetir` ficam escondidos no mesmo caso;
- `agendas.js`: a seção de agendas passa a ser escondida por `!podeExecutar()` em vez de
  `perfil not in ('admin','editor')` — **efeito colateral bom**: o perfil `campo`, que tem `jobs.executar` e podia
  criar agenda pela API, deixa de ficar sem a seção.

Nada mais do front precisa mudar por causa deste conserto.

### Evidência

```
$ bash db/migrar.sh
aplicada   015_privilegio_jobs_ver (43 ms)
migracoes: aplicadas 1 · reaplicadas 0 · iguais 13 · pendentes 0

$ sudo -u postgres psql -d iagro_sat -Atc "SELECT p.nome, p.administrativo, string_agg(pp.perfil, ',' ORDER BY pp.perfil) ..."
jobs.executar    | f | admin,campo,editor
jobs.gerir_todos | t | admin
jobs.ver         | f | admin,campo,editor,visualizador
$ ... "SELECT count(*) FROM plat.privilegio"
47
```

A tela, pelo navegador real, com cookie de um `visualizador` do inquilino `demo` — **antes** do reinício da API
(código velho no processo) e **depois**, mesmo script:

```
ANTES (20:18:2x Z)                                    DEPOIS (20:18:4x Z)
RESP 200 .../api/eu                                   RESP 200 .../api/eu
RESP 403 .../api/jobs/tipos                           RESP 200 .../api/jobs/tipos
CONSOLE error Failed to load resource: ... 403        RESP 200 .../api/jobs?limite=50&deslocamento=0&...
RESP 403 .../api/jobs/resumo                          RESP 200 .../api/jobs/resumo
CONSOLE error Failed to load resource: ... 403        PRONTO ok
RESP 403 .../api/jobs?limite=50&...                   lista-total: '0 tarefas'
CONSOLE error Failed to load resource: ... 403        aviso: ''
PRONTO ok                                             lista-aviso: ''
lista-total: '…'                                      corpo: 'nenhuma tarefa com estes filtros'
aviso: 'não foi possível carregar os tipos de tarefa (403): a operação exige o privilégio jobs.executar'
lista-aviso: 'não foi possível carregar a lista (403): a operação exige o privilégio jobs.executar'
corpo: ''
```

```
$ flock .../.pytest.lock venv/bin/python -m pytest tests/api/jobs/test_jobs_perfil_leitura.py -q
......                                                                   [100%]        (6 passaram)

$ timeout 400 flock .../.pytest.lock venv/bin/python -m pytest \
    "tests/e2e/test_tarefas.py::test_visualizador_le_a_tela_em_modo_so_leitura" -q
.                                                                        [100%]
```

O e2e novo prova, no chromium contra a URL pública: a tela pinta, `#lista-total` tem número (não "…"),
**0 resposta 403 em `/api/`**, `/api/jobs` + `/api/jobs/resumo` + `/api/jobs/tipos` em 200, **0 botão
`.acao-cancelar` e 0 `.acao-repetir`**, `#agendas` oculto, `#f-quem` oculto, e `conferir_limpo(page)` (0 erro de
console, 0 resposta ≥ 400 fora das toleradas). Captura em
`tests/e2e/capturas/L0-05-jobs_visualizador.png`.

Arquivos: `db/migracoes/015_privilegio_jobs_ver.sql` (novo) · `app/auth/privilegios.py` · `app/jobs/contexto.py`
(`PRIVILEGIO_VER`, `dependencia_jobs_ver`) · `app/jobs/rotas.py` (`AUTH_VER`, `XV`) ·
`tests/api/test_privilegios_declarados.py` (46 → 47) · `tests/api/jobs/test_jobs_perfil_leitura.py` (novo) ·
`tests/jobs_sessao.py` (`sessao_de_usuario`) · `tests/e2e/test_tarefas.py` · `web/js/jobs/{util,lista,detalhe,agendas}.js`
· `docs/adr/0002-identidade-e-acesso.md` · `docs/adr/0003-fila-de-jobs.md`. O `docs/openapi.json` com `jobs.ver`
entrou pela trilha do catálogo (`36317a7`), que rodou `make openapi` depois da minha edição — conferido: 8
ocorrências de `jobs.ver` no arquivo comitado e `test_openapi_comitado_esta_contido_na_aplicacao` passa.

---

## Conserto 3 — `Cache-Control` com uma origem só: a **aplicação**

### A medição que decide

```
$ for u in /saude /api/versao /tarefas; do curl -sS -o /dev/null -D - "https://plat.iagrointel.com$u" | grep -i '^cache-control'; done
/saude       cache-control: no-store                    <- da aplicação
             Cache-Control: no-store, must-revalidate   <- do nginx
/api/versao  Cache-Control: no-store, must-revalidate   <- só do nginx (a rota não declara)
/tarefas     cache-control: no-store
             Cache-Control: no-store, must-revalidate
```

Não é só o SSE: **toda rota em que a aplicação já declarava o cabeçalho saía com dois.**

### Escolha e justificativa

Origem única = **a aplicação**, nas rotas proxiadas; o **nginx** continua sendo a origem em `location /static/`,
onde o corpo é dele. Três razões, em ordem de peso:

1. `add_header` do nginx **acrescenta, nunca substitui**, e o modelo usava `always`. Uma rota que precisa de cache
   não teria como se opor: `app/catalogo/miniatura.py` devolve `Cache-Control: private, max-age=300` (e
   `private, max-age=60` no link compartilhado de `rotas_compartilhamento.py`) — com a linha no nginx, essas
   respostas sairiam com `private, max-age=300` **e** `no-store, must-revalidate`, contraditórias. Hoje ainda não
   há miniatura no banco (`0 itens com miniatura_sha256`), então o defeito ainda não é observável em produção; o
   mecanismo, sim, está medido acima. Isso vale em dobro para o roteiro do produto: tile de imagem e de vetor
   (L1/L2) só faz sentido com cache, e um `no-store` global no `location /` inviabiliza declarar isso na rota.
2. Só a aplicação conhece a semântica do recurso; o nginx trata todas as respostas proxiadas como uma coisa só.
3. A suíte de API bate no uvicorn direto (`TestClient`) e vários testes já exigiam `no-store` ali
   (`test_saude.py`, `test_paginas.py`, `test_jobs_sse.py`, `test_compartilhamento.py`): a aplicação já era a
   origem de fato para metade do produto.

Para que nada perdesse o cabeçalho (rotas que não declaram nada, como `/api/versao`), o piso passou a ser posto
pelo middleware de requisição: `resposta.headers.setdefault("Cache-Control", "no-store, must-revalidate")` — a
rota que declara o seu vence, porque `setdefault` não sobrescreve.

### Evidência

```
$ (deploy/nginx.conf: removida a linha add_header Cache-Control das 3 location proxiadas; mantida em /static/)
$ sudo bash <mesma função escrever_nginx do install.sh>       (20:22:05Z)
bloco 443 reescrito, preservando 5 linhas do certbot
nginx: configuration file /etc/nginx/nginx.conf test is successful
nginx recarregado

$ for u in /saude /api/versao /tarefas /static/app.js; do ... grep -ci '^cache-control' ...; done
/saude          1  cache-control: no-store
/api/versao     1  cache-control: no-store, must-revalidate      <- piso do middleware
/tarefas        1  cache-control: no-store
/static/app.js  1  Cache-Control: no-store, no-cache, must-revalidate, max-age=0   <- nginx, origem do corpo

$ (SSE pela URL pública, job prova.progresso de 6 s)
cache-control (lista): ['no-store'] · n = 1
content-type: text/event-stream; charset=utf-8
eventos vistos: 15 em 6.1 s          # o canal continua vivo e sem buffer

$ flock .../.pytest.lock venv/bin/python -m pytest tests/api/test_cabecalhos.py -q
.........................................                                [100%]     (41 passaram)
```

**Efeito colateral que vale registrar:** ao republicar o bloco do nginx a partir de `deploy/nginx.conf` (mesma
função `escrever_nginx` do `install.sh`, para não rodar o instalador inteiro — ele reinicia o `plat-worker`), o
`Referrer-Policy` que a **trilha A** tinha comitado em `abbb03d` e que nunca chegara ao arquivo vivo (o arquivo em
`sites-enabled` era de 17:15, o commit é de 17:23) entrou junto: `grep -c Referrer-Policy` no arquivo vivo foi de
**1 para 5**, e os **7 `test_referrer_policy_em_toda_rota`** que reprovavam desde o `make check` das 17:52 passaram
a passar. Não era do meu escopo; foi consequência de publicar o repositório como está.

Arquivos: `deploy/nginx.conf` · `app/auth/middleware.py` · `tests/api/test_cabecalhos.py` (2 testes novos, 8 casos)
· `docs/adr/0001-fundacao.md` (bloco do nginx + parágrafo "Alterado em T2") · `docs/adr/0002-identidade-e-acesso.md`
(a linha que dizia "(nginx)").

---

## Riscos

- **`PLAT_SEMENTE_DEMO=sim` no `.env` deste servidor.** O e2e dos 1.000 jobs precisa da semeadura, e este host roda
  a suíte com `PLAT_AMBIENTE=producao` (é o servidor de análise/beta que também é a máquina de construção). Optei
  por **não** trocar o ambiente para `dev` — isso ligaria os atalhos de teste de sessão (`PLAT_TESTE_BLOQUEIO_MIN`,
  `PLAT_TESTE_OCIOSA_S`, `PLAT_RELOGIO_TESTE`) num host que serve gente. O interruptor é o mínimo: função de nome
  explícito, `EXECUTE` só para `plat_app`, só inquilino de demonstração, só job terminal, marca no `parametros`.
  **Numa instalação de cliente a chave não existe e a função recusa.** Se o gerente ou o adversário preferir, basta
  tirar a linha do `.env` e rodar o `install.sh`: o e2e passa a **pular** com a razão escrita, em vez de falhar.
- **O visualizador vê uma lista vazia.** É o filtro de dono do ADR 0003 seção 9, que eu não mexi. Se o produto
  quiser que ele veja os jobs do inquilino, isso é `jobs.gerir_todos` (administrativo) ou uma regra nova — decisão
  de produto, não de implementação. Registrado aqui para o gerente, não como pendência minha.
- **`plat.via_worker` é definível por qualquer role.** Já explicado acima; inerte, mas o adversário vai testar.
- **Duas reescritas do bloco do nginx no mesmo minuto** (20:20:49 e 20:22:05): a primeira foi um `sed` cirúrgico no
  arquivo vivo, a segunda republicou o arquivo inteiro a partir do repositório. Cópia do arquivo anterior em
  `/root/plat.iagrointel.com.bak-20260905-2020`.

## Pendências (não são deste papel)

- `docs/PARIDADE.md`, `MANUAL.md` e `CHANGELOG.md` não citam ainda `jobs.ver` nem o modo só-leitura da tela: é do
  **cronista** (P9).
- A **contagem de privilégios** aparece em material do cronista e no `laco/PAINEL.md` como 46 — agora são 47.
- A trilha do catálogo estava com `pytest tests/api/catalogo tests/unit` sob o mesmo `flock` durante esta rodada;
  o `make check` inteiro sai no ponto seguinte.

## Para o próximo papel (testador e adversário)

Ataques que eu tentaria, na ordem:

1. `plat_app` ligando o interruptor por outro caminho (`ALTER TABLE`, `TRUNCATE`, `COPY`, função de terceiro que
   escreva em `plat.ambiente`) e depois semeando em inquilino que não é de demonstração;
2. `jobs_semear_demo` com `p_parametros` contendo `semente_demo: false` (a função sobrescreve com `|| {"semente_demo": true}`
   — conferir que a marca não some) e com `p_tipo` de um tipo **pesado**, para ver se algum job seria pego;
3. token de serviço com escopo `jobs:executar` cujo dono é `visualizador`: tem de LER (200) e não EXECUTAR (403);
4. papel personalizado com `jobs.executar` e **sem** `jobs.ver` (criado depois da 015): as rotas de leitura devolvem
   403 — é o comportamento declarado, mas vale confirmar que a interface do papel mostra os dois privilégios juntos;
5. a tela com um usuário que tem `jobs.ver` e `jobs.gerir_todos` e não tem `jobs.executar`: vê os jobs do inquilino
   inteiro e nenhum botão de execução;
6. `Cache-Control` em rota de erro (401, 403, 404, 422, 500) e em resposta com `Content-Encoding: gzip`, pela URL
   pública: um cabeçalho só, sempre;
7. matar o `plat-api` no meio de um SSE e conferir que o cabeçalho volta igual no reconecta.

---

## Suíte depois dos três consertos (sob `flock`, 20:36–20:41Z)

```
$ make lint
venv/bin/ruff check app tests
All checks passed!                                                   (LINT_EXIT=0)

$ make sem-marcador
db/migracoes/016_catalogo_apagar_usuario.sql:1: -- 016_catalogo_apagar_usuario ... depois de transferir TODOS os itens
make: *** [Makefile:16: sem-marcador] Error 1                        (a palavra "TODOS" casa com o regex de TODO;
                                                                      arquivo da trilha do catálogo, não meu — os meus
                                                                      caminhos passam o mesmo grep com rc=1)

$ timeout 1500 flock laco/.pytest.lock venv/bin/python -m pytest tests/api/jobs tests/api/test_usuarios.py \
    tests/api/test_funcoes_seguras.py tests/api/test_privilegios_declarados.py tests/api/test_cabecalhos.py \
    tests/api/test_saude.py tests/api/test_paginas.py tests/api/test_tokens.py tests/unit \
    -m "not lento" -q -p no:randomly --tb=line --no-header
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
................................................                         [100%]
EXIT=0                                                               (336 testes, 0 falha)
```

Antes disso, a varredura `pytest tests -m "not lento"` inteira (20:29–20:34Z) pegou **duas reprovações minhas**,
já consertadas no commit `7cf33c2`: `test_usuarios::test_privilegios_e_papeis` e
`test_funcoes_seguras::test_privilegios_de_e_tem_respeitam_rls` tinham o número **46** fixo além do
`test_privilegios_declarados` que eu já havia corrigido (`assert (47 == 46)`). Fica a lição para quem acrescentar
privilégio depois: **são três lugares com o número, não um** (`grep -rn "== 46" tests/` agora não devolve nada).

O que reprovou na mesma varredura e **não é meu**: 14 de `tests/api/catalogo/*` e 3 de `test_cruzado` sobre rotas
do catálogo (trilha L0-03, que estava comitando durante a rodada), e
`test_jobs_rls::test_sem_contexto_zero_linhas_e_worker_inacessivel` por resíduo em `plat_trabalho.passos` de um job
que ainda rodava quando a suíte passou por ali — conferido logo depois: `SELECT count(*) FROM plat_trabalho.passos`
→ **0**, e o teste passa na rodada dirigida acima. É a mesma interferência de árvore compartilhada que o testador
já registrou.

Os testes marcados `lento` da fila (job de 5 min, reinício, kill -9) **não** foram rodados nesta correção **de
propósito**: `tests/api/jobs/test_jobs_reinicio.py` faz `systemctl restart plat-worker`, e o adversário está
medindo reinícios do worker. Uma primeira tentativa minha rodou sem `-m "not lento"` e foi interrompida por PID
(`kill` nos dois processos do `pytest`, nunca `pkill -f uvicorn`) **antes** de chegar a esse arquivo:
`systemctl show plat-worker -p ActiveEnterTimestamp` continuou em **20:15:50Z**, que é anterior a todo este
trabalho, e `NRestarts=0`. Nenhuma linha do caminho de execução do worker foi tocada por estes três consertos.

Conferência final no navegador, depois do último commit (20:44Z), com a árvore como está:

```
$ timeout 500 flock laco/.pytest.lock venv/bin/python -m pytest \
    "tests/e2e/test_tarefas.py::test_primeira_pintura_com_mil_jobs" \
    "tests/e2e/test_tarefas.py::test_visualizador_le_a_tela_em_modo_so_leitura" \
    "tests/e2e/test_tarefas.py::test_agendas_criar_pausar_retomar_apagar" -q -p no:randomly
...                                                                      [100%]
```

Ou seja: os 1.000 jobs voltam a pintar (semeadura pela função de demonstração), o `visualizador` lê a tela em modo
só-leitura sem erro de console, e o admin continua criando, pausando, retomando e apagando agenda — o gate por
privilégio no front não quebrou quem executa.

Commits desta correção: `7037009` · `ea77246` · `a496cdd` · `4053e3c` · `7cf33c2`.
