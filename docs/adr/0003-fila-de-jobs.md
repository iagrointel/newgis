# ADR 0003 — Fila de jobs, worker `plat-worker` e tela "Tarefas" (item L0-05-jobs)

Estado: aceito (arquiteto, turno T2, trilha B, setembro de 2026). Cita e obedece `laco/decomposicao/L0_CONCEITO.md`
(D1 UUID gerado no banco; D11 GDAL por subprocesso no worker; **D12 fila própria só com Postgres, Procrastinate como
reserva documentada**; D14 eventos; D16 cotas; D18 contrato de erro; D19 registro de tarefas por decorador; D20 RLS em
tudo) e `L3L6_CONCEITO.md` A8/B9 (1 job pesado por vez; progresso granular; troca atômica; agendamento por tick da
fila). Toda decisão traz o motivo em uma das formas admitidas: MEDIDO nesta máquina (comando e saída literal em
`laco/handoffs/T2/L0-05-jobs/20_arquitetura.md`, scripts em `.../medicoes/`), LIDO em código que roda aqui ou DOCUMENTO
OFICIAL. Onde a decisão custa caro para mudar, o custo está escrito.

Contexto fixo (ADR 0001): schema `plat`, role `plat_app` LOGIN sem BYPASSRLS, pool psycopg2 com reconexão, RLS
`FOR ALL USING/WITH CHECK` em toda tabela com `tenant_id`, funções `SECURITY DEFINER` como único caminho que enxerga
além do inquilino, porta **8153** reservada ao worker, unidade `plat-worker`. Máquina: 12 vCPU, 23 GB de RAM com
3 GB disponíveis, disco `/` a 98 %. PostgreSQL 16.13; `pg_cron 1.6` instalado (`cron.database_name = iagro_sat`,
0 jobs); `idle_in_transaction_session_timeout = 60 s` no servidor.

---

## 1. Decisão principal: fila própria em SQL, Procrastinate como reserva

### 1.1 O que foi medido no Procrastinate (05/09/2026, venv do repositório, desinstalado depois)

| grandeza | valor medido | comando |
|---|---|---|
| versão mais recente no PyPI | 3.9.0 | `pip index versions procrastinate` |
| licença | MIT (`Classifier: License :: OSI Approved :: MIT License`) | `unzip -p ... METADATA` |
| wheel | 153.597 bytes | `pip download --no-deps` |
| dependências obrigatórias | `psycopg[pool]` (3.3.5 + psycopg_pool 3.3.1), `croniter` 6.2.4, `asgiref` 3.12.1, `attrs`, `packaging`, `python-dateutil`, `typing-extensions` | `Requires-Dist` |
| tamanho na venv | **+3.583.038 bytes** (52.690.427 → 56.274.465): procrastinate 1.552 kB, psycopg 2.048 kB, psycopg_pool 344 kB, croniter 548 kB, asgiref 188 kB | `du -sb venv` antes/depois |
| RSS ao importar | +12,2 MB por processo (25.920 kB com `app.db`+psycopg2 → 38.144 kB) | `/proc/self/status` |
| LISTEN/NOTIFY | sim: gatilhos `procrastinate_notify_queue_job_inserted_v1` e `..._abort_job_v1` em `procrastinate_any_queue_v1` | `sql/schema.sql` linhas 404-427 |
| retirada da fila | `procrastinate_fetch_job_v2` com `FOR UPDATE OF jobs SKIP LOCKED` | `schema.sql` linha 252 |
| retentativa | `RetryStrategy` (`retry_at`/`retry_in`, prioridade e lock na repetição) | `retry.py` |
| cancelamento | `cancel_job_by_id(abort=True)` marca `abort_requested`; a tarefa tem de ler `context.should_abort()` (cooperativo) | `manager.py` 350, `schema.sql` 294-320 |
| heartbeat / worker parado | tabela `procrastinate_workers`, `update_heartbeat_interval` 10 s, `stalled_worker_timeout` 30 s, poda na partida | `worker.py` 48-49 |
| agendamento cron nativo | sim, `@app.periodic(cron=...)` via croniter | `periodic.py` |
| esquema próprio | 4 tabelas, 2 tipos enum, 37 arquivos de migração, ferramenta própria de migração | `sql/migrations/` |
| tarefa síncrona | roda em **thread** do mesmo processo (`utils.sync_to_async`, `thread_sensitive=False`) | `worker.py` 311, `utils.py` 105-110 |

O que o Procrastinate **não** dá e o portão exige: `tenant_id` e RLS (as tabelas são dele), progresso 0-100 com
mensagem, log por job, limite de memória por job, "só 1 pesado por vez", proveniência, e isolamento por processo:
a tarefa síncrona roda em thread, logo uma tarefa que ignora o cancelamento ou estoura memória só morre com o worker
inteiro. Também obriga a um segundo driver (psycopg 3) no processo, contra a decisão do ADR 0001 (psycopg2 com pool
de reconexão).

### 1.2 O que foi medido para a fila própria (mesma máquina, como `plat_app`)

| grandeza | valor medido |
|---|---|
| latência `pg_notify` → `LISTEN` entre duas conexões | mediana **0,090 ms**, p95 0,122 ms, máx 2,9 ms (n = 200) |
| limite de carga do NOTIFY | 7.999 bytes ok; 8.001 → `payload string too long` (doc: 8000) |
| `UPDATE ... FROM (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)` em tabela de 10.000 linhas com índice parcial | mediana **0,282 ms**, p95 0,339 ms (n = 200) |
| fork de filho + conexão própria + `SELECT 1` + saída | mediana **14,7 ms**, p95 16,6 ms → ≈ 4.000 jobs vazios/min por processo (meta do item: ≥ 600) |
| filho com `RLIMIT_AS` 512 MiB tentando 1 GiB | morre com `MemoryError` em 0,01 s, código de saída 1, pai intacto |
| `import numpy, rasterio, shapely, pyproj` + 64 MB reais sob `RLIMIT_AS` 256/512 MB, 12 threads OpenBLAS (padrão) | 256 e 512 **travam** (OpenBLAS reserva endereço por thread: `pthread_create failed`); só 1.024 MB passa (VSZ 716 MB, RSS 137 MB) |
| o mesmo com `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` | `RLIMIT_AS` 256 falha, 512 passa (VSZ 276 MB); **`RLIMIT_DATA` 256, 512 e 1.024 passam** (RSS 137 MB), `ogrinfo --version` como neto rc = 0 |
| filho que ignora SIGTERM | continua vivo após 2 s; `SIGKILL` encerra em 0,001 s, código −9 |
| pai morto por `SIGKILL`, filho com `prctl(PR_SET_PDEATHSIG, SIGKILL)` | filho morre junto (verificado em `/proc`) |
| RSS base de um processo com `app.db` + psycopg2 | 25.920 kB (python puro 10.592 kB) |
| SSE (um thread `LISTEN` por processo, rota `async`, 1 cliente) | latência NOTIFY → cliente mediana **0,94 ms**, p95 1,15 ms |
| SSE com 100 clientes no mesmo job, 20 eventos | 1.900 entregas em 1.900 esperadas; mediana 5,4 ms, p95 7,1 ms, máx 22 ms; RSS do uvicorn 58.376 kB |

### 1.3 Decisão

**Fila própria** (D12), com quatro peças: tabela `plat.job` (+ `job_log`, `worker`, `agenda`) com RLS; retirada por
função `SECURITY DEFINER` com `FOR UPDATE SKIP LOCKED`; `LISTEN/NOTIFY` por gatilho para acordar worker e navegador;
**cada job roda em um processo filho** (fork) com `RLIMIT_DATA`, `PR_SET_PDEATHSIG` e kill por escalonamento. Motivos,
em ordem de peso:

1. Isolamento por processo é o único caminho medido que cumpre "job que estoura memória é morto e marcado `falhou`"
   e "kill após N s" sem derrubar o worker. Em thread (Procrastinate) não há como impor limite de memória por job nem
   matar uma tarefa que ignora a flag.
2. RLS por `tenant_id` no job, no log e na agenda: o Procrastinate não tem inquilino; seria preciso manter uma
   tabela paralela de qualquer jeito. Aqui a tabela que a tela lê é a própria fila.
3. Custo: ≈ 450 linhas de Python + ≈ 300 de SQL contra +3,6 MB, +12 MB de RSS por processo, um segundo driver e um
   esquema com 37 migrações que não é nosso. Os números medidos da fila própria (NOTIFY 0,09 ms, SKIP LOCKED 0,28 ms,
   fork 14,7 ms) estão duas ordens de grandeza abaixo do que o portão pede (progresso em ≤ 2 s; ≥ 600 jobs/min).
4. O Procrastinate resolve por biblioteca exatamente as partes que o Postgres já resolve sozinho (SKIP LOCKED,
   NOTIFY, heartbeat) e não resolve as que o produto precisa (itens 1 e 2).

**Custo de mudar para Procrastinate** (reserva do D12, gatilho: fila própria reprovar duas vezes o teste de morte):
o decorador `@tarefa`, a tabela `plat.job` vista pela API/tela e o contrato de API ficam; troca-se o motor de
retirada/heartbeat pelo dele (coluna `motor_ref bigint` em `plat.job` apontando para `procrastinate_jobs.id`), entra
psycopg 3 **só no worker**, e o isolamento por processo passa a ser feito dentro da tarefa (fork explícito). Estimativa:
dois dias de uma pessoa; nenhuma migração destrutiva.

---

## 2. Modelo de dado (`db/migracoes/004_jobs.sql`, idempotente)

### 2.1 Tabelas

```sql
CREATE TABLE IF NOT EXISTS plat.job (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- D1: opaco, gerado no banco
  tenant_id           int NOT NULL REFERENCES plat.tenant(id),
  usuario_id          int REFERENCES plat.usuario(id),             -- NULL = agenda/periódico
  tipo                text NOT NULL,                                -- nome registrado em código (seção 3)
  parametros          jsonb NOT NULL DEFAULT '{}'::jsonb,           -- validados pelo modelo do tipo na criação
  estado              text NOT NULL DEFAULT 'pendente'
                      CHECK (estado IN ('pendente','rodando','concluido','falhou','cancelado')),
  prioridade          smallint NOT NULL DEFAULT 5 CHECK (prioridade BETWEEN 1 AND 9),  -- 1 = primeiro
  chave               text,                                         -- lock lógico: mesma chave nunca roda em paralelo
  pesado              boolean NOT NULL,                             -- copiado do registro do tipo na criação
  memoria_mb          int NOT NULL,                                 -- idem (RLIMIT_DATA do filho, seção 4.3)
  timeout_s           int NOT NULL,                                 -- idem
  executor            text NOT NULL DEFAULT 'local' CHECK (executor IN ('local','gpu')),
  max_tentativas      smallint NOT NULL DEFAULT 3,
  tentativa           smallint NOT NULL DEFAULT 0,                  -- quantas execuções começaram
  reinicios           smallint NOT NULL DEFAULT 0,                  -- devoluções por reinício/ceifa (não contam como tentativa)
  agendado_para       timestamptz NOT NULL DEFAULT now(),           -- só sai da fila a partir daqui (retentativa, agenda)
  agenda_id           uuid,                                         -- origem periódica (seção 7)
  programado_para     timestamptz,                                  -- ocorrência da agenda; UNIQUE com agenda_id
  criado_em           timestamptz NOT NULL DEFAULT now(),
  iniciado_em         timestamptz,
  heartbeat_em        timestamptz,
  terminado_em        timestamptz,
  worker              text,                                         -- nome do worker que pegou
  processo_pid        int,
  progresso           smallint NOT NULL DEFAULT 0 CHECK (progresso BETWEEN 0 AND 100),
  mensagem            text,                                         -- ≤ 200 caracteres, última mensagem de progresso
  cancelar_solicitado boolean NOT NULL DEFAULT false,
  cancelado_por       int,
  cancelado_em        timestamptz,
  resultado           jsonb,                                        -- {"item_id": uuid, ...} do tipo (seção 3.3)
  erro                text,                                         -- mensagem saneada; traceback vai para job_log nível ERRO
  proveniencia        jsonb,                                        -- seção 3.4
  linhas_log          int NOT NULL DEFAULT 0,
  UNIQUE (agenda_id, programado_para)
);
CREATE INDEX IF NOT EXISTS ix_job_fila      ON plat.job (prioridade, agendado_para, criado_em) WHERE estado = 'pendente';
CREATE INDEX IF NOT EXISTS ix_job_rodando   ON plat.job (heartbeat_em) WHERE estado = 'rodando';
CREATE INDEX IF NOT EXISTS ix_job_tenant    ON plat.job (tenant_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_job_chave     ON plat.job (chave) WHERE estado IN ('pendente','rodando') AND chave IS NOT NULL;

CREATE TABLE IF NOT EXISTS plat.job_log (
  id         bigserial PRIMARY KEY,
  job_id     uuid NOT NULL REFERENCES plat.job(id) ON DELETE CASCADE,
  tenant_id  int NOT NULL,
  em         timestamptz NOT NULL DEFAULT clock_timestamp(),
  nivel      text NOT NULL CHECK (nivel IN ('DEBUG','INFO','AVISO','ERRO')),
  mensagem   text NOT NULL                                            -- ≤ 4.000 caracteres (truncado pelo filho)
);
CREATE INDEX IF NOT EXISTS ix_job_log_job ON plat.job_log (job_id, id);

CREATE TABLE IF NOT EXISTS plat.worker (                            -- sem tenant_id: só funções SECURITY DEFINER escrevem
  nome         text PRIMARY KEY,                                     -- PLAT_WORKER_NOME (padrão: hostname)
  pid          int NOT NULL,
  versao       text NOT NULL,
  git_sha      text NOT NULL,
  processos    int NOT NULL,
  iniciado_em  timestamptz NOT NULL DEFAULT now(),
  heartbeat_em timestamptz NOT NULL DEFAULT now(),
  rss_kb       int,
  rodando      int NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS plat.agenda (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        int NOT NULL REFERENCES plat.tenant(id),
  usuario_id       int REFERENCES plat.usuario(id),                 -- dono; NULL = periódico da plataforma
  nome             text NOT NULL,
  tipo             text NOT NULL,
  parametros       jsonb NOT NULL DEFAULT '{}'::jsonb,
  cron             text NOT NULL,                                   -- 5 campos; validado por croniter na API e no worker
  fuso             text NOT NULL DEFAULT 'America/Sao_Paulo',       -- nome IANA; validado por zoneinfo
  ativa            boolean NOT NULL DEFAULT true,
  proxima_em       timestamptz,                                     -- NULL quando pausada
  ultima_em        timestamptz,
  ultimo_job_id    uuid,
  ultimo_estado    text,
  falhas_seguidas  smallint NOT NULL DEFAULT 0,                     -- 5 → ativa = false (B9)
  expira_em        timestamptz,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_agenda_proxima ON plat.agenda (proxima_em) WHERE ativa AND proxima_em IS NOT NULL;
```

Motivos das escolhas que não são óbvias:

- `pesado`, `memoria_mb`, `timeout_s`, `executor`, `max_tentativas` copiados do registro do tipo **na criação**: o
  job é auditável depois que o código mudou; o filho aplica o limite que o job carrega, não o que o registro tem hoje.
- `tentativa` e `reinicios` separados: reinício do worker e ceifa **não** consomem tentativa (o job não falhou); só
  exceção da tarefa consome. É o que faz "sobrevive a reinício" e "3 tentativas" não se anularem.
- `chave` como lock lógico (mesma camada não importa duas vezes ao mesmo tempo): a função de retirada pula job
  cuja chave já está `rodando`. Não é advisory lock porque tem de ser visível na tela e sobreviver ao worker.
- `job_log` tem `tenant_id` denormalizado para a política de RLS ser comparação direta (mesma razão de `sessao` no
  ADR 0001). Teto: 10.000 linhas por job; a partir daí o filho grava 1 linha por 1.000 suprimidas e `linhas_log`
  continua contando.
- `worker` sem `tenant_id`: é infraestrutura, não pertence a inquilino; `plat_app` só lê pela função
  `plat.fila_estado()`.
- `UNIQUE (agenda_id, programado_para)`: dois workers (ou o mesmo depois de reinício) não enfileiram a mesma
  ocorrência duas vezes; a inserção repetida é ignorada por `ON CONFLICT DO NOTHING`.

### 2.2 RLS (D20) e quem escreve o quê

| tabela | política `FOR ALL TO plat_app` | quem escreve fora da política |
|---|---|---|
| job | `tenant_id = plat.tenant_atual()` (USING e WITH CHECK) | funções `job_pegar`, `job_heartbeat`, `job_terminar`, `job_devolver`, `job_ceifar` (SECURITY DEFINER; seção 4.2) |
| job_log | `tenant_id = plat.tenant_atual()` | ninguém: o filho grava sob o contexto do inquilino do job |
| worker | sem RLS; `REVOKE ALL ... FROM plat_app`; leitura por `plat.fila_estado()` | funções `worker_registrar`, `worker_heartbeat`, `worker_ceifar` |
| agenda | `tenant_id = plat.tenant_atual()` | `agenda_vencidas()` e `agenda_enfileirar()` (o relógio do worker vê todos os inquilinos) |

**Alterado em T2 (correção após o testador; migração `006_jobs_transicoes.sql`): motivo** — a role `plat_app` com
contexto de inquilino conseguia, por SQL, levar um job `pendente → rodando → concluido` com resultado forjado, sem
worker: o gatilho da 004 só protegia o estado FINAL. Passa a valer, em três camadas verificáveis por
`tests/api/jobs/test_jobs_transicoes.py`: (1) **role própria `plat_worker`** (LOGIN, sem BYPASSRLS, sem privilégio de
tabela; `PLAT_DSN_WORKER` no `.env`, senha e linha no `pg_hba.conf` pelo `install.sh`) é a única com EXECUTE em
`job_pegar`, `job_pid`, `job_heartbeat`, `job_terminar`, `job_devolver`, `job_ceifar`, `worker_*`, `agenda_vencidas`,
`agenda_enfileirar`, `agenda_periodica_sincronizar`, `jobs_no_dia`; `plat_app` perde o EXECUTE nelas; (2) **`REVOKE
UPDATE ON plat.job FROM plat_app`**: a API cancela por `plat.job_cancelar(id, usuario)` (pendente → cancelado; rodando →
`cancelar_solicitado`; exige o contexto do inquilino do job) e o filho reporta por `plat.job_progresso(id, worker, pct,
mensagem)` (só progresso/mensagem/heartbeat do job rodando deste worker e deste inquilino; `linhas_log` passa a ser
contado por gatilho SECURITY DEFINER); (3) **gatilho `plat.job_transicao`** BEFORE INSERT OR UPDATE: job nasce
`pendente` e limpo (sem resultado, tentativa 0, sem worker, sem datas) e toda transição para `rodando`/`concluido`/
`falhou` ou mudança de `resultado`/`tentativa`/`reinicios`/`worker`/`iniciado_em`/`proveniencia`/`processo_pid` exige o
GUC `plat.via_worker = 'sim'`, que só as funções SECURITY DEFINER do worker ligam e desligam dentro da própria
transação (`plat.via_worker_ligar/desligar`, sem EXECUTE para ninguém). O `pg_try_advisory_lock` e o `LISTEN` do worker
rodam na sessão de `plat_worker`. O filho continua `plat_app` dentro do inquilino do job (a tarefa é dado do inquilino).
Limite escrito: RLS por GUC continua sendo o limite de tudo o que é `plat_app` (quem tem a senha da role escolhe o
inquilino); a separação nova é entre **quem executa tarefas** e **quem muda estado de job**.

**Alterado em T2 (correção 3): semeadura de demonstração, migração `014_jobs_semear_demo.sql`.** O e2e da primeira
pintura com 1.000 jobs semeava por `INSERT` direto de job já `concluido` como `plat_app` — o que a 006 passou a
barrar, corretamente. Em vez de abrir exceção no gatilho, existe agora `plat.jobs_semear_demo(quantos, tipo,
parametros, estado)` (`SECURITY DEFINER`, `EXECUTE` só para `plat_app`) com quatro guardas: interruptor
`plat.ambiente.semear_demo` (tabela nova, uma linha, escrita só pelo `install.sh` a partir de `PLAT_AMBIENTE=dev`
ou `PLAT_SEMENTE_DEMO=sim`; `plat_app` só lê), inquilino de demonstração (`demo`, `demo2`, `zt-%`), estado
**terminal** (nunca `pendente` visível ao worker nem `rodando`) e teto de 5.000 por chamada com a marca
`parametros.semente_demo = true`. **A 006 não é afrouxada**: a função insere o job `pendente` e limpo, como o ramo
de INSERT do gatilho já permite a qualquer chamador, e só então transiciona pelo mesmo caminho do worker
(`plat.via_worker_ligar` dentro do `SECURITY DEFINER`). Limite escrito: o GUC `plat.via_worker` é de prefixo livre e
qualquer role consegue defini-lo; o que impede a forja é o `REVOKE UPDATE ON plat.job FROM plat_app` mais o ramo de
INSERT do gatilho, não o GUC. Provado por `tests/api/jobs/test_jobs_semente_demo.py`.

Regra que este ADR fixa e o teste `tests/api/test_jobs_rls.py` prova: **a API nunca chama as funções do worker**, e
**o filho que executa a tarefa roda sob `set_config('plat.tenant_id', <tenant do job>)`**, ou seja, o código de
qualquer tipo de job enxerga só o inquilino dono do job (uma importação que tentasse gravar na camada de outro
inquilino falha no `WITH CHECK`). As funções `SECURITY DEFINER` têm `REVOKE EXECUTE ... FROM PUBLIC` e
`GRANT EXECUTE ... TO plat_app` (achado do adversário do T1, D20).

### 2.3 Máquina de estados e gatilhos

```
pendente ──(job_pegar)──▶ rodando ──(job_terminar)──▶ concluido | falhou | cancelado
   ▲                          │
   │  job_devolver / job_ceifar (reinício, worker sem sinal; tentativa < max) — reinicios += 1
   └──────────────────────────┘        (tentativa ≥ max ou motivo definitivo) ──▶ falhou
pendente ──(cancelar antes de iniciar)──▶ cancelado
```

Tradução para o vocabulário do job de geoprocessamento Esri (D12; usada só pelo `/svc/` do L2-04, nunca na API
própria): pendente = esriJobSubmitted/Waiting; rodando = esriJobExecuting (com `cancelar_solicitado` = Cancelling);
concluido = Succeeded; falhou = Failed ou TimedOut (quando `erro` começa por `tempo esgotado`); cancelado = Cancelled.

Gatilhos (rodam como dono da tabela, o código nunca precisa lembrar de notificar):

- `plat.job_estado_final_imutavel` BEFORE UPDATE: se `OLD.estado IN ('concluido','falhou','cancelado')` e qualquer
  coluna de estado/progresso/resultado muda → `RAISE EXCEPTION 'job em estado final'`. Estado final é imutável;
  "repetir" cria job novo.
- `plat.job_notificar` AFTER INSERT OR UPDATE OF estado, progresso, mensagem, cancelar_solicitado:
  `pg_notify('plat_job', json{job, tenant_id, estado, progresso, mensagem(≤200), tentativa, seq})` para o navegador
  e, quando `NEW.estado = 'pendente'` ou `cancelar_solicitado` virou true, `pg_notify('plat_worker', json{job})`
  para acordar o worker. Carga sempre < 1.000 bytes (limite medido: 8.000).
- `plat.job_log_notificar` AFTER INSERT em `job_log`: `pg_notify('plat_job', json{job, tenant_id, log: {id, nivel,
  mensagem(≤1000)}})`.

---

## 3. Tipos de job registrados em código (D19)

### 3.1 Decorador

```python
# app/jobs/registro.py
@tarefa(
    nome="prova.progresso",             # <área>.<verbo>; único; vai para plat.job.tipo
    descricao="Job de prova: N passos com progresso e log",
    parametros=ProvaProgressoParametros, # modelo pydantic; a API valida na criação (422 com o detalhe)
    pesado=False,                        # True = só 1 por vez na máquina (seção 4.4)
    memoria_mb=256,                      # RLIMIT_DATA do filho (seção 4.3); 128 ≤ valor ≤ PLAT_WORKER_MEMORIA_MB, senão o registro recusa no import
    timeout_s=600,                       # parede; excedido → SIGTERM, +10 s SIGKILL, estado falhou "tempo esgotado"
    tentativas=3,                        # exceção comum → retentativa com espera 2·4·8 s; FalhaDefinitiva não repete
    chave=lambda p: None,                # função dos parâmetros → texto do lock lógico, ou None
    executor="local",                    # "local" | "gpu" (seção 8; nenhum tipo usa "gpu" neste item)
    versao=1,                            # entra na proveniência; mudar a lógica = incrementar
)
def prova_progresso(ctx: ContextoJob, duracao_s: int = 300, passos: int = 60) -> dict: ...
```

O registro é um dicionário de módulo preenchido na importação de `app.jobs.tipos` (que importa cada módulo de tipos,
inclusive os de outras linhas no futuro: `app/jobs/tipos_prova.py` agora; `app/ingestao/tarefas.py` no L0-04, e assim
por diante). `GET /api/jobs/tipos` lista o registro com o JSON Schema do modelo de parâmetros (é daí que o L5-02 gera
o nó do fluxo). Nome desconhecido na criação = 422.

### 3.2 O que a tarefa recebe: `ContextoJob`

```python
class ContextoJob:
    job_id: uuid.UUID; tenant_id: int; usuario_id: int | None; tipo: str; tentativa: int
    dir_trabalho: Path                 # PLAT_JOBS_DIR/<job_id>/, criado antes, apagado no fim (mantido 7 dias se falhou)
    def db(self): ...                  # contextmanager: cursor RealDict já dentro do inquilino (app.db.db(Contexto(...)))
    def progresso(self, pct: int, mensagem: str = "") -> None
        # UPDATE plat.job SET progresso, mensagem, heartbeat_em WHERE id RETURNING cancelar_solicitado
        # no máximo 1 escrita/s (as demais só atualizam em memória); se cancelar_solicitado: raise Cancelado
    def log(self, nivel: str, mensagem: str) -> None      # INSERT em job_log (≤ 4.000 chars; teto 10.000 linhas)
    def cancelado(self) -> bool                             # leitura barata da flag (para laços sem progresso)
    def entrada(self, item_id: uuid.UUID | None, sha256: str, descricao: str = "") -> None   # proveniência
    def subprocesso(self, argv: list[str], **kw) -> subprocess.CompletedProcess
        # roda ogr2ogr/gdal/etc. como neto com o mesmo RLIMIT_DATA; stdout/stderr vão para job_log; cancelamento mata o neto
```

Exceções com significado: `Cancelado` (levantada por `progresso()`; a tarefa pode capturar para limpar e relançar),
`FalhaDefinitiva(mensagem)` (não retenta), qualquer outra exceção (retenta até `tentativas`).

### 3.3 Resultado

Dicionário serializável em JSON. Convenção obrigatória para o catálogo (L0-03) e a tela: `{"item_id": "<uuid>", ...}`
quando o job criou/alterou um item; a tela mostra o link `/conteudo/<item_id>` quando a chave existe. Sem item, o
resultado é o que o tipo quiser (contagens, caminhos relativos a `dir_trabalho`, avisos).

### 3.4 Proveniência (gravada pelo pai em `job.proveniencia`, completada pela tarefa via `ctx.entrada`)

```json
{"tipo": "ingestao.vetor", "versao_tipo": 3, "git_sha": "8ffe950", "versao": "0.2.0",
 "parametros": {...}, "entradas": [{"item_id": "…", "sha256": "…", "descricao": "arquivo.gpkg"}],
 "worker": "srv1", "python": "3.12.3", "gdal": "3.8.4", "iniciado_em": "…", "terminado_em": "…", "tentativa": 1}
```

`gdal` só quando o tipo declara `ferramentas=("gdal",)`; o pai lê a versão uma vez na partida. É o mesmo manifesto
que o L5-02-b estende por nó e que o L0-09-a copia para o bloco de procedência do item.

---

## 4. Worker (`app/jobs/worker.py`, unidade `plat-worker`)

### 4.1 Processo pai (laço, sem pool)

Uma conexão própria (`psycopg2.connect`, autocommit; **nunca o pool de `app.db`**: o pool herdado por fork
compartilharia sockets entre pai e filho). Laço a cada tick (≤ 1 s, ou antes se chegar NOTIFY em `plat_worker`):

1. `worker_heartbeat(nome, rss_kb, rodando)`; a cada 30 s `job_ceifar(60)` e `worker_ceifar(90)`; a cada 30 s o
   relógio da agenda (seção 7).
2. Para cada filho vivo: `job_heartbeat(id, worker)` a cada 10 s (devolve `cancelar_solicitado`); se pedido de
   cancelamento e o filho continua vivo 30 s depois do pedido → `SIGTERM`; +10 s → `SIGKILL`; se
   `now() − iniciado_em > timeout_s` → `SIGTERM` e marca `erro = 'tempo esgotado (timeout_s = N)'`; +10 s → `SIGKILL`.
3. Se `len(filhos) < PLAT_WORKER_PROCESSOS`: `job_pegar(nome, pesado_ok)` onde `pesado_ok = pg_try_advisory_lock(
   hashtext('plat.job.pesado'))` (seção 4.4). Job recebido → fork.
4. Filho terminou: lê do pipe `{estado, resultado|erro, traceback}`; código 0 → `job_terminar(concluido)`; código 3
   → `cancelado`; código 4 (`FalhaDefinitiva`) → `falhou`; outro código/sinal (inclusive −9 por OOM ou `MemoryError`)
   → se `tentativa < max_tentativas`: `job_devolver(id, motivo, conta_tentativa=true)` com
   `agendado_para = now() + 2^tentativa s` (2, 4, 8 s), senão `falhou`. Libera o advisory lock se o job era pesado.

Parada (`SIGTERM` da unidade): para de pegar jobs; para cada filho vivo chama `job_devolver(id, 'worker reiniciado',
conta_tentativa=false)` (**o job volta a `pendente`, `reinicios += 1`, `tentativa` não muda**) e envia `SIGTERM` ao
filho; espera até 20 s; `SIGKILL`; `worker_desregistrar`; sai 0. `TimeoutStopSec=40` na unidade cobre isso.
Partida: `job_ceifar` imediato para **os jobs com `worker = meu nome`** (não espera 60 s: o worker sabe que acabou de
nascer), depois o laço.

### 4.2 Funções do worker (`SECURITY DEFINER`, `SET search_path = plat, public`, EXECUTE só `plat_app`)

```
plat.job_pegar(p_worker text, p_pesado_ok boolean) RETURNS plat.job
   -- WITH c AS (SELECT id FROM job j WHERE estado='pendente' AND agendado_para <= now()
   --            AND (p_pesado_ok OR NOT pesado)
   --            AND (chave IS NULL OR NOT EXISTS (SELECT 1 FROM job r WHERE r.chave=j.chave AND r.estado='rodando'))
   --            AND (SELECT count(*) FROM job r WHERE r.tenant_id=j.tenant_id AND r.estado='rodando')
   --                < plat.cota_jobs_simultaneos(j.tenant_id)
   --            ORDER BY prioridade, agendado_para, criado_em FOR UPDATE SKIP LOCKED LIMIT 1)
   -- UPDATE job SET estado='rodando', worker=p_worker, iniciado_em=now(), heartbeat_em=now(),
   --                tentativa=tentativa+1, progresso=0, mensagem=NULL FROM c WHERE job.id=c.id RETURNING job.*
plat.job_heartbeat(p_id uuid, p_worker text) RETURNS boolean          -- atualiza heartbeat_em; devolve cancelar_solicitado
plat.job_terminar(p_id uuid, p_worker text, p_estado text, p_resultado jsonb, p_erro text, p_proveniencia jsonb) RETURNS boolean
   -- só se estado='rodando' AND worker=p_worker (senão devolve false: outro worker já ceifou; o pai só registra no log)
plat.job_devolver(p_id uuid, p_worker text, p_motivo text, p_conta_tentativa boolean, p_espera_s int) RETURNS text
   -- 'pendente' (reinicios+1 ou já contou tentativa) ou 'falhou' (tentativa >= max_tentativas)
plat.job_ceifar(p_limite_s int, p_worker text DEFAULT NULL) RETURNS int
   -- rodando com heartbeat_em < now() - p_limite_s (ou worker = p_worker): job_devolver('worker sem sinal', false)
plat.worker_registrar(p_nome text, p_pid int, p_versao text, p_git_sha text, p_processos int) RETURNS void
plat.worker_heartbeat(p_nome text, p_rss_kb int, p_rodando int) RETURNS void
plat.worker_desregistrar(p_nome text) RETURNS void
plat.worker_ceifar(p_limite_s int) RETURNS int                        -- apaga workers sem sinal
plat.fila_estado() RETURNS TABLE (pendentes int, rodando int, workers_vivos int, ultimo_heartbeat timestamptz)  -- /saude
plat.cota_jobs_simultaneos(p_tenant int) RETURNS int                  -- tenant.config->>'cota_jobs_simultaneos', padrão 2
plat.agenda_vencidas() RETURNS SETOF plat.agenda                      -- ativa AND proxima_em <= now() FOR UPDATE SKIP LOCKED
plat.agenda_enfileirar(p_agenda uuid, p_programado_para timestamptz, p_proxima_em timestamptz) RETURNS uuid
   -- INSERT job (ON CONFLICT (agenda_id, programado_para) DO NOTHING) + UPDATE agenda.proxima_em/ultima_em/ultimo_job_id
```

Todas devolvem só o necessário e checam `p_worker` onde há dono; nenhuma aceita mudar estado final (o gatilho
garante).

### 4.3 Processo filho (um por job)

Logo depois do fork: `prctl(PR_SET_PDEATHSIG, SIGKILL)` (medido: pai morto por SIGKILL leva o filho junto);
`os.environ` com `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` (MEDIDO: com as 12 threads padrão do OpenBLAS o
`import numpy` reserva endereço por thread e trava sob limite de 256/512 MB; tipo que precise de BLAS paralelo
declara `threads_blas=N` no decorador e o filho exporta esse N); **`resource.setrlimit(RLIMIT_DATA, memoria_mb)`**,
não `RLIMIT_AS` (MEDIDO: `RLIMIT_DATA` conta segmento de dados + mmap anônimo privado, que é o que a RAM real ocupa —
doc `setrlimit(2)`, Linux ≥ 4.7 — e deixa numpy+rasterio+shapely+pyproj+ogrinfo funcionarem sob 256 MB com RSS de
137 MB; `RLIMIT_AS` conta endereço reservado e exige ≥ 512 MB para o mesmo trabalho); `app.db._pool = None` (nunca
herdar pool); `os.setsid()` não (o filho
tem de ficar no cgroup e no grupo de processos do pai para o `KillMode=mixed` alcançá-lo); `signal(SIGTERM)` →
levanta `Cancelado` no próximo `progresso()`/`cancelado()` e mata netos. Abre conexão própria via `app.db.db(Contexto(
tenant_id, usuario_id or 0, 'worker'))`; cria `dir_trabalho`; chama a função do tipo; grava o resultado no pipe; sai
com o código da seção 4.1. `MemoryError` sai com código 5 e mensagem `memória excedida (limite N MB)`. Neto (`ctx.subprocesso`, ex.: `ogr2ogr`)
herda o `RLIMIT_DATA` e as variáveis de threads; a tarefa que precisar de mais declara `memoria_mb` maior no decorador.

### 4.4 "Só 1 pesado por vez na máquina"

`pg_try_advisory_lock(hashtext('plat.job.pesado'))` **na conexão do pai**, tomado antes de `job_pegar(..., true)`
e liberado quando o filho do job pesado termina. Lock de sessão: se o worker morrer, o Postgres libera sozinho
(DOCUMENTO: advisory lock de sessão morre com a sessão). Vale para todos os workers que apontam para o mesmo banco
(é por banco, não por máquina; para dois hosts com bancos distintos, cada um tem o seu — anotado para o L7-07).
Job pesado também é o único que pode declarar `memoria_mb > 1024`.

### 4.5 Unidade `deploy/plat-worker.service` (modelo; `install.sh` substitui APP_DIR/APP_USER)

```ini
[Unit]
Description=plat — worker da fila de jobs (:8153). Interno. Análise / beta privado.
After=network.target postgresql.service plat-api.service
Wants=postgresql.service

[Service]
Type=simple
User=APP_USER
Group=APP_USER
WorkingDirectory=APP_DIR
Environment=PYTHONNOUSERSITE=1
ExecStart=APP_DIR/venv/bin/python -m app.jobs.worker
Restart=always
RestartSec=3
TimeoutStopSec=40
KillMode=mixed
OOMPolicy=continue
MemoryHigh=1536M
MemoryMax=2G
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- `KillMode=mixed` (DOCUMENTO systemd.kill): `SIGTERM` só ao processo principal; `SIGKILL` a todo o cgroup no
  `TimeoutStopSec`. Com o padrão `control-group` o filho receberia `SIGTERM` ao mesmo tempo que o pai e o pai não
  conseguiria devolver o job antes de o filho morrer.
- `OOMPolicy=continue` (DOCUMENTO systemd.service): com o padrão `stop`, um filho morto pelo OOM do cgroup derruba
  o serviço inteiro; com `continue` o pai sobrevive, lê o código −9 e marca o job `falhou` (o teste de memória prova
  o caminho do `RLIMIT_DATA`, que mata antes do OOM; o `MemoryMax` é a segunda cerca).
- `MemoryMax=2G`: pai 26 MB medido + `PLAT_WORKER_PROCESSOS` (1) × maior `memoria_mb` admitido
  (`PLAT_WORKER_MEMORIA_MB`, padrão 1536) com folga. Máquina com 3 GB disponíveis: subir este número é decisão do
  gerente do item que precisar (L3-16 pede 4 GB) e vem com `free -g` medido. `MemoryHigh` faz o kernel frear antes
  de matar.
- `Restart=always`: o worker sem job termina só por sinal; qualquer saída é anômala.
- Escala: `PLAT_WORKER_PROCESSOS=N` (filhos simultâneos) no `.env`; um segundo worker no mesmo host exige
  `PLAT_WORKER_NOME` distinto e uma segunda unidade (`plat-worker@2`, fora deste item).

### 4.6 Saúde do worker (`:8153`)

Servidor HTTP mínimo da biblioteca padrão (`http.server` em thread do pai), só `127.0.0.1:8153`, `GET /saude`:

```json
{"worker": "srv1", "pid": 12345, "versao": "0.2.0", "git_sha": "8ffe950", "processos": 1,
 "rodando": ["<uuid>"], "pesado_em_curso": false, "ultimo_tick_ms": 12, "rss_kb": 26400, "em": "2026-09-05T15:04:05Z"}
```

`/saude` da API ganha `servicos.worker` (`PLAT_WORKER_URL=http://127.0.0.1:8153`, mesma regra `< 500 = ok`) e o
bloco `fila: {pendentes, rodando, workers_vivos, ultimo_heartbeat}` lido por `plat.fila_estado()`. Neste item o
worker é **informativo** no status HTTP (200 continua com banco ok); o L7-06 decide alerta e obrigatoriedade.

---

## 5. Progresso em tempo real: SSE com polling de reserva (decisão por medição)

Medido (seção 1.2): SSE com um único thread `LISTEN` por processo da API alimentando filas `asyncio` por job entrega
o evento em 0,94 ms (1 cliente) e 5,4 ms (100 clientes), sem ocupar o threadpool de rotas `def` (rota `async`, o
gerador só espera a fila; DOCUMENTO anyio: o limitador padrão do threadpool tem 40 tokens por processo — um SSE em
gerador síncrono gastaria um token por cliente aberto, 80 clientes travariam a API com 2 workers). Polling a cada 2 s
custaria 0,5 requisição/s por aba aberta e teria latência média de 1 s; cumpre o portão (≤ 2 s) mas não cumpre com
folga e carrega o banco proporcionalmente às abas.

Decisão: **`GET /api/jobs/{id}/eventos` em SSE é o canal principal; `GET /api/jobs/{id}` é a reserva** (o front cai
para polling de 3 s depois de dois erros seguidos do `EventSource`, e volta ao SSE ao reconectar). Regras:

- Cabeçalhos: `Content-Type: text/event-stream`, `Cache-Control: no-store`, `X-Accel-Buffering: no` (DOCUMENTO nginx:
  desliga `proxy_buffering` para a resposta sem tocar no `nginx.conf`; **alterado em T2**: o nginx consome o cabeçalho
  e não o repassa ao cliente — `X-Accel-*` estão na lista padrão de `proxy_hide_header` —, por isso o teste o confere
  direto em `:8150` e, pela URL pública, mede o efeito: primeiro evento em 0,025 s); `proxy_read_timeout 120s` já
  existente > keepalive de 15 s (`: keepalive`).
- Eventos: `estado` (instantâneo do job, mesmo JSON do `GET`), `log` (`{id, em, nivel, mensagem}`), `fim` (estado
  final; o servidor fecha). Primeiro evento é sempre `estado` lido do banco (o cliente nunca perde o estado atual por
  ter conectado depois do NOTIFY). `Last-Event-ID` = último `job_log.id`; ao reconectar o servidor reenvia as linhas
  de log com id maior.
- Limites: 10 conexões SSE simultâneas por usuário por processo (429 além disso); conexão fechada em 30 min (o
  `EventSource` reconecta sozinho); job de outro inquilino = 404 (RLS na leitura inicial).
- O `LISTEN` da API é um thread por processo uvicorn (2 conexões a mais no total), com reconexão própria (mesma
  regra do pool: preparar de novo, nunca repetir o trabalho).

---

## 6. Cancelamento, morte e sobrevivência (o que o portão e a refutação pedem)

| situação | o que acontece | estado final | teste |
|---|---|---|---|
| cancelar job `pendente` | `UPDATE estado='cancelado', cancelado_por/em` direto na API | cancelado | `test_jobs_cancelamento.py` |
| cancelar job `rodando`, tarefa cooperativa (chama `progresso()` a cada ≤ 1 s) | flag → `Cancelado` na tarefa → limpeza → código 3 → `job_terminar(cancelado)` | cancelado em ≤ 2 s (medida `cancelamento_s`) | idem |
| cancelar job que ignora a flag | 30 s depois `SIGTERM` (handler levanta `Cancelado`); +10 s `SIGKILL` | cancelado (`erro = 'morto após ignorar cancelamento'`) | idem, marcado `lento` |
| `systemctl restart plat-worker` no meio | pai devolve (`reinicios += 1`), filho morre, worker novo pega de novo do zero | concluido na retomada; `tentativa` = 1, `reinicios` = 1 | `test_jobs_reinicio.py` (`lento`) |
| `kill -9` no pai | filho morre por PDEATHSIG; job fica `rodando` até a ceifa: worker novo na partida (`worker = meu nome`) ou outro worker em 60 s | pendente → concluido na retomada; nunca `concluido` sem execução completa | refutação do item; `test_jobs_reinicio.py` |
| 4 × `kill -9` no mesmo job | cada ceifa é `reinicios += 1`, não tentativa; **`reinicios ≥ PLAT_JOB_MAX_REINICIOS` (5) → falhou** `'devolvido 5 vezes sem terminar'` | falhou | refutação (L0-05-a) |
| exceção comum na tarefa | código ≠ 0 → `job_devolver(conta_tentativa=true)`; espera 2/4/8 s | falhou na 3ª (traceback em `job_log` nível ERRO, `erro` saneado) | `test_jobs_fila.py` |
| `FalhaDefinitiva` | código 4 | falhou sem retentativa | idem |
| `timeout_s` excedido | `SIGTERM`, +10 s `SIGKILL` | falhou `'tempo esgotado (timeout_s = N)'` | `test_jobs_cancelamento.py` |
| memória > `memoria_mb` | `MemoryError` no filho (código 5) ou −9 pelo cgroup | falhou `'memória excedida (limite N MB)'` | `test_jobs_memoria.py` |
| worker parado sem sinal (host caiu) | `job_ceifar(60)` por qualquer worker vivo | pendente (ou falhou pelo teto de reinícios) | `test_jobs_reinicio.py` |

Regra de escrita das tarefas (obriga L0-04, L1-01, L2-05, L3, L5-02, L6-02): **toda tarefa tem de poder recomeçar do
zero** (reinício = reexecução). Efeito parcial fica em tabela/arquivo de trabalho e entra por troca atômica no fim
(`ALTER TABLE ... RENAME` numa transação; objeto no bucket nomeado por sha256), como o B9 manda. A tarefa de prova
`prova.progresso` grava o efeito parcial em linhas de `plat_trabalho.passos` chaveadas por `job_id` e as apaga na
limpeza; o teste de cancelamento prova que não sobram (**alterado em T2**: o desenho original era uma tabela por job;
MEDIDO nesta máquina, `CREATE TABLE` custa 528–1.030 ms — catálogo com 3,2 mil objetos, disco a 98 % — e escondia a
vazão da fila; regra para autores de tipos escrita na 004: efeito parcial pequeno vai em linhas de tabela
compartilhada, DDL só quando o tipo realmente cria uma camada).

---

## 7. Agendamento (`plat.agenda`, para o L5-02-c, L6-02-k, L0-05-d, L5-30)

- Expressão cron de 5 campos + fuso IANA. Biblioteca: **croniter 6.2.4** (MIT, 548 kB, mantida em
  `github.com/pallets-eco/croniter`, mesma que o Procrastinate usa), com `python-dateutil` 2.9.0.post0 fixado no
  `requirements.txt` (MEDIDO: `dpkg -s python3-dateutil` não existe; `python3-six` 1.16 existe, mas fixa-se `six`
  também pela regra 2.1 do ADR 0001). MEDIDO: `*/15 2 * * *` a partir de 05/09/2026 13:30 `America/Sao_Paulo` →
  06/09 02:00 e 02:15 −03:00; `30 2 * * *` em `America/New_York` no dia da troca de horário (08/03/2026) → 03:00 −04:00
  (não some nem duplica); `61 * * * *` → `CroniterBadCronError` (a API devolve 422).
- **O worker é o relógio**: a cada 30 s, `agenda_vencidas()` (`FOR UPDATE SKIP LOCKED`, então dois workers não
  duplicam) → para cada agenda, `agenda_enfileirar(id, programado_para = proxima_em, proxima_em = croniter.next)`;
  `UNIQUE (agenda_id, programado_para)` é a segunda trava. Ocorrências perdidas por parada longa: enfileira **uma**
  (a mais recente vencida) e avança; não recupera o atraso (regra explícita; a Esri e o cron do sistema fazem o mesmo).
- Ao terminar um job com `agenda_id`: `ultimo_estado`; `falhas_seguidas` += 1 em `falhou` (zera em `concluido`);
  5 seguidas → `ativa = false` e evento `agenda.pausada` (D14; o e-mail é do L0-07-d).
- `pg_cron` **não** é usado. Motivo: exige `shared_preload_libraries` e agendamento por superusuário, que o appliance
  do cliente (L7-11) pode não ter; o relógio no worker não depende de nada além do banco. O que o B9 obriga
  ("aceita enfileiramento por tick") está cumprido por `agenda_enfileirar` e por `POST /api/agendas/{id}/rodar-agora`.
- Tetos por inquilino (D16): `cota_agendas` (padrão 50, como a referência Esri publica por organização) e intervalo
  mínimo de 15 min (cron cujas ocorrências distam < 15 min é recusado com 422); `cota_jobs_dia` (padrão 1.000) checado
  no `POST /api/jobs` (413) e no relógio (agenda pula a ocorrência e grava aviso no log da plataforma).
- Periódicos da plataforma (L0-05-d: expurgo de sessões, uploads incompletos, lixeira, `job` > 90 dias, `job_log` >
  30 dias, diretórios de trabalho órfãos) precisam de um `tenant_id`, porque a política de RLS de `agenda`, `job` e
  `job_log` exige a coluna preenchida e uma política alternativa para `NULL` teria de existir em toda tabela. Decisão:
  a migração 004 garante o **inquilino técnico `plataforma`** (**alterado em T2**: a 003 da trilha A o governa —
  superadmin vive nele, ativo, 2FA obrigatório — e a 004 só faz `INSERT ... ON CONFLICT DO NOTHING`, sem `ativo`/`config`) e os periódicos são declarados em código (`app/jobs/periodicos.py`, lista de
  `(nome, cron, tipo, parametros)`), sincronizados para `plat.agenda` desse inquilino na partida do worker
  (`INSERT ... ON CONFLICT (tenant_id, nome) DO UPDATE` só de `cron`/`parametros`) e enfileirados pelo mesmo relógio.
  A RLS continua valendo para tudo e o superadmin vê esses jobs no console (L0-07-f). Este item entrega **um**
  periódico: `jobs.expurgo` (diário 03:30, apaga `job` > 90 dias, `job_log` > 30 dias, diretórios órfãos e, **alterado
  em T2** (o testador mediu 1.255 marcadores acumulados), marcadores e passos órfãos de `plat_trabalho`; a função
  `plat.jobs_expurgar` só roda no contexto do inquilino `plataforma`).

---

## 8. Job remoto no GPU box (gancho; implementação é do L1-05)

Contrato fixado agora, para o registro e a tabela não mudarem depois:

- `executor = 'gpu'` no decorador e na linha do job. O pai, em vez de forkar a função do tipo, forka o **executor
  remoto** (`app/jobs/remoto.py`, entregue pelo L1-05), que:
  1. escreve `dir_trabalho/entrada/` (arquivos) + `entrada.json` (`{job_id, tipo, parametros, entradas:[{nome,
     sha256}]}`) e um `manifesto_entrada.json` com sha256 de cada arquivo;
  2. `rsync -a` para `PLAT_GPU_SSH:PLAT_GPU_DIR/<job_id>/` (MEDIDO: `ssh gpu` responde por chave; rsync 3.x e
     sha256sum existem lá; Python 3.12.3; disco 100 % com 16 GB livres — o L1-05 mede o espaço antes de copiar);
  3. `ssh PLAT_GPU_SSH python3 PLAT_GPU_DIR/executor.py <job_id>` com stdout em linhas JSON
     `{"progresso": n, "mensagem": "..."}` / `{"log": ...}` que o executor local repassa a `ctx.progresso/log`;
     cancelamento = fechar o ssh (o executor remoto recebe SIGHUP) + `rm -rf` remoto;
  4. `rsync -a` de volta `saida/` + `manifesto_saida.json`; **verifica sha256 de cada arquivo**; divergência =
     `FalhaDefinitiva('hash divergente na volta: <arquivo>')`; os hashes entram em `proveniencia.saidas`.
- Chaves de configuração reservadas: `PLAT_GPU_SSH` (ex.: `gpu`), `PLAT_GPU_DIR` (ex.: `/home/dev/plat-jobs`).
  Ausentes → o registro recusa tipos com `executor='gpu'` na importação (mensagem nomeia a chave), então nenhum job
  desse executor entra na fila.
- Job `gpu` é sempre `pesado = true` (a GPU é uma só) e usa o mesmo advisory lock da seção 4.4.

Neste item existe só a coluna, o CHECK, o campo do decorador e a recusa na importação; nenhum tipo `gpu` é registrado.

---

## 9. Contrato de API (todas as rotas exigem sessão; erros no formato D18 `{erro, mensagem, detalhe?, req_id}`)

**Alterado em T2 (correção 3, achado do testador).** As rotas de LEITURA (`GET /api/jobs`, `/api/jobs/resumo`,
`/api/jobs/tipos`, `/api/jobs/{id}`, `/api/jobs/{id}/log`, `/api/jobs/{id}/eventos`, `GET /api/agendas`,
`GET /api/agendas/{id}`) exigem o privilégio **`jobs.ver`**, que os quatro perfis têm (migração 015). As rotas de
EXECUÇÃO (`POST /api/jobs`, `cancelar`, `repetir`, e criar/alterar/apagar/pausar/retomar/rodar-agora de agenda)
seguem exigindo **`jobs.executar`** (campo, editor, admin). Motivo: com um privilégio só, o perfil `visualizador`
tomava 403 em `/api/jobs`, `/api/jobs/resumo` e `/api/jobs/tipos` e a tela Tarefas ficava em "…" com 4 erros de
console — P1 reprovado para um perfil legítimo. O filtro de dono desta seção **não muda**: quem não tem
`jobs.gerir_todos` continua vendo só os próprios jobs, logo o visualizador, que não cria job, lê uma lista vazia,
em modo só-leitura e sem erro. O escopo de token continua sendo `jobs:executar` (não há escopo novo).

| método e rota | entrada | resposta | códigos |
|---|---|---|---|
| `GET /api/jobs` | `estado`, `tipo`, `usuario_id`, `de`, `ate` (ISO 8601), `agenda_id`, `limite` (≤ 200, padrão 50), `deslocamento`, `ordenar` (`criado_em:desc` padrão; `iniciado_em`, `terminado_em`, `estado`, `tipo`) | `{"itens": [job...], "total": n}`; `admin` vê todos os jobs do inquilino, os demais só os próprios (`usuario_id = plat.usuario_atual()`) | 200, 401, 422 |
| `POST /api/jobs` | `{"tipo", "parametros", "prioridade"?, "agendado_para"?}` | 201 + job | 401, 403 (perfil `visualizador`/`campo` não cria job, salvo tipos com `perfil_minimo='visualizador'`), 413 (`cota_jobs_dia`), 422 (tipo desconhecido, parâmetros inválidos com `detalhe` do pydantic), 429 (> 200 pendentes do inquilino) |
| `GET /api/jobs/resumo` | — | `{"pendente": n, "rodando": n, "concluido_24h": n, "falhou_24h": n}` (mesmo filtro por perfil) | 200 |
| `GET /api/jobs/tipos` | — | `[{nome, descricao, pesado, memoria_mb, timeout_s, tentativas, executor, versao, perfil_minimo, parametros_schema}]` | 200 |
| `GET /api/jobs/{id}` | — | job (todas as colunas menos `processo_pid`; `parametros` e `resultado` inteiros; `proveniencia` inteira) | 200, 404 (inexistente ou de outro inquilino ou de outro usuário sem ser admin) |
| `POST /api/jobs/{id}/cancelar` | — | 202 + job (`cancelar_solicitado = true` ou `estado = cancelado` se era pendente) | 404, 409 (estado final) |
| `POST /api/jobs/{id}/repetir` | `{"parametros"?}` (sobrescreve chaves) | 201 + job novo (`proveniencia.repetido_de = id`) | 404, 403, 422 |
| `GET /api/jobs/{id}/log` | `apos` (id, padrão 0), `nivel`, `limite` (≤ 2.000, padrão 500) | `{"linhas": [{id, em, nivel, mensagem}], "total": n}` | 200, 404 |
| `GET /api/jobs/{id}/eventos` | cabeçalho `Last-Event-ID` opcional | `text/event-stream` (seção 5) | 200, 404, 429 |
| `GET /api/agendas` | `ativa`, `tipo`, `limite`, `deslocamento` | `{"itens": [...], "total"}` | 200 |
| `POST /api/agendas` | `{"nome", "tipo", "parametros", "cron", "fuso"?, "expira_em"?}` | 201 + agenda com `proxima_em` | 403, 413 (`cota_agendas`), 422 (cron inválida, fuso inválido, intervalo < 15 min, tipo desconhecido), 409 (nome repetido) |
| `GET/PUT/DELETE /api/agendas/{id}` | PUT: mesmos campos | agenda / 204 | 404, 422 |
| `POST /api/agendas/{id}/pausar`, `.../retomar`, `.../rodar-agora` | — | agenda / 201 + job | 404, 409 |
| `GET /tarefas`, `GET /tarefas/{id}` | — | `web/tarefas.html` (a página lê o id da URL) | 200 |

JSON de um job (o mesmo em lista, detalhe e evento `estado`):

```json
{"id": "…", "tipo": "prova.progresso", "estado": "rodando", "progresso": 42, "mensagem": "passo 25 de 60",
 "prioridade": 5, "pesado": false, "executor": "local", "usuario_id": 3, "usuario_login": "admin",
 "criado_em": "…", "agendado_para": "…", "iniciado_em": "…", "heartbeat_em": "…", "terminado_em": null,
 "duracao_s": 127.4, "tentativa": 1, "max_tentativas": 3, "reinicios": 0, "cancelar_solicitado": false,
 "worker": "srv1", "chave": null, "agenda_id": null, "resultado": null, "erro": null, "linhas_log": 25,
 "parametros": {"duracao_s": 300, "passos": 60}, "proveniencia": null}
```

`duracao_s` é calculada (`terminado_em` ou `now()` − `iniciado_em`). Datas em UTC ISO 8601 com `Z`.

---

## 10. Tela "Tarefas" (`web/tarefas.html` + `web/js/jobs/*.js`; wireframe)

```
┌ plat ───────────────────────────────────────────────────────────── [conteúdo] [tarefas ●3] [usuário ▾] ┐
│ Tarefas                                                               análise / beta privado            │
│ ┌ filtros ───────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ estado [todos ▾]  tipo [todos ▾]  quem [eu ▾ | todos (admin)]  período [últimos 7 dias ▾]  [limpar] │ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ lista (50 por página; ordenar por coluna) ─────────────────────────────────────────────────────────┐ │
│ │ estado     tipo               quem     criado          duração   progresso                 ações    │ │
│ │ ● rodando  ingestao.vetor     ana      hoje 14:02      01:27     ████████░░░░ 42 % passo 25 [cancelar]│ │
│ │ ○ pendente exportacao.gpkg    ana      hoje 14:05      —         na fila (2º)               [cancelar]│ │
│ │ ✓ concluído prova.progresso   admin    hoje 13:40      05:00     100 %  → item              [repetir] │ │
│ │ ✗ falhou   ingestao.vetor     joao     ontem 18:11     00:03     memória excedida (256 MB)  [repetir] │ │
│ │ — cancelado exportacao.csv    ana      ontem 17:50     00:41     cancelado por ana          [repetir] │ │
│ │                                                       ‹ 1 2 3 … 20 ›   1.000 tarefas   [exportar CSV]│ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ detalhe (abre à direita ou em /tarefas/<id>) ──────────────────────────────────────────────────────┐ │
│ │ ingestao.vetor · rodando · 42 % · tentativa 1 de 3 · worker srv1 · iniciado 14:02:10 · 01:27       │ │
│ │ [cancelar] [repetir] [baixar log]                                                                   │ │
│ │ ▸ parâmetros  {"item_id": "…", "crs": "EPSG:4674", ...}                                              │ │
│ │ ▸ resultado   {"item_id": "…"}  → abrir item                                                        │ │
│ │ ▸ proveniência  git 8ffe950 · versão 0.2.0 · tipo v3 · entradas: arquivo.gpkg sha256 3f9a…          │ │
│ │ ▾ log (ao vivo; nível [INFO ▾]; 25 linhas)                                                           │ │
│ │   14:02:11 INFO  inspeção: 3 camadas, 120.431 feições                                                │ │
│ │   14:02:40 INFO  camada 1/3: 40.000 feições em 28 s                                                  │ │
│ │   14:03:37 AVISO 12 geometrias inválidas corrigidas por ST_MakeValid                                 │ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌ agendas (admin/editor) ─────────────────────────────────────────────────────────────────────────────┐ │
│ │ nome            tipo              cron          fuso               próxima          última   [novo] │ │
│ │ expurgo diário  jobs.expurgo      30 3 * * *    America/Sao_Paulo  06/09 03:30      ✓ 05/09 [rodar agora] [pausar]│ │
│ └────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Comportamento: a lista assina **um** SSE por job visível em estado `pendente`/`rodando` (máx. 10 por usuário; acima
disso a lista faz polling de `GET /api/jobs?estado=rodando` a cada 3 s); linha nova aparece sem recarregar
(`GET /api/jobs/resumo` a cada 10 s atualiza o contador da barra e dispara releitura da primeira página quando muda);
progresso e mensagem atualizam na linha; detalhe assina o SSE do job e anexa linhas de log conforme chegam;
`cancelar` pede confirmação e desabilita o botão até o evento `estado`; `repetir` abre o detalhe do job novo;
`baixar log` = `GET /api/jobs/{id}/log?limite=2000` em texto. Estados com cor e símbolo (não só cor). Sem framework;
módulos `api.js`, `eventos.js` (EventSource + reserva por polling), `lista.js`, `detalhe.js`, `agendas.js`,
`formato.js` (datas pt-BR, durações), `tarefas.js` (entrada) — cada um ≤ 60 kB (ADR 0001 11.2).

---

## 11. Configuração nova (`.env`, `.env.exemplo`, `install.sh`)

| chave | obrigatória | padrão | uso |
|---|---|---|---|
| PLAT_WORKER_URL | não | `http://127.0.0.1:8153` | `/saude` da API |
| PLAT_WORKER_NOME | não | hostname | `plat.worker.nome`, `job.worker` |
| PLAT_WORKER_PROCESSOS | não | 1 | filhos simultâneos |
| PLAT_WORKER_MEMORIA_MB | não | 1536 | teto de `memoria_mb` que o registro aceita |
| PLAT_JOBS_DIR | não | `APP_DIR/var/jobs` | `dir_trabalho` (`.gitignore`: `var/`) |
| PLAT_JOB_MAX_REINICIOS | não | 5 | teto de devoluções sem terminar |
| PLAT_GPU_SSH, PLAT_GPU_DIR | não | vazio | seção 8 (só L1-05) |
| PLAT_DSN_WORKER | sim para o worker | `postgresql://plat_worker:<senha>@127.0.0.1:5432/iagro_sat` | **alterado em T2**: role do processo pai (seção 2.2); `install.sh` gera a senha e a linha do `pg_hba.conf` |

---

## 12. Testes obrigatórios (o testador roda; o backend entrega os arquivos)

| arquivo | prova | medida em `tests/medidas/L0-05-jobs.json` |
|---|---|---|
| `tests/unit/test_jobs_registro.py` | decorador recusa nome repetido, `memoria_mb` > teto, `executor='gpu'` sem `PLAT_GPU_SSH`; JSON Schema gerado | — |
| `tests/unit/test_cron.py` | 5 expressões válidas com fuso; 3 inválidas → 422; intervalo < 15 min recusado | — |
| `tests/api/test_jobs_fila.py` | 100 jobs `prova.progresso(duracao_s=0)` executados exatamente uma vez (tabela de prova conta 100, 0 duplicata) com `PLAT_WORKER_PROCESSOS=2` temporário; exceção → 3 tentativas com espera 2/4/8 s → `falhou` com traceback no log; `FalhaDefinitiva` sem retentativa; `chave` igual roda em série; job pesado nunca em paralelo com outro pesado | `jobs_vazios_por_min` (≥ 600) |
| `tests/api/test_jobs_progresso.py` (`lento`) | **job de 5 min** (`duracao_s=300, passos=60`): SSE recebe ≥ 60 eventos `estado` crescentes; atraso NOTIFY → cliente medido por timestamp no evento; heartbeat avança a cada ≤ 10 s | `latencia_progresso_s` (≤ 2), `tempo_job_5min_s` |
| `tests/api/test_jobs_cancelamento.py` | cancelar no passo 10 → `cancelado` em ≤ 2 s e a tabela de trabalho não sobra; cancelar pendente → imediato; cancelar concluído → 409; tipo que ignora a flag → morto em 30 + 10 s (`lento`); `timeout_s=5` → `falhou` "tempo esgotado" | `cancelamento_s` |
| `tests/api/test_jobs_reinicio.py` (`lento`) | no meio do job de 5 min: `sudo systemctl restart plat-worker` → job volta a `pendente` com `reinicios=1` e termina `concluido` com `tentativa=1`; depois `kill -9` no pai → filho morre (PDEATHSIG), ceifa na partida, `concluido` na retomada; 5 × `kill -9` → `falhou` "devolvido 5 vezes"; em nenhum momento `concluido` sem execução inteira (o job de prova grava um marcador no fim que o teste confere) | `reinicio_retomada_s` |
| `tests/api/test_jobs_memoria.py` | `prova.memoria(mb=600)` com `memoria_mb=256` → `falhou` "memória excedida"; worker continua vivo (`/saude` :8153 responde) | `rss_worker_kb` (`MemoryPeak` da unidade) |
| `tests/api/test_jobs_rls.py` | inquilino A não vê/cancela/repete job de B (404); `job_log` idem; sem contexto = 0 linhas; API nunca expõe `plat.worker`; usuário não-admin não vê job de outro usuário | — |
| `tests/api/test_jobs_agenda.py` | agenda `*/15 * * * *` com relógio do worker injetado (`PLAT_RELOGIO_TESTE`) dispara 3 vezes exatamente uma vez cada com 2 processos; 5 falhas pausam; `rodar-agora` cria job; cron inválida 422; cota de agendas 413 | — |
| `tests/api/test_saude.py` (estender) | `/saude` traz `servicos.worker = ok` e `fila.workers_vivos ≥ 1` | — |
| `tests/e2e/test_tarefas.py` (`lento`, `e2e`) | disparar `prova.progresso(60 s)` pela tela, ver a linha aparecer sem recarregar, progresso subir, concluir, link do resultado; cancelar outro; filtro por estado bate com a API; 0 erro de console; capturas `L0-05-jobs_lista.png`, `L0-05-jobs_detalhe.png`; lista com 1.000 jobs semeados pinta em ≤ 1 s | `primeira_pintura_tarefas_ms` |

O `make check` inteiro continua obrigatório (P3). Os testes `lento` de reinício precisam de `sudo systemctl`: o
`Makefile` ganha o alvo `e2e-worker` e o testador registra a saída literal.

---

## 13. Consequências e o que custa mudar

| decisão | custo de reverter |
|---|---|
| fila própria → Procrastinate | dois dias; `plat.job` e `@tarefa` ficam; psycopg 3 só no worker (seção 1.3) |
| um processo por job (fork) | trocar por thread perde limite de memória e kill por job; não há motivo medido para isso |
| `RLIMIT_DATA` em vez de `RLIMIT_AS` | uma constante em `filho.py`; `RLIMIT_AS` exigiria dobrar todo `memoria_mb` declarado |
| SSE principal, polling de reserva | desligar SSE = uma bandeira no front (o polling já existe) |
| croniter | trocar por parser próprio = 1 módulo + os mesmos testes de `test_cron.py` |
| relógio no worker, sem pg_cron | ligar pg_cron depois = 1 linha `cron.schedule` chamando `agenda_enfileirar`; nada muda no esquema |
| inquilino técnico `plataforma` para periódicos | alternativa (RLS com `tenant_id IS NULL`) exigiria política diferente em toda tabela; não se muda |
| estados finais imutáveis por gatilho | nenhum: é a garantia do portão ("nunca some", "nunca concluído sem execução") |
| `MemoryMax=2G` | editar a unidade e `daemon-reload`, com `free -g` e `MemoryPeak` medidos antes |
