# T2 · trilha B · L0-05-jobs · 20_arquitetura (arquiteto)

## Objetivo

Decidir, por medição e documento, como a plataforma executa trabalho longo (ingestão, COG, geoprocessamento, motor
multicritério, fluxos, IA no GPU box, exportação, backup, verificação de frescor) e fixar o contrato que backend (30)
e frontend (31) constroem em paralelo: fila, modelo `plat.job`, worker `plat-worker` (:8153), progresso em tempo
real, cancelamento, sobrevivência a reinício, agendamento, cotas, tela "Tarefas", testes. Entregável:
`/home/dev/plataforma/enterprise/docs/adr/0003-fila-de-jobs.md` (aceito) e este handoff.

Item copiado do estado: hipótese "fila de trabalho só com Postgres (Procrastinate ou própria) para ingestão,
geoprocessamento, COG, IA: progresso, cancelamento, log por job, retentativa, visível na tela 'Tarefas'"; portão
"job de 5 min mostra progresso em tempo real, pode ser cancelado, sobrevive a reinício do serviço (retoma ou marca
falha, nunca some); 1 worker por padrão com limite de RAM declarado; tela Tarefas por inquilino; teste automatizado";
refutação "adversário mata o worker no meio de um job e reinicia: job não pode aparecer como concluído".

## O que fiz

1. Regra de conceito do dono: esperei `laco/decomposicao/L0_CONCEITO.md`. Ele apareceu às 13:25 UTC (o laço de
   espera começou às 13:21; nenhuma ausência a registrar). Li D1, D11, **D12** (fila própria; Procrastinate como
   reserva), D14, D16, D18, D19, D20 e o `L3L6_CONCEITO.md` A8/B9. Li também `L0.json` (itens L0-05-a..d e os que
   dependem da fila: L0-04-a/g/h, L0-06-a/d, L0-10, L0-11, L0-12, L0-14), `L5.json` (L5-02-a..f, L5-16, L5-30) e
   `L3L6.json` (L3-01-c, L3-10, L3-12, L3-16, L6-01-h, L6-02-k/n) para enumerar os tipos de job que as outras linhas
   vão precisar: ingestão vetorial e raster→COG (subprocesso GDAL, memória alta), geoprocessamento e extração de
   fatores (SQL longo + numpy), traçado de rede (custo mínimo, RAM 2,7 GB por worker no motor de LT), IA no GPU box
   (executor remoto), fluxos (grafo de jobs com proveniência por nó), agendados (cron por inquilino, tetos), exportação
   (arquivo no bucket com validade), backup (periódico da plataforma), verificação de frescor (semanal). O modelo do
   ADR cobre todos sem coluna nova: `tipo` + `parametros jsonb` + `pesado/memoria_mb/timeout_s/executor` + `chave` +
   `agenda_id` + `resultado jsonb` + `proveniencia jsonb` (D19: linha que precisar de coluna nova em `job` está errada).
2. Medi o Procrastinate instalando-o **só na venv do repositório** (`./venv/bin/pip`, offline a partir do wheel baixado)
   e desinstalei depois; a venv voltou ao tamanho exato de antes (52.690.427 bytes) e `git status` está limpo.
3. Medi a fila própria com a role `plat_app`: NOTIFY, SKIP LOCKED, fork por job, RLIMIT, PDEATHSIG, SIGTERM/SIGKILL,
   SSE com 1 e 100 clientes, croniter com fuso. Scripts guardados em `laco/handoffs/T2/L0-05-jobs/medicoes/`
   (`med_notify.py`, `sse_proto.py` + `sse_cliente.py`, `rlimit.py`); o testador pode reexecutar.
4. Escrevi o ADR 0003 (13 seções: decisão, modelo de dado, registro por decorador, worker e unidade, SSE, cancelamento
   e morte, agendamento, gancho GPU, contrato de API, wireframe da tela, configuração, testes, custo de mudar).
5. Varredura de marcadores (`tests/marcadores.regex`) no ADR: 0 ocorrências. Nenhum nome de cliente/parceiro.

## Evidência (comando + saída literal)

Procrastinate (05/09/2026, `/home/dev/plataforma/enterprise`):

```
$ ./venv/bin/pip index versions procrastinate
procrastinate (3.9.0)
$ ./venv/bin/pip download procrastinate==3.9.0 -d <scratch>/pkg    # + unzip -p ... METADATA
Name: procrastinate / Version: 3.9.0 / Classifier: License :: OSI Approved :: MIT License / Requires-Python: >=3.10
Requires-Dist: asgiref, attrs, croniter, packaging, psycopg[pool], python-dateutil, typing-extensions
-rw-rw-r-- 1 dev dev 153597 procrastinate-3.9.0-py3-none-any.whl   (+ psycopg 213598, psycopg_pool 40023, croniter 46677, asgiref 25478)
$ du -sb venv   (antes / depois de pip install --no-index --find-links pkg procrastinate==3.9.0)
antes 52690427 depois 56274465
procrastinate 1552 kB · psycopg 2048 kB · psycopg_pool 344 kB · croniter 548 kB · asgiref 188 kB
$ grep -n "SKIP LOCKED\|pg_notify\|abort_requested\|heartbeat" venv/.../procrastinate/sql/schema.sql
252:            FOR UPDATE OF jobs SKIP LOCKED
412:	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
413:	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
76:    abort_requested boolean DEFAULT false NOT NULL,
542:CREATE FUNCTION procrastinate_update_heartbeat_v1(worker_id bigint)
$ grep -n "sync_to_async\|update_heartbeat_interval\|stalled_worker_timeout" venv/.../procrastinate/worker.py venv/.../utils.py
worker.py:48:        update_heartbeat_interval: float = 10.0,
worker.py:49:        stalled_worker_timeout: float = 30.0,
worker.py:311:                    task_result = await utils.sync_to_async(
utils.py:110:    return await sync.sync_to_async(func, thread_sensitive=False)(*args, **kwargs)
$ ls venv/.../procrastinate/sql/migrations | wc -l   → 37 arquivos .sql
$ PYTHONNOUSERSITE=1 PYTHONPATH=. ./venv/bin/python -c "<rss antes/depois dos imports>"
rss_kb_python_puro=10592
rss_kb_com_app_db_psycopg2=25920
rss_kb_mais_procrastinate=38144
rss_kb_mais_fastapi_app_main=53404
$ ./venv/bin/pip uninstall -y procrastinate psycopg psycopg-pool asgiref croniter; du -sb venv
52690427
```

Fila própria (`medicoes/med_notify.py`, como `plat_app` pelo `PLAT_DSN` do `.env`):

```
notify_latencia_ms mediana=0.090 p95=0.122 max=2.907 n=200
notify_payload_7999=ok
notify_payload_8001=erro: payload string too long
skip_locked_fetch_ms mediana=0.282 p95=0.339 n=200 linhas=10000
```

Processo filho (`medicoes/rlimit.py` e trechos inline):

```
filho_exitcode=1 tempo_s=0.01 (esperado: !=0 por MemoryError)          # RLIMIT_AS 512 MiB, alocação de 1 GiB
apos_SIGTERM_ignorado alive=True em 2.01s
apos_SIGKILL alive=False exit=-9 em 0.001s
pdeathsig: pai morto por SIGKILL -> filho vivo=False (esperado False)
fork_conexao_exit_ms mediana=14.7 p95=16.6 -> jobs_vazios_por_min≈4075 (1 processo)
# RLIMIT × bibliotecas científicas (12 threads OpenBLAS padrão):
OpenBLAS blas_thread_init: pthread_create failed for thread 6 of 12: Resource temporarily unavailable   (RLIMIT_AS=256 e 512 travaram; mortos)
  ok RLIMIT_AS=1024MB modulos=['psycopg2', 'numpy', 'rasterio', 'shapely', 'pyproj'] rss=137MB vsz=716MB
  FALHA RLIMIT_DATA=512MB ...: MemoryError: Unable to allocate 64.0 MiB
# com OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 no filho:
  FALHA RLIMIT_AS=256MB: MemoryError: Unable to allocate 64.0 MiB
  ok RLIMIT_AS=512MB import+64MB rss=137MB vsz=276MB ogrinfo_rc=0 GDAL 3.8.4
  ok RLIMIT_DATA=256MB import+64MB rss=137MB vsz=276MB ogrinfo_rc=0 GDAL 3.8.4
  ok RLIMIT_DATA=512MB import+64MB rss=137MB vsz=276MB ogrinfo_rc=0 GDAL 3.8.4
  ok RLIMIT_DATA=1024MB import+64MB rss=137MB vsz=276MB ogrinfo_rc=0 GDAL 3.8.4
```

SSE (`medicoes/sse_proto.py` em `127.0.0.1:18159`, porta de rascunho fora da faixa 8150-8159; `sse_cliente.py`):

```
$ ./venv/bin/python sse_cliente.py 1 30
clientes=1 eventos=30 entregas=30 latencia_ms mediana=0.94 p95=1.15 max=3.25
$ ./venv/bin/python sse_cliente.py 100 20
clientes=100 eventos=20 entregas=1900 latencia_ms mediana=5.41 p95=7.13 max=22.29
rss_kb_uvicorn_100_sse=VmHWM:	   58376 kB
```

Cron, fuso e dependências:

```
croniter_sp: ['2026-09-06T02:00:00-03:00', '2026-09-06T02:15:00-03:00']      # */15 2 * * * a partir de 05/09 13:30 America/Sao_Paulo
croniter_dst_ny: 2026-03-08T03:00:00-04:00                                     # 30 2 * * * no dia da troca de horário
croniter_invalida: recusou: CroniterBadCronError                               # 61 * * * *
$ unzip -p croniter-6.2.4-py3-none-any.whl 'croniter-6.2.4.dist-info/METADATA' | grep -E "^(Project-URL|License-Expression)"
Project-URL: Homepage, https://github.com/pallets-eco/croniter
License-Expression: MIT
$ dpkg -s python3-dateutil python3-six | grep -E "^(Package|Version)"
Package: python3-six
Version: 1.16.0-4                                                              # python3-dateutil NÃO é dpkg
```

Banco, systemd e GPU box:

```
$ sudo -u postgres psql -d iagro_sat -tAc "..."
PostgreSQL 16.13 · max_connections 100 · pg_stat_activity 15 · pg_cron|1.6 · pgcrypto|1.3
idle_in_transaction_session_timeout|60000 · shared_preload_libraries|timescaledb,pg_cron,pgaudit
cron.database_name|iagro_sat · SELECT count(*) FROM cron.job → 0
$ systemctl list-units 'plat-*' → plat-api.service active running (MemoryPeak=93908992, NRestarts=0)
$ systemctl --version → systemd 255 (255.4-1ubuntu8.17)
$ ssh gpu 'hostname; nvidia-smi ...; df -h /; which rsync sha256sum; python3 --version; free -g'
Ubuntu-2404-noble-amd64-base · NVIDIA RTX 4000 SFF Ada Generation, 20475 MiB · /dev/md2 1.7T 1.6T 16G 100% /
/usr/bin/rsync /usr/bin/sha256sum · Python 3.12.3 · RAM 62 GB, 29 disponíveis
$ free -g; df -h /        (13:44 UTC, fim do trabalho)
Mem: 23 total, 3 available · /dev/vda2 469G 451G 13G 98% /
```

Varredura do ADR:

```
$ grep -nI -E -f tests/marcadores.regex docs/adr/0003-fila-de-jobs.md ; echo $?
1          # nenhuma linha
$ git status --short → (vazio)   # o ADR é o único arquivo novo no repositório; ainda não comitado (gerente comita)
```

## Riscos

1. **Cookie e dependência de sessão são da trilha A** (L0-02), que ainda não escreveu handoff. Este ADR assume cookie
   `plat_sessao` (sha256 no banco, função `plat.auth_sessao` já existente na 002) e uma dependência FastAPI que devolve
   `Contexto` + `perfil` + `superadmin`. Para a trilha B não esperar, o backend entrega `app/jobs/contexto.py` com essa
   dependência mínima (só cookie) e uma constante `COOKIE_SESSAO`. No merge, se a trilha A publicou `app/auth.py` com
   `contexto_atual`, a trilha B troca **uma linha de importação** em `app/jobs/rotas.py` e apaga `contexto.py`.
2. **RAM**: 3 GB disponíveis agora; `plat-api` (MemoryMax 1G) + `plat-worker` (MemoryMax 2G) somam o que a máquina
   tem. O backend confere `free -g` antes do `install.sh` e o testador grava `MemoryPeak` das duas unidades. Se
   o adversário rodar job pesado e e2e ao mesmo tempo, o guardrail de "1 job pesado por vez" é o que segura.
3. **`RLIMIT_DATA` e bibliotecas**: medido com numpy/rasterio/shapely/pyproj/ogrinfo; não medido com DuckDB nem
   com PyTorch (só no GPU box). Tipo que falhar na importação sob o limite declara `memoria_mb` maior, nunca remove o
   limite.
4. **`idle_in_transaction_session_timeout = 60 s` no servidor**: a tarefa que abrir `ctx.db()` e ficar 60 s sem
   consulta (ex.: rodando `ogr2ogr` dentro do bloco) perde a conexão. Regra para toda tarefa: trabalho longo fora do
   bloco `with ctx.db()`; o `ContextoJob` documenta e o `prova.progresso` demonstra.
5. **Disco a 98 %**: `PLAT_JOBS_DIR` fica em `/` (`APP_DIR/var/jobs`); o expurgo apaga diretórios de jobs terminados.
   Nenhum job deste item escreve mais de alguns MB; L0-04/L1-01 medem `df` antes de aceitar upload.
6. **OpenAPI comitado** vai conflitar entre as trilhas: é gerado, nunca se resolve à mão (regra abaixo).
7. **SSE atrás de proxy**: `X-Accel-Buffering: no` cobre o nginx desta máquina (medido no protótipo só direto na
   porta; o testador mede pela URL pública). Se o domínio um dia passar por CDN com buffer, o front já cai para polling.

## Pendências

- Gerente: comitar `docs/adr/0003-fila-de-jobs.md`; fixar a ordem de merge A/B (proposta: B espera A em `app/main.py`,
  `install.sh`, `settings.py`, `requirements.txt`, `.env.exemplo`; os blocos de B estão listados abaixo com âncoras).
- Gerente: os testes `lento` de reinício e morte precisam de `sudo systemctl restart/kill plat-worker` e do
  `install.sh` como root; o backend não roda isso sozinho — o testador roda com evidência literal.
- Gerente: o `driver.sh` roda `python3 -m pytest` com o Python do sistema (pendência herdada do T1); com o worker
  isso não muda, mas `make check-rapido` passa a exigir a unidade `plat-worker` ativa para `test_saude` (campo `fila`).
- Decisão do dono: nenhuma nova. `MemoryMax` do worker (2G) e cotas padrão (2 simultâneos, 1.000/dia, 50 agendas) são
  do ADR e mudam por `.env`/`tenant.config`, sem decisão dele.

## Para o próximo papel

Contrato fixado no ADR 0003 seções 2 (esquema), 3 (decorador e `ContextoJob`), 4.2 (funções do worker), 5 (SSE), 9
(rotas e JSON), 10 (tela), 11 (`.env`), 12 (testes). Backend (30) e frontend (31) rodam **em paralelo**; o frontend
codifica contra o JSON da seção 9 e só o e2e (40) exige os dois juntos. Nada de marcador proibido; nada de nome de
cliente; português nos identificadores; ADR 0001 continua valendo (pool, RLS, migração imutável, sem `?v=`).

### 30 · backend — arquivo por arquivo

1. `requirements.txt` — acrescentar ao fim, sob o comentário `# jobs (app/jobs importa croniter)`:
   `croniter==6.2.4`, `python-dateutil==2.9.0.post0`, `six==1.17.0`. Instalar com `PYTHONNOUSERSITE=1 venv/bin/pip
   install -r requirements.txt`. `tests/unit/test_dependencias.py` já reprova linha sem `==`.
2. `db/migracoes/004_jobs.sql` — idempotente, sem BEGIN/COMMIT: tabelas `plat.job`, `plat.job_log`, `plat.worker`,
   `plat.agenda` e índices (ADR 2.1, DDL literal); `ENABLE ROW LEVEL SECURITY` + políticas `p_job`, `p_job_log`,
   `p_agenda` (`FOR ALL TO plat_app USING (tenant_id = plat.tenant_atual()) WITH CHECK (...)`, `DROP POLICY IF EXISTS`
   antes); `REVOKE ALL ON plat.worker FROM plat_app`; gatilhos `job_estado_final_imutavel`, `job_notificar`,
   `job_log_notificar` (ADR 2.3; funções `CREATE OR REPLACE`, gatilhos com `DROP TRIGGER IF EXISTS`); funções
   `SECURITY DEFINER SET search_path = plat, public` da seção 4.2 com `REVOKE EXECUTE ... FROM PUBLIC; GRANT EXECUTE ...
   TO plat_app` em cada uma; `plat.cota_jobs_simultaneos(int)`; inquilino técnico
   `INSERT INTO plat.tenant(slug, nome, ativo) VALUES ('plataforma', 'Plataforma (periódicos)', false) ON CONFLICT (slug)
   DO NOTHING`. Numeração: **004 é da trilha B**; a trilha A usa 003 e, se precisar de mais uma, 005 (nunca 004).
3. `app/jobs/__init__.py` — vazio.
4. `app/jobs/registro.py` — `Tarefa` (dataclass congelada com os campos do decorador da seção 3.1 + `threads_blas: int
   = 1`, `perfil_minimo: str = 'editor'`, `ferramentas: tuple[str, ...] = ()`), `@tarefa(...)`, `REGISTRO: dict[str,
   Tarefa]`, exceções `Cancelado`, `FalhaDefinitiva`, validações na importação: nome único e no padrão `^[a-z][a-z0-9_]*
   (\.[a-z][a-z0-9_]*)+$`, `128 ≤ memoria_mb ≤ settings.PLAT_WORKER_MEMORIA_MB` (pesado pode ir até o teto; leve até
   1024), `timeout_s ≥ 1`, `executor='gpu'` só com `PLAT_GPU_SSH` (mensagem nomeia a chave), `executor='gpu'` obriga
   `pesado=True`; `esquema_parametros(tarefa) -> dict` (`modelo.model_json_schema()`).
5. `app/jobs/contexto_job.py` — `ContextoJob` da seção 3.2: `progresso()` faz `UPDATE plat.job SET progresso, mensagem
   = left(%s, 200), heartbeat_em = now() WHERE id = %s RETURNING cancelar_solicitado` no máximo 1×/s (guarda o último
   instante; chamadas mais frequentes só atualizam memória e devolvem a última flag lida) e levanta `Cancelado`;
   `log()` insere em `job_log` (teto 10.000 linhas: a partir daí 1 linha a cada 1.000 suprimidas; `linhas_log`
   incrementado por `UPDATE ... SET linhas_log = linhas_log + 1`); `entrada()`; `subprocesso()` com
   `preexec_fn` que herda o limite (já herdado pelo fork) e mata o neto em `Cancelado`; `db()` = `app.db.db(Contexto(
   tenant_id, usuario_id or 0, 'worker'))`.
6. `app/jobs/filho.py` — `executar(job: dict, pipe_w)`: `prctl(PR_SET_PDEATHSIG, SIGKILL)` via `ctypes`;
   `os.environ.update(OPENBLAS_NUM_THREADS=str(threads_blas), OMP_NUM_THREADS=..., MKL_NUM_THREADS=...)`;
   `resource.setrlimit(RLIMIT_DATA, memoria_mb·2^20)`; `app.db._pool = None`; `signal.signal(SIGTERM, ...)` levanta
   `Cancelado` na próxima checagem; cria `dir_trabalho`; monta `ContextoJob`; chama a função do tipo; escreve no pipe
   `{"estado", "resultado"|"erro", "traceback", "entradas"}`; códigos de saída 0/3/4/5/1 (ADR 4.1 e 4.3); `MemoryError`
   → 5 com `memória excedida (limite N MB)`; sempre `os._exit`.
7. `app/jobs/worker.py` — pai da seção 4.1 (`python -m app.jobs.worker`): conexão própria autocommit + `LISTEN
   plat_worker`; `worker_registrar`; ceifa imediata dos jobs com `worker = meu nome`; laço com `select()` de ≤ 1 s;
   `job_pegar(nome, pesado_ok)` com `pg_try_advisory_lock(hashtext('plat.job.pesado'))`; fork por job com pipe;
   heartbeat 10 s (devolve `cancelar_solicitado` → escalonamento 30 s SIGTERM / +10 s SIGKILL); `timeout_s` →
   SIGTERM/+10 s SIGKILL e `erro = 'tempo esgotado (timeout_s = N)'`; coleta do filho → `job_terminar` /
   `job_devolver(conta_tentativa, espera 2^tentativa)`; proveniência (seção 3.4; `git_sha` e `versao` de
   `app.versao`, `gdal` por `ogrinfo --version` uma vez na partida quando algum tipo declara `ferramentas=('gdal',)`);
   a cada 30 s `job_ceifar(60)`, `worker_ceifar(90)` e `agenda.tick()`; `SIGTERM` → devolve jobs (`conta_tentativa=
   false`), SIGTERM ao filho, espera 20 s, SIGKILL, `worker_desregistrar`, sai 0; thread `http.server` em
   `127.0.0.1:8153` com `GET /saude` (JSON da seção 4.6); log JSON pelo `app.log` (campos extra `job_id`, `tipo`,
   `tenant_id`, `pid_filho`). Relógio injetável: `PLAT_RELOGIO_TESTE` (ISO) substitui `now()` só no relógio da agenda
   e só quando `PLAT_AMBIENTE=dev`; em `producao` a variável é ignorada com aviso no log.
8. `app/jobs/agenda.py` — `validar_cron(expr, fuso)` (croniter + `zoneinfo`; intervalo mínimo 15 min medido pelas 3
   primeiras ocorrências), `proxima(expr, fuso, apos)`, `tick(con, agora)`: `agenda_vencidas()` → para cada,
   `agenda_enfileirar(id, programado_para = proxima_em, proxima_em = proxima(...))`, respeitando `cota_jobs_dia`
   (pula e grava linha no log da plataforma); `sincronizar_periodicos(con)` na partida do worker (upsert das linhas
   de `periodicos.py` no inquilino `plataforma`); atualização de `ultimo_estado`/`falhas_seguidas` quando um job com
   `agenda_id` termina (chamado pelo pai); 5 falhas → `ativa = false`.
9. `app/jobs/periodicos.py` — `PERIODICOS = [("expurgo diário", "30 3 * * *", "jobs.expurgo", {})]` e o tipo
   `jobs.expurgo` (`pesado=False`, `memoria_mb=256`, `timeout_s=1800`): apaga `job` terminado há > 90 dias, `job_log` >
   30 dias, diretórios em `PLAT_JOBS_DIR` sem job `rodando` e mais velhos que 7 dias; resultado com contagens.
10. `app/jobs/tipos_prova.py` — tipos de prova, todos `perfil_minimo='editor'`: `prova.progresso(duracao_s=300,
    passos=60, chave=None, pesado=False)` (cria `CREATE TABLE plat_trabalho.j_<id>` fora de transação longa, dorme
    `duracao_s/passos` por passo chamando `progresso()` e `log()`, apaga a tabela na limpeza inclusive em `Cancelado`,
    grava no resultado `{"passos": n, "marcador": "<uuid>"}` e insere o marcador numa tabela `plat_trabalho.marcadores`
    só no último passo — é o que prova "nunca concluído sem execução inteira"); `prova.memoria(mb=600)` com
    `memoria_mb=256`; `prova.falha(definitiva=False)`; `prova.ignora_cancelamento(duracao_s=120)` (laço sem checar a
    flag); `prova.pesado(duracao_s=20)` com `pesado=True`. Schema `plat_trabalho` criado na 004 com `GRANT CREATE ON
    SCHEMA plat_trabalho TO plat_app`.
11. `app/jobs/tipos.py` — importa `tipos_prova` e `periodicos` (e, no futuro, os módulos de tipos das outras linhas)
    e expõe `REGISTRO`.
12. `app/jobs/contexto.py` — `COOKIE_SESSAO = "plat_sessao"`; `Sessao(ctx: Contexto, perfil: str, superadmin: bool)`;
    dependência `sessao_atual(request) -> Sessao`: lê o cookie, `sha256`, `SELECT * FROM plat.auth_sessao(%s)`; ausente
    ou vencida → 401 no formato D18. (Risco 1: substituível por `app.auth.contexto_atual` da trilha A no merge.)
13. `app/jobs/servico.py` — regras de negócio chamadas pelas rotas (e pela CLI do L0-14): `criar(sessao, tipo,
    parametros, prioridade, agendado_para)` (valida tipo e parâmetros pelo modelo pydantic → 422 com `detalhe`; perfil
    mínimo → 403; `cota_jobs_dia` → 413; > 200 pendentes → 429; copia `pesado/memoria_mb/timeout_s/executor/
    max_tentativas` do registro; `INSERT` sob RLS), `listar(sessao, filtros)` (não-admin: `AND usuario_id =
    plat.usuario_atual()`), `obter`, `cancelar` (pendente → cancelado direto; rodando → `cancelar_solicitado = true,
    cancelado_por, cancelado_em`; final → 409), `repetir`, `log`, `resumo`, `agendas_*`. Erros: função
    `erro(status, codigo, mensagem, detalhe=None)` → `JSONResponse({erro, mensagem, detalhe, req_id})` com
    `req_id` de `request.state.req_id`.
14. `app/jobs/eventos.py` — thread `LISTEN plat_job` por processo, iniciado **preguiçosamente** na primeira conexão
    SSE (sem hook de startup: zero toque em `main.py`); fan-out por `job_id` em filas `asyncio` via
    `loop.call_soon_threadsafe`; gerador SSE da seção 5 (primeiro evento `estado` lido do banco, `Last-Event-ID`
    reenvia log, keepalive 15 s, fecha em estado final ou 30 min); limite 10 conexões por `usuario_id` por processo
    (429); reconexão do `LISTEN` com a mesma disciplina do pool (repete a preparação).
15. `app/jobs/rotas.py` — `router = APIRouter()` com todas as rotas da seção 9 (`/api/jobs*`, `/api/agendas*`) mais
    `GET /tarefas` e `GET /tarefas/{job_id}` (`FileResponse(WEB / "tarefas.html")`, `include_in_schema=False`,
    `Cache-Control: no-store`). Modelos pydantic de resposta em toda rota (regra do L0-12: rota sem esquema reprova).
16. `app/settings.py` — campos novos ao **fim** da dataclass e do `carregar()`: `PLAT_WORKER_URL`, `PLAT_WORKER_NOME`,
    `PLAT_WORKER_PROCESSOS` (int ≥ 1), `PLAT_WORKER_MEMORIA_MB` (int, padrão 1536), `PLAT_JOBS_DIR`,
    `PLAT_JOB_MAX_REINICIOS` (int, padrão 5), `PLAT_GPU_SSH`, `PLAT_GPU_DIR`, `PLAT_RELOGIO_TESTE`; `servicos()` ganha
    `"worker": self.PLAT_WORKER_URL`. (A trilha A acrescenta os dela: os dois blocos ficam ao fim, em ordem A depois B.)
17. `app/saude.py` — em `saude()`: `fila = plat.fila_estado()` (dentro de `try`, `erro` → `{"erro": true}`) como campo
    `fila` do JSON; `servicos` já inclui `worker` pelo `settings.servicos()`. Status HTTP inalterado.
18. `app/main.py` — **exatamente dois acréscimos**, para o merge com a trilha A ser trivial:
    ```python
    from app.jobs.rotas import router as rotas_jobs          # logo abaixo de: from app.saude import router as rotas_saude
    ...
    app.include_router(rotas_jobs)                           # logo abaixo de: app.include_router(rotas_saude)
    ```
    Nada mais: nenhum hook de startup, nenhuma rota de página em `main.py` (estão no router), nenhum middleware.
19. `deploy/plat-worker.service` — o modelo literal da seção 4.5 (`APP_DIR`/`APP_USER` substituídos pelo `install.sh`;
    sem `PORTA`: 8153 está no código e no `.env`).
20. `install.sh` — quatro acréscimos com âncora, nenhuma linha existente alterada:
    (a) no heredoc que cria o `.env` (passo d), **depois** de `PLAT_LOG_NIVEL=INFO`: `PLAT_WORKER_URL=http://127.0.0.1:8153`,
    `PLAT_WORKER_PROCESSOS=1`, `PLAT_WORKER_MEMORIA_MB=1536` (a trilha A acrescenta as linhas dela antes ou depois; são
    linhas independentes);
    (b) logo após o bloco `chmod 600 .env; chown ...` do passo d: `for chave in PLAT_WORKER_URL=http://127.0.0.1:8153
    PLAT_WORKER_PROCESSOS=1 PLAT_WORKER_MEMORIA_MB=1536; do grep -q "^${chave%%=*}=" .env || echo "$chave" >> .env; done`
    (instalação existente ganha as chaves);
    (c) **passo novo `h2`** entre `== h. systemd plat-api` (fim do bloco `systemctl --no-pager ... status $UNIDADE`) e
    `== i. nginx`:
    ```bash
    echo "== h2. systemd plat-worker"
    install -d -o "$APP_USER" -g "$APP_USER" var/jobs
    sed -e "s#APP_DIR#$APP_DIR#g" -e "s#APP_USER#$APP_USER#g" deploy/plat-worker.service > /etc/systemd/system/plat-worker.service
    systemctl daemon-reload
    systemctl enable -q plat-worker
    systemctl restart plat-worker
    for i in $(seq 1 30); do
      if curl -fsS -m 2 "http://127.0.0.1:8153/saude" >/dev/null 2>&1; then echo "/saude do worker respondeu 200 em ${i} s"; break; fi
      if [ "$i" -eq 30 ]; then echo "plat-worker não respondeu em 30 s:" >&2; journalctl -u plat-worker -n 30 --no-pager >&2; exit 1; fi
      sleep 1
    done
    systemctl --no-pager --lines=0 status plat-worker | sed -n '1,4p'
    ```
    (d) no passo j, antes da linha `echo "== instalado em ..."`: `curl -fsS -m 5 "https://$DOM/saude" | grep -q
    '"workers_vivos": *[1-9]' || { echo "/saude sem worker vivo" >&2; exit 4; }`.
    A trilha A edita o passo g (administradores/2FA) e possivelmente o `.env`; nenhum desses blocos coincide.
21. `.env.exemplo` — as mesmas chaves do item 16 ao fim, com valores de exemplo; `.gitignore` ganha `var/`.
22. `Makefile` — alvos novos ao fim: `worker: ; $(VENV)/python -m app.jobs.worker` (desenvolvimento) e
    `e2e-worker: ; $(VENV)/pytest -m lento tests/api/jobs` (os testes que reiniciam o serviço). Nenhum alvo existente
    muda.
23. `tests/jobs_sessao.py` — `criar_sessao(con, slug='demo', login='admin', horas=2) -> (token, tenant_id, usuario_id)`
    via `plat.auth_login` + `plat.auth_sessao_criar` (funções SECURITY DEFINER da 002; nada de senha), usado pelos
    testes de API (cookie no `TestClient`) e pelo e2e (`context.add_cookies`).
24. `tests/api/jobs/conftest.py` — fixtures: `sessao_demo`, `sessao_demo2`, `cliente_demo` (TestClient com cookie),
    `job_de_prova` (cria e espera terminar com timeout), `esperar_estado(id, estado, timeout)`.
25. `tests/api/jobs/test_jobs_fila.py`, `test_jobs_progresso.py` (`lento`), `test_jobs_cancelamento.py`,
    `test_jobs_reinicio.py` (`lento`; usa `sudo systemctl restart plat-worker` e `sudo systemctl kill -s KILL
    plat-worker`; pula com mensagem se `sudo -n` não estiver disponível), `test_jobs_memoria.py`, `test_jobs_rls.py`,
    `test_jobs_agenda.py`, `test_jobs_sse.py` (HTTP real em `:8150` e pela URL pública: `X-Accel-Buffering` chega,
    primeiro evento é `estado`, `Last-Event-ID` reenvia log) — conteúdo na seção 12 do ADR; toda medida pela fixture
    `medida("L0-05-jobs")`.
26. `tests/unit/test_jobs_registro.py`, `tests/unit/test_cron.py` — seção 12.
27. `tests/api/test_saude.py` — acrescentar `assert corpo["servicos"]["worker"] == "ok"` e `corpo["fila"]["workers_vivos"] >= 1`.
28. `make openapi` → `docs/openapi.json` regenerado. **Regra de merge:** o arquivo é gerado; quem mescla por segundo roda
    `make openapi` de novo e comita o resultado; nunca se resolve conflito nele à mão.
29. Rodar `sudo bash install.sh plat.iagrointel.com 8150` (root; conferir `free -g` ≥ 3 GB disponíveis antes),
    `make check-rapido`, `make e2e-worker`; colar saídas literais no `30_backend.md` (unidade ativa, `/saude` com
    `fila`, 100 jobs sem duplicata, cancelamento em segundos, reinício com `reinicios=1`, memória → `falhou`).
30. Handoff `30_backend.md` no modelo obrigatório, com a lista do que ficou fora (nada de `executor='gpu'` além do
    campo; nenhum tipo além dos de prova, do expurgo e dos que este item pede).

### 31 · frontend — arquivo por arquivo

31. `web/tarefas.html` — página da seção 10: cabeçalho com `plat`, links `/` e `/tarefas` e o contador de ativos
    (`#tarefas-ativas`); seção `filtros` (`select#f-estado`, `select#f-tipo` preenchido por `GET /api/jobs/tipos`,
    `select#f-quem` com "eu"/"todos" só quando `perfil = admin`, `select#f-periodo`); tabela `#lista` com colunas
    estado · tipo · quem · criado · duração · progresso · ações; paginação `#paginacao`; painel `#detalhe` (blocos
    parâmetros, resultado com link `/conteudo/<item_id>` quando existir, proveniência, log ao vivo com filtro de nível
    e botão baixar); seção `#agendas` (lista, novo, pausar/retomar/rodar agora) visível para `admin`/`editor`;
    `<body data-pronto="1">` ao terminar a primeira carga (o e2e espera isso, como na página inicial). Estados sempre
    com símbolo e texto além da cor. `<meta name="robots" content="noindex, nofollow">`. Sem `?v=` em `import`.
32. `web/tarefas.css` — estilo da tela (arquivo próprio; **não** editar `web/style.css`, que a trilha A pode tocar);
    reutiliza as variáveis `--fundo/--painel/--borda/--texto/--fraco/--ok/--falha` do `style.css` e acrescenta
    `--andamento` e `--aviso`.
33. `web/js/jobs/api.js` — funções `listar(filtros)`, `obter(id)`, `criar(tipo, parametros)`, `cancelar(id)`,
    `repetir(id)`, `log(id, apos, limite)`, `resumo()`, `tipos()`, `agendas*()` sobre `obterJSON` de `js/core.js`;
    trata o erro D18 (`{erro, mensagem, detalhe, req_id}`) e 401 → redireciona para `/login?voltar=/tarefas` (rota da
    trilha A; enquanto não existir, mostra mensagem "sessão expirada" — não é botão inerte, é o estado real).
34. `web/js/jobs/eventos.js` — `assinar(id, aoEvento)` com `EventSource('/api/jobs/'+id+'/eventos')`, eventos
    `estado`, `log`, `fim`; após 2 erros seguidos cai para polling de 3 s em `obter(id)` + `log(id, apos)` e volta ao
    SSE na próxima abertura; limite de 10 assinaturas simultâneas por página (as demais ficam em polling da lista);
    `cancelarAssinatura(id)`.
35. `web/js/jobs/formato.js` — datas em pt-BR (`hoje 14:02`, `ontem 18:11`, `05/09 03:30`), durações `mm:ss`/`hh:mm:ss`,
    rótulo e símbolo por estado, número de linhas de log.
36. `web/js/jobs/lista.js` — renderiza a tabela a partir de `listar()`; assina SSE dos jobs `pendente`/`rodando`
    visíveis; `resumo()` a cada 10 s atualiza `#tarefas-ativas` e, se `pendente+rodando` mudou, relê a primeira
    página (linha nova aparece sem recarregar); ordenação por coluna (`ordenar=campo:asc|desc`), paginação de 50;
    botão cancelar (confirmação, desabilita até o evento `estado`), repetir (abre o detalhe do novo); exportar CSV da
    página atual (gerado no navegador a partir do JSON — não há rota de CSV neste item).
37. `web/js/jobs/detalhe.js` — abre por clique ou por `/tarefas/<id>` (lê `location.pathname`); assina o SSE; anexa
    linhas de log; filtro de nível; `baixar log` = `log(id, 0, 2000)` em `text/plain` via `Blob`; blocos de
    parâmetros/resultado/proveniência em `<pre>`; link para o item quando `resultado.item_id` existe.
38. `web/js/jobs/agendas.js` — lista e formulário (nome, tipo do registro, parâmetros JSON validados no navegador contra
    `parametros_schema` só quanto a campos obrigatórios, cron, fuso), ações pausar/retomar/rodar agora; erros 422 do
    servidor mostrados por campo (`detalhe`).
39. `web/js/jobs/tarefas.js` — entrada: lê a sessão (`GET /api/jobs/resumo` já exige sessão; 401 → item 33), carrega
    tipos, monta filtros, inicia lista e detalhe, marca `data-pronto`.
40. `tests/e2e/test_tarefas.py` — `lento` + `e2e`: cookie via `tests/jobs_sessao.py` (`context.add_cookies` com
    `plat_sessao`, `Secure`, `HttpOnly`); dispara `prova.progresso(duracao_s=60, passos=30)` pela API e confere que a
    linha aparece **sem recarregar**, que o progresso sobe (dois valores distintos observados), que termina `concluido`
    e que o detalhe mostra resultado e log; cancela um segundo job pela tela e vê `cancelado`; filtro por estado
    compara contagem da tela com `GET /api/jobs?estado=...`; 1.000 jobs semeados por SQL (como `plat_app` no inquilino
    demo) → primeira pintura medida (`primeira_pintura_tarefas_ms` ≤ 1.000); capturas `L0-05-jobs_lista.png` e
    `L0-05-jobs_detalhe.png`; 0 erro de console e nenhuma resposta ≥ 400 além do que o teste provoca.
41. Handoff `31_frontend.md` no modelo obrigatório; declarar o tamanho de cada módulo (`wc -c`, orçamento 60 kB).

### Aviso de colisão com a trilha A (identidade), em uma tabela

| arquivo | trilha B acrescenta | onde | regra de merge |
|---|---|---|---|
| `app/main.py` | 1 `import` + 1 `include_router` | abaixo das linhas homônimas de `saude` | quem comita por segundo rebaseia; os dois blocos coexistem |
| `install.sh` | 3 linhas no heredoc do `.env`; laço `grep -q \|\| echo` no passo d; passo `h2` inteiro; 1 checagem no passo j | âncoras nomeadas acima | blocos disjuntos dos da trilha A (passo g e login) |
| `app/settings.py` | campos ao fim da dataclass e do `carregar()`; `"worker"` em `servicos()` | fim de cada bloco | ordem A depois B |
| `requirements.txt` | 3 linhas ao fim | fim | manter ambas as adições |
| `.env.exemplo` | chaves ao fim | fim | idem |
| `Makefile` | 2 alvos ao fim | fim | idem |
| `tests/conftest.py` | **nada** (fixtures em `tests/api/jobs/conftest.py` e `tests/jobs_sessao.py`) | — | — |
| `web/style.css`, `web/index.html` | **nada** (`tarefas.css` próprio; a página inicial não muda) | — | — |
| `docs/openapi.json` | regenerado | — | nunca à mão: `make openapi` depois do merge |
| `db/migracoes/` | `004_jobs.sql` | — | A usa 003 (e 005 se precisar) |
| cookie de sessão | assume `plat_sessao`, constante única em `app/jobs/contexto.py` | — | se A escolher outro nome, muda-se a constante; se A publicar `app.auth.contexto_atual`, B troca 1 importação e apaga `contexto.py` |

---

Resumo em 10 linhas:
1. Decisão: fila própria em SQL (SKIP LOCKED + LISTEN/NOTIFY + heartbeat), Procrastinate documentado como reserva (D12), medido: +3,6 MB na venv, +12 MB de RSS, psycopg 3 obrigatório, tarefa em thread sem limite de memória nem kill por job.
2. Cada job roda em processo filho com `RLIMIT_DATA` (não `RLIMIT_AS`: numpy/OpenBLAS travam sob 256/512 MB de endereço), `OPENBLAS_NUM_THREADS=1`, `PR_SET_PDEATHSIG` e escalonamento SIGTERM 30 s → SIGKILL +10 s.
3. Números que decidem: NOTIFY 0,09 ms; SKIP LOCKED 0,28 ms; fork+conexão 14,7 ms (≈ 4.000 jobs vazios/min); SSE 0,94 ms (1 cliente) e 5,4 ms (100 clientes, RSS 58 MB).
4. Modelo `plat.job` com RLS, `job_log`, `worker`, `agenda`; estados pendente/rodando/concluido/falhou/cancelado; final imutável por gatilho; reinício ≠ tentativa; teto de 5 reinícios → falhou.
5. Worker = unidade `plat-worker` (`MemoryMax=2G`, `KillMode=mixed`, `OOMPolicy=continue`, `TimeoutStopSec=40`), 1 processo por padrão, `/saude` em :8153; "1 pesado por vez" por advisory lock de sessão.
6. Progresso em tempo real por SSE (`/api/jobs/{id}/eventos`) com polling de reserva; log por job em tabela (teto 10.000 linhas); proveniência = entradas + parâmetros + versão do código.
7. Agendamento por cron no worker (croniter 6.2.4 + fuso IANA), sem pg_cron; periódicos da plataforma no inquilino técnico `plataforma`; cotas: 2 simultâneos, 1.000/dia, 50 agendas, 15 min mínimo.
8. Gancho GPU: `executor='gpu'` + contrato de arquivos com sha256 ida e volta; implementação é do L1-05.
9. Contrato de API, wireframe da tela Tarefas e 12 arquivos de teste fixados; backend (30) e frontend (31) em paralelo, 41 passos numerados acima.
10. Colisão com a trilha A reduzida a 2 linhas em `main.py`, blocos disjuntos em `install.sh` e acréscimos ao fim de `settings/requirements/.env.exemplo/Makefile`; `openapi.json` sempre regenerado.
