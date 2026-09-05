# Changelog

Uma entrada por turno do laço PLATAFORMA ENTERPRISE. Números só de `tests/medidas/<item>.json` (com o comando que
os gerou) ou dos vereditos do adversário em `laco/handoffs/T<n>/<item>/refutacao.json`.

## 0.2.0 — turno 2, setembro de 2026 (itens L0-02-tenant-auth: identidade e acesso · L0-05-jobs: fila de trabalhos)

O produto passa a ter login com senha e segundo fator, sessão, usuários, grupos, papéis, tokens de serviço, log de
acesso e eventos por inquilino, superadmin em inquilino técnico, e uma fila de trabalhos com worker em processo
filho, progresso em tempo real, cancelamento, sobrevivência a reinício, agendas por cron e tela Tarefas. Nota: o
arquivo `VERSAO` ainda diz `0.1.0`; o gerente o sobe para `0.2.0` no fechamento do turno, junto com o `git_sha` de
`/saude` (o serviço no ar é `abbb03d`).

### O que entrou — identidade e acesso (L0-02, ADR 0002, migrações 003 e 009)

- Migração `003_identidade_acesso`: 46 privilégios com teto por perfil, papéis personalizados, colunas novas de
  `usuario` (segundo fator, bloqueio, pendências, origem), histórico de senha, grupos e membros, `evento` e
  `log_acesso` particionados por mês, inquilino técnico `plataforma` com 2FA obrigatório, funções `SECURITY DEFINER`
  reescritas com checagem de inquilino (`contexto_confere`) e superadmin por hash de sessão (`plataforma_operador`),
  `REVOKE EXECUTE FROM PUBLIC` em todas as funções e no privilégio padrão do schema.
- `app/auth/`: política de senha por inquilino (`tenant.config.auth`, padrões e faixas em `app/limites.py`), hash
  fantasma para tempo constante, bloqueio 5/15 min no banco, TOTP de biblioteca padrão com segredo cifrado
  (AES-GCM) e 8 códigos de recuperação, cookie `plat_sessao` com hash no banco e CSRF por `SameSite=Lax` + JSON +
  `Origin`, token de serviço `plat_…` com escopos, restrições de origem e IP, rotação de 24 h e revogação imediata,
  middleware que grava `plat.log_acesso` (bytes contados no fluxo) e redige segredos do journal, `X-Plat-Inquilino`
  só de leitura para o superadmin.
- 54 rotas do ADR mais `DELETE /api/plataforma/inquilinos/{id}` (migração 009: `tenant_apagar`), todas com
  `x-auth`, `x-privilegio`, `response_model` e evento declarado; erros no formato `{erro, mensagem, detalhe, req_id}`
  (`app/erros.py`); páginas em `app/paginas.py`.
- Sete telas sobre uma base reutilizável (`web/js/base/`: api, estado, i18n, dom, 6 componentes, layout;
  `style.css` tema único; DOMPurify 3.4.14 vendorizado com sha256): `/entrar`, `/conta`, `/admin/usuarios`,
  `/admin/grupos`, `/admin/papeis`, `/admin/tokens`, `/admin/log`; barra lateral por privilégio; página inicial com
  atalhos quando há sessão.
- Instalador: `plataforma/admin` semeado com superadmin, `demo`/`demo2` sem; 2FA reiniciado a cada instalação;
  partições de 4 meses; `plat_limites.conf` (10 r/min por IP em `/api/login` e `/api/login/2fa`); `Referrer-Policy`
  em toda `location`; limpeza de resíduos `zt-*` em `dev`; `python3-cryptography` conferido; `qrcode==8.2`.
- Testes: 5 unitários novos, 17 arquivos em `tests/api/` (varredura cruzada A→B gerada do OpenAPI com digest md5
  de todo o dado de B, força bruta, tempo constante, TOTP, token, funções seguras por `psql`, log de acesso por
  `User-Agent` único, eventos e privilégios declarados, inquilino temporário), 9 e2e playwright com captura mais
  `test_i18n_cru.py` (chave de tradução crua na tela reprova).

### O que entrou — fila de trabalhos (L0-05, ADR 0003, migrações 004, 006, 007, 008 e 010)

- Migração `004_jobs`: `job`, `job_log`, `worker`, `agenda`, RLS, gatilhos de estado final e de NOTIFY, funções do
  worker, cotas (`cota_jobs_simultaneos` 2, `cota_jobs_dia` 1.000, `cota_agendas` 50), schema `plat_trabalho`.
- `app/jobs/`: registro de tipos por decorador (`@tarefa`), worker com conexão própria, `LISTEN/NOTIFY`,
  `SKIP LOCKED`, heartbeat, "1 pesado por vez" por advisory lock, processo filho com `PR_SET_PDEATHSIG`,
  `RLIMIT_DATA`, BLAS em 1 thread e códigos de saída por causa, cancelamento cooperativo com escalonamento
  SIGTERM 30 s / SIGKILL +10 s, retentativa 2/4/8 s, teto de 5 reinícios, agendas por cron com fuso (croniter
  6.2.4) e relógio no worker, periódico `jobs.expurgo`, SSE `GET /api/jobs/{id}/eventos` com `Last-Event-ID`, 13
  rotas `/api/jobs*` e `/api/agendas*`, `/saude` com `fila` e `servicos.worker`, 6 tipos de diagnóstico.
- Unidade `plat-worker` (`Restart=always`, `KillMode=mixed`, `OOMPolicy=continue`, `MemoryMax=2G`), passo `h2` do
  instalador, chaves `PLAT_WORKER_*`, `PLAT_JOBS_DIR`, `PLAT_JOB_MAX_REINICIOS`, `PLAT_GPU_*`, `PLAT_DSN_WORKER`.
- Tela `/tarefas` (lista ao vivo por SSE com reserva por consulta, detalhe com log ao vivo, cancelar, repetir,
  baixar log, agendas) sobre a base da identidade; e2e `test_tarefas.py` com 5 provas e 3 capturas.
- Correções por achados do testador, cada uma com teste:
  - `006_jobs_transicoes` (commit `ad2ea29`): a role `plat_app` conseguia por SQL levar um job `pendente → rodando
    → concluido` com resultado forjado. Agora existe a role `plat_worker`, única com `EXECUTE` nas funções que
    mudam estado; `plat_app` perdeu `UPDATE` em `plat.job` (cancela por `job_cancelar`, reporta por
    `job_progresso`); gatilho `job_transicao` exige o GUC `via_worker` que só as funções do worker ligam;
    `jobs_expurgar` apaga marcadores e passos órfãos (1.371 acumulados antes).
  - `008_jobs_tentativa` (commit `90d03c0`): reinício e ceifa desfazem o incremento de `tentativa` feito por
    `job_pegar`; a retomada volta ao mesmo número (tentativa 1, reinícios 1). Testes de agenda robustos a resíduo
    de outras sessões.
  - `010_jobs_gatilhos_execute` (commit `7824846`): as três funções de gatilho da 004 nasceram com `EXECUTE` para
    `PUBLIC` e `plat_app` pelo privilégio padrão da 001; revogado (achado de `test_funcoes_seguras`).
  - `007_jobs_eventos` e integração com a identidade (commit `ffedc05`): `x-auth`/`x-privilegio` nas rotas da
    fila, eventos declarados, casos cruzados das 17 rotas.
  - `012_jobs_identidade_worker` e `013_jobs_execute_reafirma` (commit `9be9c6a`, depois do passe do cronista ter
    começado): identidade do worker por processo e ceifa só por heartbeat; `EXECUTE` do worker reafirmado contra o
    `GRANT ON ALL FUNCTIONS` da 011. Sem veredito do testador e do adversário neste turno.

### Medições (`tests/medidas/L0-02-tenant-auth.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| rotas no OpenAPI / com caso cruzado | 74 / 73 | `len(paths×methods)` de `docs/openapi.json`; casos em `tests/api/cruzado_casos.py` (o 74º caso entrou em `abbb03d`) |
| varredura cruzada viva: rotas, chamadas, 2xx indevidos, linhas de B alteradas | 73, 411, 0, 0 | `varredura_viva.py` do testador contra `/api/openapi.json` vivo, 6 vetores por rota; md5 das linhas de B como `postgres` |
| login (senha certa) | mediana 128,6 ms | 3 `POST /api/login` no TestClient (inclui pbkdf2 600.000) |
| login pela URL pública | 142,9 · 141,7 · 146,0 ms | 3 `POST /api/login` individuais (nginx + TLS) |
| login: 20 chamadas direto no uvicorn | mediana 129,2 · p95 145,4 · máx 156,6 ms | `testador_login_ms_20_uvicorn` |
| tempo constante (inexistente × senha errada) | 122,3 × 123,6 ms (TestClient); 121,7 × 123,2 ms (testador) | mediana de 4 e de 6 `POST /api/login` |
| autenticação por token | 3,0 ms (TestClient); 2,5 ms (testador) | mediana de `GET /api/eu` com Bearer menos `GET /api/versao` |
| custo de gravar `log_acesso` | 0,66 ms | mediana de 30 `GET /api/eu` com e sem `log_registrar` |
| revogação de token até o 401 | 0,01 s (TestClient) · 0,02 s (URL pública) · 6,2 ms (e2e) | `DELETE /api/tokens/{id}` e chamada seguinte |
| limite por IP no nginx | 10 × 401 depois 429 | 25 `POST /api/login` em 15 s de outro IP |
| RLS | 22 de 22 tabelas e partições com `tenant_id` | `pg_class × pg_attribute` |
| funções `SECURITY DEFINER` sem `PUBLIC` | 51 de 60 funções; 0 com `PUBLIC` | `pg_proc × aclexplode` |
| memória do `plat-api` | 122.781.696 bytes | `systemctl show plat-api -p MemoryCurrent` |
| páginas prontas (chromium) | login 54,3 · conta 37,8 · 2FA 9,7 · usuários 59,4 · grupos 60,8 · papéis 58,7 · tokens 78,9 · log 73,7 ms | `goto` até `body[data-pronto=1]` |
| e2e de identidade | 9 aprovados, 0 falhas | `make e2e` 16:03-16:27 UTC |
| marcadores de pendência / nomes de cliente | 0 / 0 | grep com a expressão do driver; grep da lista do testador |

### Medições (`tests/medidas/L0-05-jobs.json`, gerado às 17:28 UTC sobre `90d03c0`)

| medida | valor | comando |
|---|---|---|
| job de 5 min | 300,4 s; 62 eventos `estado`; heartbeat ≤ 5,0 s; latência heartbeat → cliente 0,065 s | `prova.progresso(300 s, 60 passos)` pelo SSE (`test_jobs_progresso.py`) |
| primeiro evento SSE pela URL pública | 0,022 s | `GET https://plat.iagrointel.com/api/jobs/{id}/eventos` até o primeiro `estado` |
| cancelamento cooperativo | 0,426 s (API) · 0,24 s (tela) | `POST .../cancelar` até `estado = cancelado`; clique até `tr[data-estado=cancelado]` |
| cancelamento de tarefa que ignora a flag | 40,5 s | pedido até SIGTERM (30 s) + SIGKILL (10 s) |
| retomada após `systemctl restart plat-worker` | 1,0 s | job volta a `pendente`/`rodando` com `reinicios = 1` (`test_jobs_reinicio.py`) |
| vazão de jobs vazios | 2.135,9 por min (2 workers, 3 processos) | 100 `prova.progresso(duracao_s=0)` (`test_jobs_fila.py`); só a unidade com 1 processo: 1.613,7 por min (`40_testes.md`, seção 6) |
| RSS do processo pai do worker | 40.556 kB | `GET :8153/saude` após o job de memória |
| tela Tarefas pronta | 142,9 ms | `goto('/tarefas')` até `body[data-pronto=1]` |
| linha nova sem recarregar | 10,3 s | `POST /api/jobs` até `tr[data-id]` |
| valores distintos de progresso na linha | 2 | leituras de `.c-progresso .valor` num job de 60 s |

### Vereditos

- **L0-02-tenant-auth: adversário PASSA em 2 rodadas** (`refutacao.json`). Rodada 1, não destrutiva, 16 famílias de
  ataque no serviço vivo: varredura A→B em 40 rotas por id (40 × 404, 0 cross 200), 8 listas sem vazamento, spoof
  por cabeçalho (403), token de B age só como B, 0 função com `PUBLIC`, GUC forjado (`so_superadmin`), força bruta
  (6ª = 423), TOTP e recuperação sem replay, tempo existente × inexistente (delta 2,7 ms em 60 amostras), fixação e
  encerramento de sessão, CSRF (403/415), escalada a superadmin (422/404), token (escopo, revogado, IP, não se
  perpetua), segredos fora do git e do journal, 0 marcador, 0 nome de cliente. Rodada 2, com reinstalação do zero
  (schemas e roles apagados, `install.sh` em 50 s, 63 s fora do ar): invariantes recriados, login real pelo
  navegador, nova varredura cruzada de 34 rotas sem cross 200. Gerente (`99_veredito.md`): todas as 7 cláusulas do
  portão passam; item **parcial** só porque P3 (suíte inteira verde) dependia da trilha B em curso e P9 (esta
  documentação) estava pendente; vira `entregue` no fechamento do turno se a suíte fechar verde.
- **L0-05-jobs: testador com correções 006/008/010 por achados** (`40_testes.md`, em escrita no fim deste passe).
  Cláusulas do portão medidas: job de 5 min com progresso em tempo real, cancelamento, sobrevivência a
  `systemctl restart` e a `kill -9` (nunca `concluido` sem execução inteira: marcador só no último passo; 5 × `kill -9`
  → `falhou`), 1 worker por padrão com limite de RAM declarado, tela Tarefas por inquilino com RLS varrida em 15
  rotas, testes automatizados. **Achado 2 aberto** (acrescentado ao portão em `estado.json`): um worker homônimo
  fora do systemd (nome padrão = host) fez `job_ceifar` devolver os jobs do worker vivo, que foram reexecutados do
  zero; o portão passa a exigir identidade de worker única por processo e ceifa só por heartbeat vencido, com teste
  de dois workers. O adversário do L0-05 ainda não rodou; o item foi devolvido a `pendente` pelo driver às 17:30 UTC
  (sessão do gerente interrompida). A correção entrou no commit `9be9c6a` (17:52 UTC), sem veredito ainda:
  migração `012_jobs_identidade_worker` (identidade `<nome-base>:<pid>`, ceifa só por heartbeat vencido do job e do
  worker dono, assinatura por nome removida; a partida não devolve nada por nome e um `kill -9` no pai é recolhido
  pela ceifa em até cerca de 90 s; `worker.py`, `test_jobs_identidade.py` com dois workers do mesmo nome-base) e
  `013_jobs_execute_reafirma`, motivada por outra regressão achada depois da reinstalação destrutiva: a
  `011_catalogo` (em construção) faz `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app` e devolvia a
  `plat_app` as funções do worker, inclusive `via_worker_ligar`, desfazendo a 006. Testador e adversário ainda não
  conferiram a correção; até lá o estado do item é o descrito acima.
- Ressalvas registradas: `auth_login`, `auth_sessao` e `auth_token` são pré-contexto por chave-segredo (o portão as
  cita como "checam o inquilino"; a checagem acontece na função seguinte, `auth_sessao_criar`); "expiração
  configurável" é por `tenant.config.auth`, não por `.env`; `X-Forwarded-For` só é confiável atrás do nginx
  (herdado ao L7-03); job devolvido 5 vezes mostra "tentativa 0"; com 1 processo a fila é serial e sem justiça
  entre inquilinos.

### Commits do turno

| sha | mensagem |
|---|---|
| `0985a11` | ADR 0002: identidade e acesso (T2, trilha A) |
| `1540c84` | ADR 0003: fila de jobs (T2, trilha B) |
| `1668d76` | Tela Tarefas (L0-05-jobs, trilha B, frontend): lista ao vivo por SSE, detalhe com log, agendas e e2e |
| `cab32da` | Fila de jobs (L0-05, trilha B): migração 004, registro de tipos, worker plat-worker, agendas e tipos de diagnóstico |
| `52d7a3b` | API da fila (L0-05): /api/jobs, /api/agendas, eventos SSE, páginas /tarefas, /saude com fila, testes de API |
| `674798d` | Unidade plat-worker e instalador (L0-05): passo h2, chaves PLAT_WORKER_* no .env, conferência de worker vivo |
| `57c24a5` | ADR 0004: catálogo de conteúdo (T2, preparação do L0-03) |
| `431ba0c` | Instalador (L0-05): inquilinos de demonstração com cota_jobs_dia = 100000 |
| `6a00645` | Base do front (L0-02-tenant-auth, trilha A): tema único, módulos ES de base, componentes, layout, i18n e DOMPurify |
| `50d587d` | Telas de identidade (L0-02-tenant-auth, trilha A, frontend): entrar, minha conta, usuários, grupos, papéis, tokens, log |
| `757f0d3` | e2e do L0-02-tenant-auth (playwright, chromium): login, 2FA, conta, usuários, grupos, papéis, tokens, log |
| `9be4a04` | Identidade (L0-02, trilha A, 1/4): migração 003, política, TOTP, escopos, redação, contrato de erro, limites |
| `2ffe8b4` | Identidade (L0-02, trilha A, 2/4): sessão, token, middleware de log_acesso, 54 rotas do ADR 0002, páginas |
| `b5c336b` | Instalador (L0-02): admin de plataforma com superadmin, demos sem, limite por IP nos logins, partições, cryptography |
| `ae6ec45` | Testes do portão L0-02: varredura cruzada A→B gerada do OpenAPI, força bruta, token, funções seguras, log_acesso |
| `441069c` | ADR 0005: ingestão vetorial (T2, preparação do L0-04) |
| `38430b2` | Medidas do item L0-02-tenant-auth (backend) |
| `ad2ea29` | Correção T2 da fila (L0-05, achados do testador): transições de estado só pelo worker; expurgo de marcadores |
| `ffedc05` | Integração T2 da fila com a identidade (L0-05 × L0-02): x-auth/x-privilegio, eventos e casos cruzados |
| `12b2c2e` | Medidas do testador para L0-02-tenant-auth (T2, 40) |
| `90d03c0` | Fila (L0-05): reinício não consome tentativa (008) e testes de agenda robustos a outras sessões |
| `7c62831` | Correção T2 do front (L0-02): componentes re-traduzem quando o dicionário chega; chaves conta.apos_pendencia e nav.tarefas_desc; e2e contra chave crua |
| `7824846` | Fila (L0-05): funções de gatilho da 004 sem EXECUTE para PUBLIC e plat_app (010) |
| `abbb03d` | Correção T2 do L0-02 (achados do testador): apagar inquilino, fixtures sem resíduo, log por chamada, Referrer-Policy em toda location |
| `41c1dd9`, `a06ca71` | Tela Conteúdo e e2e do L0-03-catalogo (outra trilha, em curso; documentada no passe do cronista desse item) |
| `7cd0327` | Documentação do turno 2 (cronista): MANUAL, ARQUITETURA, CHANGELOG 0.2.0, PARIDADE, README |
| `9be9c6a` | Correção T2 (2) da fila (L0-05, achado do testador): identidade do worker por processo e ceifa só por heartbeat (012, 013) |
| (este) | Documentação do turno 2, passe 2: absorve 012/013 e o commit 9be9c6a |

## 0.1.0 — turno 1, setembro de 2026 (item L0-01-repo: fundação)

Primeira versão. O repositório instala, sobe um serviço, responde saúde por HTTPS e isola inquilinos no
banco. Não há login, catálogo, camada nem mapa.

### O que entrou

- API FastAPI `plat-api` em 127.0.0.1:8150 (2 workers uvicorn, `MemoryMax=1G`), com `GET/HEAD /saude`
  (200 só com banco atualizado; 503 em `desatualizado`/`erro`), `GET/HEAD /api/versao`, página inicial
  `/` e `/api/docs`.
- nginx em `https://plat.iagrointel.com` com `X-Robots-Tag: noindex, nofollow` e
  `Strict-Transport-Security` em toda `location`, `/static/` servido do disco com `no-store`,
  redirecionamento de HTTP para HTTPS.
- Schema `plat` no banco `iagro_sat`: role `plat_app` (sem BYPASSRLS, sem posse), tabelas
  `versao_migracao`, `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS em toda tabela com
  `tenant_id` (USING e WITH CHECK); 9 funções `SECURITY DEFINER` para autenticação, sessão, token e log;
  inquilinos de demonstração `demo` e `demo2`.
- Migrações `001_fundacao` e `002_identidade`, aplicadas por `db/migrar.sh` com sha256 por arquivo,
  uma transação por arquivo e recusa (código 3) de arquivo aplicado que tenha mudado.
- `install.sh` idempotente (extensões, migrações, `.env` 600 com senha da role e `PLAT_GIT_SHA`, linha
  no `pg_hba.conf`, venv com `PYTHONNOUSERSITE=1` e prova de importação sem o diretório do usuário,
  administradores de demonstração com senha por stdin, unidade systemd, nginx com troca atômica
  preservando certbot, certbot na primeira vez, conferência pública de 200 + noindex + HSTS).
- `requirements.txt` com toda dependência da aplicação e da suíte fixada com `==` (`fastapi 0.138.0`,
  `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv 1.2.2`, `httpx 0.28.1`, ...); `uvicorn` e
  `psycopg2` do sistema, conferidos por nome de pacote dpkg.
- `make check`: ruff, varredura de marcador de pendência (inclui os `.md`), 81 testes rápidos (unit,
  instalador, dependências, vendor, contrato de `/saude`, `/api/docs`, banco, migrações, RLS, cabeçalhos
  HTTP reais) e 1 e2e playwright com captura; `make medidas` e `make vendor`.
- Front mínimo em módulos ES sem bundler; MapLibre GL JS 4.7.1 (ainda não carregado por nenhuma tela) e
  Swagger UI 5.32.15 (serve `/api/docs` sem CDN) em `web/vendor/`, versão no nome, sha256 e licença em
  `VERSOES.txt`; `favicon.svg`.
- Documentos: `docs/adr/0001-fundacao.md` (13 seções), `docs/openapi.json` gerado e comitado,
  `ARQUITETURA.md`, `MANUAL.md`, este arquivo, `README.md`; `docs/PARIDADE.md` só com cabeçalho (nenhuma
  capacidade de usuário para comparar ainda).

### Medições (`tests/medidas/L0-01-repo.json`, rodada 2 do testador sobre `8ffe950`, commit `3083366`; instalação e RLS da rodada 1)

| medida | valor | comando |
|---|---|---|
| instalação do zero (schema e role apagados) | 6,24 s | `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` (rodada 1) |
| reinstalação do zero pelo adversário sobre `8ffe950` | 9,66 s | `refutacao.json`, rodada 2, ataque 1 |
| instalação com `.env`, credenciais e linha do pg_hba também apagados | 9,14 s | idem; o script imprimiu `.env criado`, `linha acrescentada`, `tests/credenciais.txt criado` |
| instalação repetida em seguida | 4,69 s | idem; 0 migrações novas, 1 linha no pg_hba, NRestarts=0 |
| testes coletados / rápidos passando / e2e passando | 82 / 81 / 1 | `venv/bin/pytest --collect-only -q` (unit 31, api 50, e2e 1); `make check` |
| `make check` | rc=0, 2,86 s | `/usr/bin/time -f %e make check` |
| árvore suja depois de `make check` | 0 arquivos | `git status --short` |
| marcadores de pendência no código e nos documentos | 0 linhas | grep com a expressão do driver em `app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md` |
| nomes de cliente/parceiro no repositório | 0 linhas | `grep -rniE` com a lista do testador, fora de venv/.git/vendor |
| `/saude` pela URL pública | HTTP 200, `git_sha` = HEAD `8ffe950516f5`, 2 migrações, 0 pendentes | `curl -sSI` e `curl -sS https://plat.iagrointel.com/saude` |
| `X-Robots-Tag` com noindex | 11 de 11 rotas | `curl -sI` em API, estático, docs e 404 |
| `Strict-Transport-Security` | 11 de 11 rotas HTTPS; ausente no 301 de http | `curl -sI` |
| `/api/docs` sem URL externa; `make vendor` | 0 URLs; 4 arquivos OK | leitura do HTML; `sha256sum -c` |
| latência `/saude` pública, conexão nova (mediana / p95) | 19,8 / 21,0 ms | 20 × `curl -s -o /dev/null -w %{time_total}` |
| latência `/saude` pública, conexão reaproveitada (mediana / p95) | 1,9 / 2,8 ms | 20 URLs numa invocação de curl |
| memória do serviço (cgroup) | 88,5 MB | `systemctl show plat-api -p MemoryCurrent` |
| tabelas com `tenant_id` e RLS | 4 (mais `tenant` por `id`) | `pg_class × pg_attribute` |
| linhas visíveis a `plat_app` sem contexto | 0 | `psql` como `plat_app` sem `set_config` |
| página pronta / primeira pintura (chromium) | 62,6 / 48 ms | e2e `tests/e2e/test_saude_pagina.py` |

### Adversário (`laco/handoffs/T1/refutacao.json`): veredito final PASSA (rodada 2, HEAD `8ffe950`)

Rodada 1 (sobre `3b53c24`): PARCIAL. A refutação literal resistiu (apagar schema e role, reinstalar em
6,46 s, `/saude` 200 com noindex, 58 testes verdes), mas caíram: dependências `fastapi`, `starlette`,
`pydantic`, `python-dotenv` fora do `requirements.txt` (máquina nova não subia); senha de demonstração
em argumento de `sudo` (ficava no journal); documentos de topo vazios; sem `Strict-Transport-Security`;
Swagger de CDN externo; promessas do ADR sem código.

Rodada 2 (sobre `8ffe950`): PASSA. Reinstalação do zero em 9,66 s, 82 testes verdes, `/saude` 200 com
noindex e HSTS; os quatro achados reatacados e fechados com reprodução: aplicação importa e roda sem o
diretório do usuário (`PYTHONNOUSERSITE=1` na unidade viva); 0 senha no journal durante e depois da
reinstalação; ADR e código batem (`make medidas`, vendor com versão no nome, `PLAT_GIT_SHA` gravado,
`requirements.txt` completo, gravação em `log_acesso` adiada explicitamente ao L0-02); HSTS só no bloco
443 e `/api/docs` com 0 requisição externa em chromium real. Ressalvas que não derrubam o item: prova de
"máquina nova" por simulação; funções `SECURITY DEFINER` sem checagem de inquilino (regra para o L0-02);
caminhos do `install.sh` só lidos (`.env` inexistente, certbot emitindo, `nginx -t` reprovando).

### Commits

| sha | mensagem |
|---|---|
| `a1d0c20` | Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0) |
| `904a849` | Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes |
| `b22761e` | Medidas do item L0-01-repo regeneradas sobre o commit 904a849 |
| `ca61ea1` | Medidas do item L0-01-repo assinadas pelo testador (turno T1) |
| `3b53c24` | P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1 |
| `7092755` | Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0 |
| `8ffe950` | L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA |
| `3083366` | Medidas do item L0-01-repo, rodada 2 do testador sobre 8ffe950 |
| (este) | Documentação atualizada sobre 8ffe950 e 3083366 (passe curto do cronista) |
