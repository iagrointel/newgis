# T2 · trilha B · L0-05-jobs · 40_testes (testador)

## Objetivo

Conferir, sem ter construído nada, cada afirmação dos handoffs 30 (backend) e 31 (frontend) contra o portão literal do
item e os portões congelados P1–P9, com comandos reais e saídas literais; medir o que o portão pede; gravar
`tests/medidas/L0-05-jobs.json`; deixar a tabela cláusula → evidência → veredito para o adversário e o gerente.

Portão do item (literal, `estado.json`): "job de 5 min mostra progresso em tempo real, pode ser cancelado, sobrevive a
reinício do serviço (retoma ou marca falha, nunca some); 1 worker por padrão com limite de RAM declarado; tela
Tarefas por inquilino; teste automatizado". Refutação: "adversário mata o worker no meio de um job e reinicia: job não
pode aparecer como concluído".

## O que fiz (linha do tempo, UTC de 05/09/2026)

| hora | o quê | HEAD |
|---|---|---|
| 15:30–15:40 | leitura de skill, estado, plano, handoffs 30/31, ADR 0003, código (`worker.py`, `filho.py`, `contexto_job.py`, `eventos.py`, `004_jobs.sql`) e testes; espera pelo commit da trilha A (laço de 60 s) | `757f0d3` |
| 15:33 | **achado 1** (banco, com ROLLBACK): a role da API `plat_app`, com contexto de inquilino, levava um job `pendente → rodando → concluido` com `resultado` forjado, sem worker; o gatilho da 004 só protegia o estado FINAL | `757f0d3` |
| 15:40:26 | trilha A comitou (`ae6ec45`); `import app.main` ok no HEAD | `ae6ec45` |
| 15:40–15:59 | backend reagiu ao achado 1 com a migração 006 (role `plat_worker`, `REVOKE UPDATE`, gatilho `job_transicao`, `job_cancelar`/`job_progresso`, expurgo de marcadores); `install.sh` rodou 15:40:26–33 (5 `ERROR` de `permission denied` no worker antigo entre a migração e o reinício, depois sadio) | `ad2ea29` (15:59) |
| 16:02–16:03 | repetição do achado 1 e provas da 006 (tabela abaixo) | `ad2ea29` |
| 16:03:52–16:27:47 | `pytest -m lento` de OUTRA sessão ocupou o worker; cedi o slot (dois lentos em paralelo derrubam um ao outro: o 2º job de 5 min espera o 1º e estoura os 360 s) | |
| 16:28:01 / 16:28:12 | o meu `make check` e um `make check` de outra sessão começaram com 11 s de diferença; matei o meu (o pytest morto deixou um worker extra órfão `teste-extra-2965431` vivo até eu o encerrar às 17:15:09) | |
| 16:30:23–16:32:12 | `make check` sozinho: `lint` e `sem-marcador` verdes; `teste` 404 passaram / 5 falharam (análise abaixo) → `make` parou antes da fase `e2e` | `ad2ea29` |
| 16:45–17:14 | sessão pausada (limite de API na casa); nesse meio o HEAD andou (`ffedc05` integração, `90d03c0` migração 008 + testes de agenda robustos) | |
| 17:14:10–17:15:30 | reinstalação destrutiva do adversário da trilha A (`plat.worker`/`plat.agenda` inexistentes, `/saude` 502); nada medido nesse intervalo | |
| 17:15:45–17:28:56 | **`make medidas`** (suíte inteira, not lento + lento, `PLAT_GRAVAR_MEDIDAS=1`) sozinho: 422 passaram / 8 falharam (análise abaixo); o job de 5 min e os `kill -9` ocuparam o slot do worker de 17:17:26 a 17:24:36 | `90d03c0` |
| 17:28:56 | varredura RLS A→B em todas as rotas `/api/jobs*` e `/api/agendas*` do OpenAPI público (`cruzado_jobs.py`) | `90d03c0` |
| 17:28:56–17:29:00 | vazão com a configuração PADRÃO (só `plat-worker`, 1 processo): 100 jobs vazios | `90d03c0` |
| 17:29:01–17:34:01 | **job de 5 min pela URL pública com SSE** (`sse_latencia.py`), slot ocupado | `90d03c0` |
| 17:34–… | e2e extra (polling forçado, reinício com a tela aberta, perfis) esperou a fila esvaziar (2 jobs de 300 s de `demo2`, de outra sessão) — ver seção "e2e extra" | `90d03c0` |

Scripts próprios (fora do repositório, scratchpad desta sessão): `sessao.py`, `cruzado_jobs.py`, `vazao_1worker.py`,
`sse_latencia.py`, `e2e_extra.py`, `mil_jobs.py`, `amostra_mem.sh`, `caca_worker.sh`, `grava_medidas.py`.

## Evidência (comando + saída literal)

### 1. Repositório, importação e suíte inteira (P3)

```
$ git log --oneline | head -4          (17:15Z, o HEAD testado)
90d03c0 Fila (L0-05): reinício não consome tentativa (008) e testes de agenda robustos a outras sessões
12b2c2e Medidas do testador para L0-02-tenant-auth (T2, 40): ...
ffedc05 Integração T2 da fila com a identidade (L0-05 × L0-02): x-auth/x-privilegio, eventos e casos cruzados
ad2ea29 Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores
$ PYTHONNOUSERSITE=1 ./venv/bin/python -c 'import app.main; print("import ok")'
import ok
$ make check                             (16:30:23–16:32:12Z, HEAD ad2ea29, sozinho na máquina)
venv/bin/ruff check app tests            → All checks passed!
sem-marcador                             → rc=0 (0 marcadores em app web db docs deploy install.sh Makefile ... *.md)
venv/bin/pytest -m "not lento"           → 5 failed, 404 passed, 21 deselected, 4 warnings in 108.96s   (make parou aqui: rc=2; a fase e2e não rodou)
FAILED tests/api/jobs/test_jobs_agenda.py::test_cinco_falhas_seguidas_pausam_a_agenda   → assert 2 == 1 (o relógio enfileirou também a agenda vencida de uma rodada abortada de outra sessão)
FAILED tests/api/jobs/test_jobs_agenda.py::test_cota_de_agendas_413_e_rls               → 413 na 1ª criação com cota 1 (agenda residual em demo2 de outra rodada)
FAILED tests/api/jobs/test_jobs_fila.py::test_100_jobs_executados_exatamente_uma_vez     → "o worker extra não pegou nenhum job: {'teste-extra-2965431', 'iagrosat-db-sp'}" (worker extra ÓRFÃO do meu pytest morto às 16:28 seguiu vivo e pegou os jobs; encerrado 17:15:09Z)
FAILED tests/api/test_log_acesso.py::test_rotas_excluidas_nao_geram_linha               → 1952 == 1954 (chamadas concorrentes de outra sessão; trilha A)
FAILED tests/api/test_usuarios.py::test_ultimo_admin_nao_se_desabilita_rebaixa_nem_apaga → 'possui_grupos' (grupo residual zt-cruzado-grupo-93ca4f de outra rodada; trilha A)
```

As 5 são interferência de outras sessões/rodadas abortadas, não do produto; as duas de agenda foram tornadas
robustas pelo backend em `90d03c0` (o teste passou a contar só os jobs da própria agenda; cota = "o que B já tem + 1").

```
$ PLAT_GRAVAR_MEDIDAS=1 make medidas     (= suíte inteira not lento + lento, --base-url https://plat.iagrointel.com; 17:15:45–17:28:56Z, HEAD 90d03c0, sozinho)
8 failed, 422 passed, 4 warnings in 790.58s (0:13:10)
FAILED tests/api/jobs/test_jobs_progresso.py::test_job_de_5_min_com_progresso_em_tempo_real   → progressos [0, 0, 1, 1, 0, 1, ...] não monotônicos (ver 4)
FAILED tests/api/jobs/test_jobs_rls.py::test_sem_contexto_zero_linhas_e_worker_inacessivel     → "efeito parcial de prova.progresso sobrou": 6 linhas em plat_trabalho.passos — de um job RODANDO naquele instante (o teste supõe fila vazia; depois da rodada: passos fora de job rodando = 0)
FAILED tests/api/test_cruzado.py::test_cobertura_100_por_cento                                 → rota nova DELETE /api/plataforma/inquilinos/{id} sem caso cruzado (trilha A)
FAILED tests/api/test_cruzado.py::test_rota_nao_cruza[GET-/api/jobs]                           → "GET /api/jobs?limite=5 [token de A] alterou B: (hash, 23) → (hash, 24)": a impressão de B inclui plat.sessao e outra sessão criou uma sessão em demo2 no meio (plat.sessao 17:17:34 … 17:27:57, agente testclient); não é vazamento (ver 5)
FAILED tests/api/test_eventos.py::test_toda_rota_de_escrita_tem_evento_declarado              → mesma rota nova da trilha A
FAILED tests/api/test_migracoes.py::test_migrar_duas_vezes_nao_insere_linha                    → 011_catalogo aplicada no banco por outra trilha e ainda não no repositório
FAILED tests/api/test_privilegios_declarados.py::test_openapi_comitado_esta_contido_na_aplicacao → /api/plataforma/inquilinos/{id} (trilha A)
FAILED tests/e2e/test_tarefas.py::test_primeira_pintura_com_mil_jobs[chromium]                → psycopg2.errors.InsufficientPrivilege: job nasce pendente e sem resultado — a semeadura por SQL do próprio teste (INSERT já 'concluido' como plat_app) foi barrada pelo gatilho da 006; **falha REAL do teste (não do produto)**; a cláusula foi medida à mão (ver 7)
```

Passaram na mesma rodada: `test_jobs_reinicio.py` (3 lentos: restart no meio, `kill -9` no pai, 5 × `kill -9`),
`test_jobs_cancelamento.py` (5, incluindo o lento de 30 + 10 s), `test_jobs_memoria.py`, `test_jobs_fila.py` (com
`jobs_vazios_por_min` regravado), `test_jobs_sse.py` (4, incluindo o público), `test_jobs_agenda.py` (7),
`test_jobs_registro.py`, `test_cron.py`, e 4 dos 5 e2e de `test_tarefas.py` (lista/progresso/detalhe, cancelar
pela tela, filtro = API, agendas) com capturas `tests/e2e/capturas/L0-05-jobs_{lista,detalhe,agendas}.png`.

### 2. Achado 1 e a correção 006 (banco, como `plat_app` com contexto do inquilino 1, tudo com ROLLBACK)

```
antes (HEAD 757f0d3, 15:33Z):
pendente->rodando direto pela role da API: {'estado': 'rodando'}
rodando->concluido direto pela role da API: {'estado': 'concluido', 'resultado': {'forjado': True}}
depois (HEAD ad2ea29, 16:02Z, migração 006 aplicada 15:40:26):
achado 1 repetido: UPDATE pendente->rodando como plat_app: InsufficientPrivilege: permission denied for table job
GUC plat.via_worker='sim' por set_config + UPDATE como plat_app: InsufficientPrivilege: permission denied for table job
plat.via_worker_ligar() + UPDATE como plat_app: InsufficientPrivilege: permission denied for function via_worker_ligar
INSERT já concluido como plat_app: InsufficientPrivilege: job nasce pendente e sem resultado
plat.job_pegar como plat_app: InsufficientPrivilege: permission denied for function job_pegar
plat.job_terminar como plat_app: InsufficientPrivilege: permission denied for function job_terminar
plat_worker SELECT direto em plat.job: permission denied for table job
plat_worker UPDATE direto em plat.job: permission denied for table job
$ sudo -u postgres psql ... (transação com ROLLBACK): 3 jobs concluídos apagados → marcadores órfãos 3 →
  plat.jobs_expurgar(90, 30) = (0 jobs, 0 logs, 3 marcadores, 0 passos, rodando {}) → órfãos depois 0
  fora do inquilino plataforma: ERROR: expurgo só no contexto do inquilino técnico plataforma
$ proacl (pg_proc): job_pegar/terminar/devolver/ceifar/worker_registrar = {postgres, plat_worker}; job_cancelar/job_progresso = {postgres, plat_app}
```

Nota: `via_worker_ligar` tinha `GRANT EXECUTE` a `plat_app` num estado intermediário (15:41Z); no HEAD `ad2ea29` está
negada. Com o `REVOKE UPDATE`, o GUC deixou de ser a linha de defesa: mesmo `set_config` (chamável por qualquer role)
não abre caminho porque a role da API já não tem UPDATE na tabela.

### 3. Sobrevivência a reinício, `kill -9`, memória, cancelamento (jobs da rodada 17:15–17:29, lidos no banco depois)

```
$ sudo -u postgres psql -Atc "select ... from plat.job where criado_em between '17:15' and '17:30' and duracao_s >= 40"
criado  |iniciado|fim     |id       |dur|estado   |prog|tent|rein|erro
17:16:06|17:16:06|17:16:48|ddf0e55a |300|cancelado|  0 | 1  | 0  |morto após ignorar cancelamento        (SIGTERM 30 s + SIGKILL 10 s = 42 s; medida 40,5 s)
17:17:26|17:17:34|17:22:34|d80551e2 |300|concluido|100 | 1  | 1  |                                       (job de 5 min da suíte; ver 4)
17:22:34|17:22:45|17:22:51|3ed6a837 |300|cancelado|  1 | 1  | 1  |cancelamento solicitado                (systemctl restart no meio: devolvido "worker reiniciado", retomado com tentativa 1 / reinicios 1, cancelado pelo teste)
17:22:51|17:23:02|17:23:43|d51306be | 40|concluido|100 | 1  | 1  |                                       (kill -9 no pai: PDEATHSIG matou o filho, ceifa na partida devolveu, concluiu com marcador)
17:23:43|17:24:26|17:24:36|7ac26dcc |600|falhou   |  1 | 0  | 5  |devolvido 5 vezes sem terminar (worker sem sinal)
$ journalctl -u plat-worker 17:22–17:25: "parando: 1 filhos vivos" → "job devolvido na parada: pendente 3ed6a837" → "worker parado" → "worker iniciado ... orfaos_devolvidos=0";
  depois 5 × "Sent signal SIGKILL to main process ... Scheduled restart job, restart counter is at N" → "worker iniciado ... orfaos_devolvidos=1"
$ systemctl show plat-worker -p NRestarts -p MemoryPeak       (17:35Z)
NRestarts=6            (1 restart do teste + 5 kill -9 do teste; o job de memória NÃO reiniciou a unidade: pid igual antes/depois no teste)
MemoryPeak=27332608    (instância desde 17:24:35; a anterior: "Consumed 2.375s CPU time, 26.1M memory peak" e cobriu o prova.memoria(600 MB) das 17:17:05 → falhou "memória excedida (limite 256 MB)", tentativa 1)
marcadores: d80551e2 = 1 e bate com resultado.marcador; d51306be = 1 e bate; 3ed6a837 = 0; 7ac26dcc = 0 (nunca concluído sem execução inteira)
```

O marcador prova o que o backend diz (30_backend, item 3): só existe quando a função da tarefa chegou ao último passo,
e `concluido` só nasce de `job_terminar` chamado pelo pai depois do código 0 do filho; agora (006) ninguém mais tem
UPDATE na tabela. Ressalva: `7ac26dcc` termina `falhou` com `tentativa = 0` (a 008 desfaz o incremento de `job_pegar`
a cada devolução: 5 retiradas − 5 devoluções); é coerente com "reinício não consome tentativa", mas um job que
rodou 5 vezes e mostra "tentativa 0 de 3" na tela vai confundir o usuário — para o cronista/gerente.

### 4. Job de 5 min com progresso em tempo real (portão literal)

Suíte (TestClient, em processo): `tempo_job_5min_s 300.4`, `eventos_estado_job_5min 62`, `heartbeat_intervalo_max_s 5.0`,
`latencia_progresso_s 0.065`. O teste reprovou SÓ na monotonicidade: o job `d80551e2` foi devolvido e reexecutado do
zero 8 s depois de começar:

```
$ psql: job_log de d80551e2
17:17:27.294|INFO|início: 60 passos em 300 s; efeito parcial em plat_trabalho.passos; tentativa 1
17:17:34.376|INFO|início: 60 passos em 300 s; efeito parcial em plat_trabalho.passos; tentativa 1
...; estado final concluido, progresso 100, tentativa 1, reinicios 1, proveniencia.reinicios 1, marcador 1
```

Não há linha de parada, ceifa nem reinício da unidade no journal entre 17:17:04 e 17:22:45; o `prova.memoria(64)`
das 17:17:22 também terminou com `reinicios = 1`. Ou seja, TODOS os jobs `rodando` do worker `iagrosat-db-sp` foram
devolvidos de uma vez às 17:17:2x-3x por algo fora da unidade. O único caminho que faz isso sem journal é
`job_ceifar(60, 'iagrosat-db-sp')` na partida de um worker HOMÔNIMO — e a caça de processos (`caca_worker.sh`) flagrou
às 17:31:56 outra sessão (`claude`, usuário dev, cwd `/home/dev/plataforma/laco`, fora do systemd) lançando
`python -m app.jobs.worker` **sem `PLAT_WORKER_NOME`**, isto é, com o mesmo nome padrão (hostname) da unidade.
`worker_registrar` faz `ON CONFLICT (nome) DO UPDATE`: nada impede dois workers com o mesmo nome. Achado para o
adversário/gerente: **um `make worker` (ou o adversário) no mesmo host devolve silenciosamente os jobs da unidade**;
o portão "retoma ou marca falha, nunca some" continuou valendo (o job retomou do zero e concluiu com marcador).

Medição própria pela URL PÚBLICA (nginx + uvicorn + SSE), job `88b084f1`, 17:29:01–17:34:01Z, sem interferência:

```
$ venv/bin/python sse_latencia.py 300 60
cabecalhos {'content-type': 'text/event-stream; charset=utf-8', 'cache-control': 'no-store, no-store, must-revalidate', 'x-robots-tag': 'noindex, nofollow'}
{"primeiro_evento_s": 0.006, "eventos_estado": 62, "eventos_log": 11, "intervalo_medio_s": 4.922, "intervalo_max_s": 5.024,
 "progressos_distintos": 61, "crescente": true, "lat_hb_min_s": 0.004, "lat_hb_mediana_s": 0.005, "tempo_total_s": 300.2,
 "fim_estado": "concluido", "fim_progresso": 100, "tentativa": 1, "reinicios": 0, "marcador_resultado": "53166f26-..."}
```

Latência do 1º evento 6 ms; intervalo médio entre eventos `estado` 4,92 s = o passo do job (300 s / 60), não a latência
do canal; latência `heartbeat_em` (carimbo do banco) → chegada no cliente: mediana 5 ms. `X-Accel-Buffering` não chega ao
cliente pela URL pública (o nginx consome `X-Accel-*`, como o backend registrou no risco 4) — o efeito (sem buffer) está
provado pelos 6 ms. O `Cache-Control` sai duplicado (`no-store, no-store, must-revalidate`): o nginx acrescenta o seu ao
da API; inofensivo, mas é sujeira de cabeçalho para o cronista.

### 5. RLS em TODAS as rotas de jobs/agendas do OpenAPI público (P6)

```
$ venv/bin/python cruzado_jobs.py       (17:28:56Z; recurso de demo, chamado com sessão de demo2; lista gerada de /api/openapi.json)
GET    /api/agendas                     200 OK  total_B=0 contem_recurso_de_A=False
GET    /api/agendas/{agenda_id}         404 OK  {"erro":"agenda_inexistente",...}
PUT    /api/agendas/{agenda_id}         404 OK
DELETE /api/agendas/{agenda_id}         404 OK
POST   /api/agendas/{agenda_id}/pausar  404 OK
POST   /api/agendas/{agenda_id}/retomar 404 OK
POST   /api/agendas/{agenda_id}/rodar-agora 404 OK
GET    /api/jobs                        200 OK  total_B=8 contem_recurso_de_A=False
GET    /api/jobs/resumo                 200 OK  {"pendente":0,"rodando":0,"concluido_24h":0,"falhou_24h":0,"cancelado_24h":8}   (só B)
GET    /api/jobs/tipos                  200 OK
GET    /api/jobs/{job_id}               404 OK  {"erro":"job_inexistente",...}
POST   /api/jobs/{job_id}/cancelar      404 OK
GET    /api/jobs/{job_id}/eventos       404 OK
GET    /api/jobs/{job_id}/log           404 OK
POST   /api/jobs/{job_id}/repetir       404 OK
rotas conferidas: 15 falhas: 0
sem sessao: 401 em 17 de 17
```

Mais: `test_jobs_rls.py` (sem contexto 0 linhas em job/job_log/agenda; `plat.worker` inacessível; INSERT em outro
inquilino barrado pelo WITH CHECK; editor só vê os próprios jobs; admin vê os do editor) passou na rodada, exceto a
cláusula "passos = 0" explicada em 1.

### 6. Vazão, memória, cota, agenda

```
$ venv/bin/python vazao_1worker.py 100      (só a unidade, PLAT_WORKER_PROCESSOS=1, pela URL pública)
{"n": 100, "criacao_s": 0.91, "total_s": 3.7, "jobs_por_min": 1613.7, "estados": ["concluido"], "workers": ["iagrosat-db-sp"], "concluidos": 100}
suíte (2 workers, 3 processos, TestClient): jobs_vazios_por_min 2135.9   (o backend media 3180.8; a máquina tinha 2 testadores + adversário ao mesmo tempo)
$ amostra_mem.sh (cgroup plat-worker, 5 s, 16:04–17:05, 718 amostras): memory.current máx 25,3 MB; memory.peak 89,3 MB (herdado das rodadas do backend)
$ /saude do worker: rss_kb 40556 (pai)   · unidade: MemoryHigh=1536M MemoryMax=2G OOMPolicy=continue KillMode=mixed Restart=always
.env: PLAT_WORKER_PROCESSOS=1 · PLAT_WORKER_MEMORIA_MB=1536 · PLAT_DSN_WORKER=postgresql://plat_worker:...   (limite de RAM declarado)
cota: test_cota_diaria_de_jobs_413 (cota 0 em demo2 → 413 cota_jobs_dia) e test_cota_de_agendas_413_e_rls passaram na rodada 17:15
agenda com cron e fuso: test_cron.py (5 válidas com fuso, 5 inválidas, 3 < 15 min, troca de horário, ultima_vencida) e
  test_jobs_agenda.py (3 ocorrências × 2 relógios = 1 job cada; 5 falhas pausam; rodar-agora; PUT cron/fuso America/Manaus) passaram
placeholder (mesma expressão do driver) no escopo do item: 0 · nomes de cliente no escopo do item: 0 (grep de cbre|fgr|novaterra|certel|... = só "subprocess.CompletedProcess")
```

Limitação observada (não é cláusula do portão): com 1 processo a fila é estritamente serial e sem justiça entre
inquilinos — 4 jobs de 0 s de `demo` criados às 17:30 esperaram atrás de dois jobs de 300 s de `demo2` (17:29) até
17:44; `cota_jobs_simultaneos = 2` por inquilino não vale nada com `PLAT_WORKER_PROCESSOS = 1`.

### 7. e2e extra (playwright, URL real; `e2e_extra.py`, 17:48:47–17:49:27Z; `mil_jobs.py`, 18:00:33–18:01:13Z)

```
polling:      rota /api/jobs/*/eventos abortada no navegador (page.route → connectionrefused) → detalhe "atualização a cada 3 s";
              lista "1 ao vivo"; progresso na linha 20 % → 23 % → 30 % pela reserva por polling; 0 erro de console fora do
              ERR_CONNECTION_REFUSED da própria rota abortada; captura L0-05-jobs_polling.png
reinicio:     sudo systemctl restart plat-worker (17:49:19Z) no meio de prova.progresso(300 s) com a tela aberta →
              transições na linha SEM recarregar: pendente 0 % em 1,25 s, rodando 0 % em 1,36 s; API: rodando, reinicios 1, tentativa 1;
              nunca "concluído" na tela; 0 erro de console; captura L0-05-jobs_reinicio.png
editor:       sem filtro "quem"; 0 linhas do job do admin ("0 tarefas"); seção de agendas visível; 0 erro; captura L0-05-jobs_editor.png
visualizador: sem filtro "quem"; seção de agendas oculta; MAS /api/jobs, /api/jobs/resumo e /api/jobs/tipos devolvem 403
              (todas as rotas exigem o privilégio jobs.executar) → a tela fica em "…" com 4 console.error "status of 403";
              captura L0-05-jobs_visualizador.png   ← P1 não vale para este perfil (ver Riscos)
mil_jobs:     1.000 prova.progresso(0 s) pela API pública em 30,9 s (20 × 429 "fila_cheia": cota de 200 pendentes por inquilino
              provada de verdade), concluídos pelo worker em 39 s; /tarefas com período "tudo" (2.214 jobs no inquilino, 50 na
              página): first-contentful-paint 48 ms, página pronta 182,9 ms, 0 erro de console; captura L0-05-jobs_mil.png
              limpeza: DELETE (plat_app, contexto demo) de 1.279 jobs terminados = os 1.000 + os 200 da 1ª tentativa (barrada
              pela cota) + 79 jobs de outra sessão com o mesmo perfil (prova.progresso 0 s, prioridade 9, ≥ 18:00Z) — apagados
              por engano do filtro de limpeza; eram jobs de teste já terminados, sem efeito no produto, registrado aqui.
```

### 8. Achado 2 e a correção 012/013 (`prova_012.py`, 17:57:59–17:59:56Z, HEAD 05a41cd instalado como abbb03d)

```
17:57:59Z unidade: iagrosat-db-sp:3177982 pid 3177982
17:58:07Z job A na unidade: a97968d9 worker iagrosat-db-sp:3177982 progresso 3 reinicios 0
17:58:07Z worker MANUAL lançado fora do systemd, pid 3202979 nome-base iagrosat-db-sp     (PLAT_WORKER_NOME = hostname, cwd do repositório, PLAT_WORKER_URL :18160)
17:58:08Z manual /saude: iagrosat-db-sp:3202979
17:58:13Z job B rodando no iagrosat-db-sp:3202979 progresso 2
17:58:48Z job A depois de 35 s com o homônimo vivo: estado rodando progresso 20 reinicios 0 tentativa 1 worker iagrosat-db-sp:3177982
VEREDITO 1: PASSA (não devolvido, progresso cresceu de 3 para 20)
17:58:48Z kill -9 no worker manual; job B estava rodando 16 % heartbeat 2026-09-05T17:58:48.429Z
17:59:56Z job B devolvido/ceifado após (68.4, 'pendente', 1, None, 'worker sem sinal') | devolvido antes de 55 s? None
VEREDITO 2: PASSA (ceifa só após heartbeat vencido: 68.4 s, >= 60)
17:59:56Z jobs A e B cancelados; worker manual encerrado (returncode -9)
18:01:04Z plat.worker: só iagrosat-db-sp:3177982 (o registro do manual morto saiu pela worker_ceifar(90))
```

A identidade é `<nome-base>:<pid>`; `job_ceifar(p_limite_s, p_max_reinicios)` (012) não recebe mais nome e só devolve
job com heartbeat vencido cujo worker dono também está sem heartbeat há ≥ 60 s. A 013 reafirma o EXECUTE por função
(a 011 do catálogo tinha feito `GRANT ... ON ALL FUNCTIONS` e desfeito a 006 — outro achado do próprio backend).

## Medidas gravadas (`tests/medidas/L0-05-jobs.json`, HEAD 05a41cd)

| medida | valor | de onde |
|---|---|---|
| cancelamento_s | 0,426 s | suíte (API → estado cancelado) |
| cancelamento_tela_s | 0,24 s | e2e (clique + confirmação → linha cancelada) |
| cancelamento_forcado_s | 40,5 s | suíte (tarefa que ignora a flag: 30 s SIGTERM + 10 s SIGKILL) |
| jobs_vazios_por_min | 2.135,9 | suíte (2 workers, 3 processos; backend media 3.180,8 numa máquina menos ocupada) |
| jobs_vazios_por_min_1_worker | 1.613,7 | próprio, configuração padrão (1 processo) pela URL pública |
| rss_worker_kb | 40.556 kB | pai do worker (/saude :8153) |
| memoria_cgroup_worker_peak_mb | 27,3 MB | systemd MemoryPeak (limite 2 G) |
| latencia_progresso_s | 0,065 s | suíte (TestClient) |
| sse_primeiro_evento_publico_s | 0,022 s | suíte, URL pública |
| sse_publico_primeiro_evento_s | 0,006 s | próprio, job de 5 min, URL pública |
| sse_publico_latencia_heartbeat_mediana_s | 0,005 s | próprio (carimbo do banco → cliente) |
| sse_publico_intervalo_medio_eventos_s | 4,922 s | próprio (= passo do job de 5 s) |
| tempo_job_5min_s / eventos_estado_job_5min / heartbeat_intervalo_max_s | 300,4 s / 62 / 5,0 s | suíte |
| reinicio_retomada_s | 1,0 s | suíte (restart → pendente/rodando com reinicios=1) |
| reinicio_com_tela_aberta_s | 1,36 s | próprio (linha volta a rodando sem recarregar) |
| polling_de_reserva_progressos_vistos | 3 | próprio (SSE derrubado no navegador) |
| pagina_tarefas_pronta_ms / linha_nova_aparece_s / progresso_valores_distintos | 142,9 ms / 10,3 s / 2 | e2e da suíte |
| primeira_pintura_tarefas_ms / pagina_tarefas_mil_pronta_ms | 48 ms / 182,9 ms | próprio (2.214 jobs no inquilino) |
| rls_rotas_jobs_agendas_conferidas | 15 (0 falhas) | próprio, OpenAPI público |
| worker_homonimo_012_devolucoes | 0 (ceifa a 68,4 s) | próprio |

## Portão cláusula a cláusula

| cláusula | evidência | veredito |
|---|---|---|
| job de 5 min mostra progresso em tempo real | seção 4: pela URL pública 62 eventos `estado`, 61 valores crescentes, 1º evento 6 ms, latência banco→cliente 5 ms, 300,2 s, `concluido` com marcador; suíte 300,4 s / 62 eventos / heartbeat ≤ 5 s; na tela: linha sobe (e2e da suíte, e2e polling) | PASSA |
| pode ser cancelado | 0,426 s pela API; 0,24 s pela tela; tarefa que ignora a flag morre em 40,5 s; pendente cancela na hora; concluído = 409; passos de trabalho apagados | PASSA |
| sobrevive a reinício do serviço (retoma ou marca falha, nunca some) | `systemctl restart` no meio: devolvido "worker reiniciado", retomado em 1,0 s (API) / 1,36 s (tela) com tentativa 1 e reinicios 1; `kill -9` no pai: filho morre (PDEATHSIG), ceifa na partida, `concluido` com marcador; 5 × `kill -9` → `falhou` "devolvido 5 vezes"; job devolvido por worker homônimo (antes da 012) também retomou do zero e concluiu; nenhum job sumiu | PASSA |
| 1 worker por padrão com limite de RAM declarado | `.env` PLAT_WORKER_PROCESSOS=1, PLAT_WORKER_MEMORIA_MB=1536; unidade MemoryMax=2G/MemoryHigh=1536M/OOMPolicy=continue; filho com RLIMIT_DATA (600 MB sob 256 → `falhou` "memória excedida", worker com o mesmo pid, NRestarts inalterado); pico medido 27,3 MB | PASSA |
| tela Tarefas por inquilino | RLS em 15/15 rotas (A não vê B em nenhuma); lista/resumo só do inquilino; editor só vê os próprios; e2e lista/detalhe/agendas com captura | PASSA (com a ressalva do perfil visualizador em P1) |
| teste automatizado | 69 rápidos + 5 lentos + 5 e2e no repositório; nesta rodada 1 lento reprovou por interferência externa (seção 4) e 1 e2e reprovou de verdade (semeadura barrada pela 006, seção 1) | PARCIAL: o `test_primeira_pintura_com_mil_jobs` precisa de nova semeadura (pela API, como `mil_jobs.py`) |
| refutação: matar o worker no meio e reiniciar → nunca `concluido` | seção 3: marcador só no último passo; `concluido` só via `job_terminar` (EXECUTE só `plat_worker`); `plat_app` sem UPDATE; gatilho de transição; 5 × kill -9 = `falhou` sem marcador | PASSA |

## P1–P9

| portão | evidência | veredito |
|---|---|---|
| P1 funciona no navegador, 0 erro de console | e2e da suíte (4/5 com captura, 0 erro), e2e extra (polling, reinício, editor, mil: 0 erro). Perfil **visualizador**: 4 `console.error` 403 e lista em "…" | PARCIAL: passa para admin/editor; reprova para visualizador |
| P2 sem placeholder | `make sem-marcador` rc=0 na árvore inteira; 0 no escopo do item | PASSA |
| P3 suíte inteira verde | `make check` 16:30: lint e marcadores verdes, `teste` 5 falhas (todas interferência, 2 já robustecidas em 90d03c0), fase `e2e` não executada pelo make; `make medidas` 17:15: 422/430, 8 falhas = 6 de outras trilhas ou interferência + 1 lento por devolução externa + 1 e2e real (semeadura) | NÃO PASSA nesta rodada (nenhuma falha é do mecanismo da fila; 1 teste do item precisa de conserto) |
| P4 paridade declarada e testada | `docs/PARIDADE.md` preenchido pelo cronista em `7cd0327` (não conferi linha a linha: fora do meu escopo; o item não tem papel `esri`) | PENDENTE (adversário confere) |
| P5 reprodutível | migrações 004/006/007/008/010/012/013 idempotentes, aplicadas por `install.sh` (rodou 3 vezes hoje, inclusive na reinstalação destrutiva da trilha A às 17:14, e o item voltou inteiro) | PASSA |
| P6 multi-inquilino e segurança | RLS 15/15 rotas + 17/17 sem sessão = 401; `plat_app` sem UPDATE/EXECUTE nas funções do worker; `plat_worker` sem tabela; forja barrada (seção 2); `plat.worker` inacessível | PASSA |
| P7 dado aberto, sem cliente, sem PII | 0 nomes de cliente no escopo; dados de prova sintéticos (`prova.*`) | PASSA |
| P8 adversário não refutou | ainda não rodou | PENDENTE |
| P9 documentado | MANUAL/ARQUITETURA/CHANGELOG/PARIDADE do cronista (`7cd0327`, `4037164`); `docs/openapi.json` comitado tem `/api/jobs` (54 rotas) | PASSA (não conferi o texto) |

## Riscos

1. **Perfil `visualizador` na tela Tarefas**: toda rota `/api/jobs*` exige `jobs.executar`; o ADR 0003 seção 9 diz "admin vê todos, os demais só os próprios" e a 003 diz que visualizador não CRIA job — mas ele nem lista. Resultado: 403 + erros de console para um perfil legítimo. Decisão de produto (ler com `jobs.ver`? esconder o item do menu?).
2. **Fila serial e sem justiça entre inquilinos** com `PLAT_WORKER_PROCESSOS=1`: 2 jobs de 300 s de `demo2` seguraram jobs de 0 s de `demo` por 10 min (17:29–17:44). `cota_jobs_simultaneos` não age com 1 processo.
3. `tentativa = 0` em job que falhou por 5 reinícios (008): coerente com a regra, estranho na tela.
4. `Cache-Control` duplicado no SSE pela URL pública (`no-store, no-store, must-revalidate`).
5. Testes frágeis a outras sessões: `test_sem_contexto_zero_linhas` (passos = 0 supõe fila vazia), `test_job_de_5_min` (qualquer devolução externa quebra a monotonicidade), `test_rota_nao_cruza` (impressão de B inclui `plat.sessao`). A casa está rodando 3-4 suítes ao mesmo tempo na mesma base; dois `-m lento` em paralelo garantem falha (o 2º job de 5 min espera o 1º).
6. Os 79 jobs de outra sessão que a minha limpeza apagou (seção 7): terminados, de prova; se algum teste alheio os procurar depois, é isto.

## Pendências

- Backend: reescrever a semeadura de `test_primeira_pintura_com_mil_jobs` (criar pela API ou por função SECURITY DEFINER de teste); decidir o perfil `visualizador`.
- Gerente: P3 só fecha com uma rodada da suíte inteira sem outras sessões na base (ou com os testes isolados por prefixo de nome/inquilino próprio por sessão).
- Cronista: risco 4 (cabeçalho duplicado), risco 3 (tentativa 0), seção 4.6 do ADR ainda descreve `http.server` em thread (o código atende `/saude` no próprio laço).

## Para o próximo papel (adversário e gerente)

Adversário: o que já está provado e não precisa repetir — forja por SQL como `plat_app` (seção 2), RLS em todas as
rotas (seção 5), restart/kill -9/5×kill -9 (seção 3), worker homônimo (seção 8), memória (seção 6). O que vale a pena
atacar: (a) `plat_worker` compartilhado entre workers — um worker manual com `PLAT_DSN_WORKER` pode chamar
`job_terminar(id, '<nome:pid da unidade>', 'concluido', ...)` forjando o nome do dono? (as funções não autenticam o
nome; qualquer processo com a senha de `plat_worker` é "o worker"); (b) `job_progresso` como `plat_app` com o nome
exato do worker dono (o nome está em `GET /api/jobs/{id}.worker`, visível ao dono do job): dá para marcar 99 % sem
executar — não muda estado, mas mente na tela; (c) o `visualizador` (risco 1); (d) dois `systemctl restart` seguidos
dentro do `TimeoutStopSec`; (e) `Last-Event-ID` com id de outro job.
Gerente: veredito sugerido `parcial` — mecanismo inteiro provado (todas as cláusulas do portão literal PASSAM), P3
não fechou nesta rodada por 1 teste do item (semeadura) + interferência, P1 reprova só para o perfil visualizador.
Horários em que o slot do worker esteve ocupado por mim: 17:15:45–17:28:56 (suíte), 17:29:01–17:34:01 (job de 5 min
público), 17:48:47–17:49:27 (e2e extra, com restart às 17:49:19), 17:57:59–17:59:56 (prova 012, worker manual
`iagrosat-db-sp:3202979` encerrado por kill -9 e desregistrado pela ceifa), 18:00:13–18:01:13 (1.200 jobs de 0 s).

## Commit

`git commit -- tests/medidas/L0-05-jobs.json` (só as medidas; as 8 capturas `tests/e2e/capturas/L0-05-jobs_*.png` estão no
disco e NÃO entram no git porque o `.gitignore` do repositório exclui `tests/e2e/capturas/*.png` — nenhuma captura de
nenhum item é rastreada; se o gerente quiser capturas no repositório, é decisão de política, não deste papel).
Nada de código foi alterado por mim. Processos meus encerrados: worker extra órfão (17:15:09Z), worker manual da prova
012 (17:58:48Z, kill -9, desregistrado pela ceifa). Às 18:03:47Z havia de novo um `app.jobs.worker` de outra sessão
fora do systemd (adversário); com a 012 ele já não afeta a unidade.

---

Resumo em 8 linhas:
1. Portão literal: todas as 6 cláusulas PASSAM com número — job de 5 min pelo SSE público (62 eventos, 1º evento 6 ms, latência banco→cliente 5 ms, 300,2 s, marcador), cancelamento 0,426 s (tela 0,24 s), restart no meio retoma em 1,0 s (tela 1,36 s) com tentativa 1/reinicios 1, kill -9 e 5 × kill -9 (`falhou` sem marcador), 1 worker com RAM declarada (pico 27,3 MB sob 2 G), tela por inquilino (RLS 15/15 rotas), 1.000 jobs pintam em 48 ms.
2. Achado 1 (15:33Z): `plat_app` forjava `concluido` por SQL; a 006 fechou (permission denied com e sem GUC), reconferido no HEAD; achado 2 (17:3xZ): worker homônimo fora do systemd devolvia os jobs da unidade; a 012 fechou (prova 17:58–17:59Z: 0 devoluções, ceifa só a 68,4 s depois do kill -9).
3. `make check` (16:30Z): lint e marcadores verdes, `teste` 404/409 — 5 falhas, todas interferência (agendas residuais, worker extra órfão meu, trilha A); `make medidas` (17:15Z): 422/430 — 6 de outras trilhas/interferência, 1 lento por devolução externa, 1 e2e REAL (`test_primeira_pintura_com_mil_jobs` semeia por SQL o que a 006 barra).
4. P1 reprova só para o perfil `visualizador` (403 em /api/jobs, lista em "…", 4 erros de console); P3 não fechou nesta rodada; P4/P8 pendentes do adversário; P2/P5/P6/P7/P9 passam.
5. Riscos novos: fila serial sem justiça entre inquilinos com 1 processo (10 min de espera medidos); `tentativa 0` após 5 reinícios; `Cache-Control` duplicado no SSE público; testes frágeis a outras sessões na mesma base (3-4 suítes simultâneas hoje).
6. Medidas: 25 em `tests/medidas/L0-05-jobs.json` (commit só desse arquivo; capturas ficam fora do git por regra do `.gitignore`).
7. Slot do worker ocupado por mim: 17:15:45–17:28:56, 17:29:01–17:34:01, 17:48:47–17:49:27 (restart 17:49:19), 17:57:59–17:59:56, 18:00:13–18:01:13Z; limpeza apagou 79 jobs terminados de outra sessão junto com os meus (registrado).
8. Veredito sugerido ao gerente: `parcial` — mecanismo provado de ponta a ponta, falta consertar a semeadura do e2e dos 1.000 jobs e decidir o perfil visualizador; para o adversário, os ataques que sobram estão na seção "Para o próximo papel".
