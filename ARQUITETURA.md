# Arquitetura do `plat` (o que existe no fim do turno 2)

Este documento descreve o que está construído, instalado e testado no repositório
`/home/dev/plataforma/enterprise` no fim do turno 2 do laço PLATAFORMA ENTERPRISE (setembro de 2026): a fundação
do turno 1 (item L0-01), a identidade e o acesso (item L0-02) e a fila de trabalhos (item L0-05). Decisões e
motivos estão nos ADRs `docs/adr/0001-fundacao.md`, `0002-identidade-e-acesso.md` e `0003-fila-de-jobs.md`; aqui
está o resultado. O que ainda não existe está na seção final e em `/home/dev/plataforma/laco/PAINEL.md`, nunca
misturado ao que existe. O catálogo de conteúdo (item L0-03, ADR 0004, migração 011) está em construção por outra
trilha e é descrito aqui só onde já toca o banco.

Todo número citado vem de `tests/medidas/L0-01-repo.json` (turno 1), `tests/medidas/L0-02-tenant-auth.json` e
`tests/medidas/L0-05-jobs.json` (gerados às 17:28 UTC de 05/09/2026 sobre o commit `90d03c0`; as chaves
`testador_*` são medições próprias do testador feitas por `curl`, `psql` e `systemctl`), ou dos vereditos do
adversário em `laco/handoffs/T2/L0-02-tenant-auth/refutacao.json`, com o comando entre parênteses.

Estado: análise / beta privado. URL interna `https://plat.iagrointel.com`, `noindex` em toda resposta, nunca
linkada de lugar público.

---

## 1. Componentes e portas

| componente | porta | existe hoje | o que é |
|---|---|---|---|
| `plat-api` | 127.0.0.1:8150 | sim | FastAPI sob uvicorn, 2 workers, unidade systemd `plat-api` (`MemoryMax=1G`); 74 rotas em 55 caminhos no OpenAPI |
| `plat-worker` | 127.0.0.1:8153 (só `/saude`) | sim | processo pai da fila de jobs (`python -m app.jobs.worker`), unidade `plat-worker` (`MemoryMax=2G`); um processo filho por job |
| nginx | 443 / 80 | sim | `server_name plat.iagrointel.com`; `/static/` do disco; o resto em proxy para :8150; limite por IP nos logins; HTTP redireciona |
| PostgreSQL 16 + PostGIS 3.6 | 5432 | sim (banco `iagro_sat`, compartilhado) | schemas `plat` e `plat_trabalho`; roles `plat_app` (API e filhos) e `plat_worker` (processo pai da fila) |
| Garage (objetos S3) | 3900 | sim, serviço `plataforma-garage` já existente | só sondado por `/saude` |
| `plat-martin` (tiles vetoriais) | 8151 | sim (`plat-martin.service`, item L2-01-b) | valida token dentro da função SQL; `/_/metrics` nativo (item L7-06-a) |
| `plat-titiler` (tiles raster) | 8152 | **não existe** | porta reservada; `/saude` devolve `"titiler": "ausente"` |

Faixa reservada ao produto: 8150-8159. Serviços vizinhos da máquina que o `plat` nunca toca: 8125, 8126, 8091,
8127-8135, 8141.

Fluxo de uma requisição:

```
navegador --HTTPS--> nginx (443)
   /static/*                 -> disco: web/ (Cache-Control: no-store; noindex; HSTS; Referrer-Policy)
   = /api/login, /api/login/2fa -> limit_req zone=plat_login (10 r/min por IP, burst 10, 429) -> proxy :8150
   /                         -> proxy 127.0.0.1:8150 -> FastAPI
        páginas  /  /entrar  /conta  /admin/{usuarios,grupos,papeis,tokens,log}  /tarefas  /tarefas/{id}
        API      /saude  /api/versao  /api/login*  /api/logout  /api/eu*  /api/privilegios  /api/papeis*
                 /api/usuarios*  /api/grupos*  /api/tokens*  /api/log  /api/eventos  /api/plataforma/*
                 /api/jobs*  /api/agendas*  /api/docs  /api/openapi.json
plat-worker --LISTEN plat_worker--> banco --fork--> filho (plat_app, contexto do inquilino do job)
plat-api    --LISTEN plat_job-----> banco --SSE---> navegador (/api/jobs/{id}/eventos)
```

Memória medida pelo testador: `plat-api` 122.781.696 bytes no cgroup, mestre mais 2 workers
(`testador_plat_api_memoria_bytes`, `systemctl show plat-api -p MemoryCurrent`); processo pai do worker
40.556 kB de RSS (`rss_worker_kb`, lido em `GET :8153/saude` depois do job de memória).

---

## 2. Repositório

```
VERSAO                 versão (semver); lido por /api/versao
README.md · ARQUITETURA.md · MANUAL.md · CHANGELOG.md
install.sh             instalador idempotente (root), passos a-j (h2 = worker)
Makefile               check, check-rapido, lint, sem-marcador, teste, e2e, medidas, vendor, migrar, openapi, worker, e2e-worker
requirements.txt       42 linhas fixadas com == (aplicação e suíte); uvicorn e psycopg2 do sistema; qrcode 8.2, croniter 6.2.4,
                       python-dateutil 2.9.0.post0, six 1.17.0 entraram neste turno
.env.exemplo           todas as chaves (seção 10.1); .env real fora do git
app/
  main.py              aplicação; lista ROUTERS (uma linha por trilha); middleware de identidade; /api/docs
  settings.py · db.py (pool, contexto, somente_leitura) · log.py · versao.py · saude.py · senha.py
  erros.py             ErroAPI e os tratadores: {erro, mensagem, detalhe?, req_id}
  limites.py           padrões e faixas (identidade; a trilha do catálogo acrescentou a seção dela)
  paginas.py           PAGINAS: /entrar, /conta, /admin/usuarios, /admin/grupos, /admin/papeis, /admin/tokens, /admin/log
  auth/                politica.py, totp.py, redigir.py, escopos.py, privilegios.py (46 nomes), sessao.py (dependências),
                       middleware.py (X-Req-Id, log JSON, plat.log_acesso), modelos.py, comum.py,
                       rotas_login.py, rotas_eu.py, rotas_usuarios.py, rotas_grupos.py, rotas_tokens.py, rotas_log.py, rotas_plataforma.py
  jobs/                registro.py (@tarefa), contexto_job.py, filho.py, worker.py, agenda.py, periodicos.py, tipos_prova.py,
                       tipos.py, contexto.py (adaptador Auth -> Sessao), servico.py, eventos.py (SSE), rotas.py
db/
  migrar.sh            aplicador por sha256
  migracoes/           001 002 003 004 006 007 008 009 010 (011 em construção pela trilha do catálogo)
deploy/                plat-api.service, plat-worker.service, nginx.conf
web/
  index.html, login.html, conta.html, tarefas.html, admin/{usuarios,grupos,papeis,tokens,log}.html
  estilo/tokens.css + estilo/base.css + estilo/componentes.css (item L0-14; substituem style.css), tarefas.css, app.js, js/core.js
  js/base/             api.js, estado.js, i18n.js, dom.js, layout.js, componentes.js + componentes/{aviso,busca,dialogo,formulario,paginacao,tabela}.js
  js/auth/             sessao.js, login.js, conta.js, usuarios.js, grupos.js, papeis.js, tokens.js, log.js, comum.js
  js/jobs/             api.js, eventos.js, formato.js, util.js, lista.js, detalhe.js, agendas.js, tarefas.js
  js/i18n/pt-BR.json   dicionário (chave ausente aparece crua; o e2e test_i18n_cru.py reprova)
  vendor/              maplibre-gl 4.7.1, swagger-ui 5.32.15, dompurify 3.4.14; VERSOES.txt com sha256 e licença
docs/
  adr/0001 0002 0003 (0004 e 0005 são preparação de L0-03 e L0-04)
  openapi.json         gerado por make openapi, comitado; PARIDADE.md (tabela viva)
tests/
  conftest.py          fixtures: env, cliente, conexao_plat_app, base_url, medida
  unit/ api/ api/jobs/ e2e/   seção 10.3
  medidas/<item>.json  único lugar de onde documento cita número
  marcadores.regex · jobs_sessao.py · credenciais.txt (600, fora do git) · credenciais_totp.txt (600, fora do git)
  e2e/capturas/        PNG do e2e (fora do git)
var/jobs/              diretório de trabalho dos jobs (fora do git)
```

---

## 3. Banco: schemas `plat` e `plat_trabalho`

### 3.1 Roles

| role | quem a usa | pode |
|---|---|---|
| `plat_app` | API (`PLAT_DSN`) e o processo filho de cada job | `SELECT/INSERT/UPDATE/DELETE` nas tabelas de inquilino sob RLS; `EXECUTE` nas funções da aplicação; **sem `UPDATE` em `plat.job`** (migração 006); `CREATE` em `plat_trabalho` |
| `plat_worker` | processo pai da fila (`PLAT_DSN_WORKER`) | nenhum privilégio de tabela; `EXECUTE` só nas funções que mudam estado de job e de worker (`job_pegar`, `job_pid`, `job_heartbeat`, `job_terminar`, `job_devolver`, `job_ceifar`, `worker_*`, `agenda_vencidas`, `agenda_enfileirar`, `agenda_periodica_sincronizar`, `jobs_no_dia`) |
| `postgres` | migrações, `install.sh` | dono de tudo |

As duas roles são `LOGIN NOBYPASSRLS NOSUPERUSER`, sem posse de objeto (adversário, `pg_roles` e `pg_class`:
`rolsuper=f rolbypassrls=f`; dono de todas as tabelas = `postgres`). Linhas no `pg_hba.conf` acrescentadas pelo
`install.sh`, uma por role. Privilégio padrão do schema: função nova nasce com `EXECUTE` para `plat_app` e sem
`PUBLIC` (a 003 fez `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`); as três funções de
gatilho da 004, que nasceram antes disso, foram corrigidas pela 010. Regressão encontrada pela trilha da fila
depois da reinstalação destrutiva: a migração `011_catalogo` (em construção) faz `GRANT EXECUTE ON ALL FUNCTIONS IN
SCHEMA plat TO plat_app`, padrão copiado da 001, e devolve a `plat_app` o `EXECUTE` nas funções do worker, inclusive
`via_worker_ligar`, desfazendo a separação da 006; a correção `013_jobs_execute_reafirma` (commit `9be9c6a`, aplicada
às 17:51 UTC) reafirma o `EXECUTE` só de `plat_worker`, e a regra nova é "grant explícito por função, nunca
`ON ALL FUNCTIONS` depois da 006"
(`tests/api/jobs/test_jobs_transicoes.py::test_plat_app_nao_executa_as_funcoes_do_worker` é a rede de segurança).

Medido pelo testador (`testador_secdef_sem_public`, `pg_proc × aclexplode(proacl)`, 16:04 UTC): 51 funções
`SECURITY DEFINER` de 60 no schema, 0 com `EXECUTE` para `PUBLIC`, 0 com grantee fora de `plat_app`, `plat_worker`
e `postgres`. O adversário repetiu na instalação nova (17:15 UTC): 0 funções com `PUBLIC`, 27 tabelas, 60 funções,
25 políticas, 2 tabelas em `plat_trabalho` (antes da migração 011 do catálogo).

### 3.2 Tabelas e RLS

| tabela | tenant_id | RLS | conteúdo |
|---|---|---|---|
| `versao_migracao` | não | não | controle das migrações (só leitura para `plat_app`) |
| `tenant` | é o `id` | sim (`id = plat.tenant_atual()`) | inquilino: `slug`, `nome`, `ativo`, `config jsonb` (seção 4.7), `cota_bytes` |
| `usuario` | sim | sim | login, `senha_hash` (pbkdf2, 600.000 iterações), `perfil`, `papel_id`, `superadmin`, `origem`, `trocar_senha`, `falhas_login`/`falhas_desde`/`bloqueado_ate`, `totp_secret` cifrado, `totp_ativo`, `totp_ultimo_passo`, `codigos_recuperacao`, `desafio_2fa_hash`/`_ate`, `ultimo_login`, `ultimo_ip` |
| `sessao` | sim | sim | `token_hash` (sha256 do cookie), `criado_em`, `ultimo_uso`, `expira_em`, `ip`, `agente` |
| `token_servico` | sim | sim | `token_hash`, `prefixo`, `escopos text[]`, `restricao jsonb`, `expira_em`, `revogado_em`, `renovado_por`, `ultimo_uso`, `ultimo_ip` |
| `senha_historico` | via `usuario` | sim | os 5 últimos hashes por usuário |
| `privilegio`, `perfil_privilegio` | não | não | vocabulário de 46 privilégios e o teto por perfil (só leitura) |
| `papel_personalizado`, `papel_privilegio` | sim / via papel | sim | papéis por inquilino e seus privilégios |
| `grupo`, `grupo_membro` | sim | sim (leitura por visibilidade com `plat.tem`) | grupos, papéis de grupo (dono/gerente/membro), estado (ativo/convidado/pedido) |
| `log_acesso` (particionada por mês) | sim (nulo antes de autenticar) | sim, inclusive nas partições | uma linha por requisição autenticada; escrita só por `plat.log_registrar` |
| `evento_tipo` | não | não | vocabulário de eventos de domínio (identidade + fila) |
| `evento` (particionada por mês) | sim | sim | eventos append-only; escrita só por `plat.evento_registrar` (exige contexto) |
| `job` | sim | sim | fila (seção 5.1); `plat_app` sem `UPDATE` |
| `job_log` | sim | sim | linhas de log por job (teto 10.000; `linhas_log` contado por gatilho) |
| `worker` | não | não; `REVOKE ALL FROM plat_app` | workers vivos (nome, pid, versão, heartbeat, rss); leitura por `plat.fila_estado()` |
| `agenda` | sim | sim | agendamentos cron por inquilino |
| `plat_trabalho.passos`, `plat_trabalho.marcadores` | por `job_id` | não (schema de trabalho) | efeito parcial e marcador de fim das tarefas de prova; expurgados por `plat.jobs_expurgar` |

Medido pelo testador (`testador_rls`, `pg_class × pg_attribute`, 16:03 UTC): 22 de 22 tabelas e partições com
`tenant_id` têm `relrowsecurity = t`; `papel_privilegio`, `senha_historico` e `tenant` têm política por junção;
0 tabelas com `tenant_id` sem RLS. O adversário confirmou o mesmo na instalação nova.

### 3.3 Contexto por inquilino

A API define o inquilino da transação com `set_config('plat.tenant_id', ..., true)`, `plat.usuario_id` e
`plat.login` (`SET LOCAL`; a conexão volta ao pool sem contexto). `plat.tenant_atual()` e `plat.usuario_atual()`
leem esses valores; toda política de RLS os usa. `app/db.py`: `ThreadedConnectionPool(1, 8)` por worker; `db(ctx)`
repete só a preparação (até 9 vezes, descartando conexão morta), nunca a consulta; `somente_leitura` faz
`SET LOCAL transaction_read_only = on` (usado pela leitura do superadmin com `X-Plat-Inquilino`).

Limite escrito nos ADRs e provado pelo adversário: o contexto é um GUC que a própria role define; quem tem a senha
de `plat_app` escolhe o inquilino. A separação nova do turno 2 é entre quem executa tarefas (`plat_app`, dentro do
inquilino) e quem muda estado de job (`plat_worker`). Todo SQL da API é parametrizado e o contexto só é definido em
`app/db.py`.

---

## 4. Identidade e acesso (item L0-02, ADR 0002, migrações 003 e 009)

### 4.1 Modelo

Inquilino → usuário → perfil (`admin`, `editor`, `visualizador`, `campo`) = teto de privilégios e papel padrão →
46 privilégios em vocabulário fechado (`app/auth/privilegios.py` e `plat.privilegio`, o teste
`test_vocabulario_python_igual_ao_banco` compara os dois; 20 são administrativos e obrigam perfil `admin`) → papel
personalizado = subconjunto do teto → grupos com papéis dono/gerente/membro. `plat.privilegios_de(usuario)` e
`plat.tem(privilegio)` servem às rotas e às políticas. Toda rota declara `x-auth` e `x-privilegio` no OpenAPI
(`tests/api/test_privilegios_declarados.py` reprova rota sem declaração), e toda rota de escrita declara o evento
que registra (`tests/api/eventos_esperados.py`).

### 4.2 Sessão

Cookie `plat_sessao` = 64 hexadecimais gerados no banco por `plat.auth_sessao_criar`; o banco guarda só o sha256.
Atributos `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`. Validade absoluta `sessao_max_dias` (7) e
deslizante `sessao_ociosa_horas` (12), por inquilino; `plat.auth_sessao(hash, ociosa_horas)` atualiza `ultimo_uso`
só quando válida. Troca de senha, redefinição, desabilitação e desligamento do segundo fator pelo administrador
apagam todas as sessões do usuário (`plat.sessoes_encerrar_usuario`). CSRF: `SameSite=Lax` mais a exigência de
`Content-Type: application/json` em escrita sob cookie (`415`) e a conferência de `Origin` quando presente
(`403 origem_invalida`). Cookie e `Authorization: Bearer` juntos = `400 autenticacao_ambigua`. Pendências
(`trocar_senha`, `configurar_2fa`) limitam a sessão às rotas de conta (`403 pendencia`).

Adversário (rodada 1): fixação de sessão recusada (o login ignora cookie pré-existente e emite outro); usuário
desativado perde a sessão na hora; cookie após logout = 401; troca de senha por uma sessão derruba a outra.

### 4.3 Senha e bloqueio

Hash `pbkdf2_sha256$600000$...` (`app/senha.py`). Política em `app/auth/politica.py` lida de `tenant.config.auth`
com corte para a faixa; recusa nomeia a regra. Bloqueio por usuário no banco (`plat.auth_falha`: 5 falhas em 15 min
→ 15 min; `plat.auth_ok` zera), contado no banco porque a API tem 2 workers; falhas de TOTP e de código de
recuperação contam no mesmo contador. Usuário inexistente é conferido contra `HASH_FANTASMA` (gerado na partida)
para o tempo ser constante: medido 122,3 ms para inexistente contra 123,6 ms para senha errada
(`login_inexistente_vs_senha_errada_ms`); o adversário mediu 137,5 contra 140,2 ms em 60 amostras. Por IP, o nginx
limita `/api/login` e `/api/login/2fa` a 10 r/min com rajada 10 (`/etc/nginx/conf.d/plat_limites.conf`).

### 4.4 Segundo fator (TOTP)

RFC 6238, HMAC-SHA1, 30 s, 6 dígitos, janela de um passo, implementação de biblioteca padrão conferida contra o
vetor da RFC (`T=59 → 287082`, `tests/unit/test_totp.py`). Segredo de 20 bytes em base32, guardado como
`enc:v1:<base64(nonce + AES-GCM)>` com chave `sha256(PLAT_SECRET || "totp")` (`cryptography` do sistema).
Anti-replay por `totp_ultimo_passo`. Oito códigos de recuperação de uso único. Desafio de login com hash e validade
de 5 min no banco (`plat.auth_desafio_2fa_criar/resolver`), por isso funciona com 2 workers. QR em SVG gerado no
servidor por `qrcode==8.2` e inserido na tela por DOMPurify. `exigir_2fa` por inquilino vira pendência de sessão, não
expulsão.

### 4.5 Token de serviço

`plat_` + 43 caracteres; sha256 no banco; `prefixo` para a lista. Escopos fechados (`app/auth/escopos.py`),
restrições de origem e IP (`ipaddress`; o IP é `request.client.host` com `--proxy-headers` e
`--forwarded-allow-ips 127.0.0.1`, isto é, o `X-Forwarded-For` que o nginx local escreve; o adversário confirmou
que um `X-Forwarded-For` forjado pela URL pública devolve `401 ip_nao_permitido` e que o spoof só valeria se :8150
fosse exposto sem nginx). Validade padrão 90 dias, máximo 365; rotação com sobreposição de 24 h; revogação sem
cache. `plat.auth_token(hash, ip)` resolve o token e grava `ultimo_uso`/`ultimo_ip`. Latência medida: 3,0 ms
(`latencia_auth_token_ms`); revogação até o 401: 0,01 s (`tempo_revogacao_s`).

### 4.6 Log de acesso e eventos

`app/auth/middleware.py`: `X-Req-Id`, linha JSON no journal (com `Cookie`, `Authorization`, `senha`, `codigo`,
`desafio` e `token` redigidos por `app/auth/redigir.py`) e, depois do último byte da resposta, `plat.log_registrar`
com `bytes` contados no `body_iterator`, em `run_in_threadpool`. Rotas excluídas: `/saude`, `/api/versao`, `/`,
`/api/docs`, `/api/openapi.json`. `log_acesso` foi recriada pela 003 particionada por mês (`PARTITION BY RANGE (em)`,
chave `(id, em)`), com a guarda "só recria se `relkind = 'r'` e `count(*) = 0`" (o ramo `DROP + CREATE` rodou com 0
linhas, 13:45 UTC); `plat.log_particao_garantir(mês)` e `plat.log_expurgar(12)` cuidam das partições; o `install.sh`
garante 4 meses. Custo medido: 0,66 ms por requisição (`custo_log_acesso_ms`). O adversário contou 30.882 linhas com
0 valores de token ou cookie na rota e 1.481 linhas com `token_id`, nenhuma com `ip` ou `bytes` nulos.

`plat.evento` (particionada, append-only) recebe os eventos de domínio por `plat.evento_registrar` (exige contexto;
sem contexto, exceção). Vocabulário em `plat.evento_tipo`: identidade (`usuarios/*`, `papeis/*`, `grupos/*`,
`tokens/*`, `sessoes/revogar`, `inquilinos/*`, inclusive `inquilinos/leitura_superadmin` e `inquilinos/apagar`) e
fila (migração 007: eventos de `/api/jobs` e `/api/agendas`). `GET /api/eventos` e a aba Eventos da tela Log leem
por inquilino.

### 4.7 Superadmin e inquilino técnico `plataforma`

Só usuários do inquilino `plataforma` podem ter `superadmin = true` (gatilho `usuario_superadmin_so_plataforma`);
o inquilino nasce na 003 com `config.auth.exigir_2fa = true`. As funções `plat.tenant_criar`, `tenant_listar`,
`tenant_suspender`, `tenant_apagar` e `plataforma_tenant_id` recebem o hash da sessão e resolvem o operador por
`plat.plataforma_operador(hash)`, nunca por GUC (o adversário forjou `plat.usuario_id` e chamou `tenant_criar`:
`ERROR so_superadmin`). Rotas `/api/plataforma/*` respondem `404` a quem não é superadmin. Apagar inquilino
(migração 009): `plat.tenant_apagar_interno(id)` (só `postgres`; desliga o gatilho do último administrador dentro
da própria transação e apaga toda tabela com `tenant_id` em passes até as chaves estrangeiras fecharem) e
`plat.tenant_apagar(hash, id)` para o superadmin, recusando `plataforma`. `X-Plat-Inquilino` abre o contexto de
outro inquilino só para leitura em rotas marcadas e gera evento no inquilino lido.

`tenant.config.auth` (padrões e faixas em `app/limites.py`, `AUTH_PADROES`): `senha_min` 8 (8-64),
`senha_maiuscula`/`senha_minuscula`/`senha_simbolo` false, `senha_historico` 5 (0-24), `senha_expira_dias` 0 (0 ou
30-365), `bloqueio_tentativas` 5 (3-10), `bloqueio_minutos` 15 (5-60), `sessao_ociosa_horas` 12 (1-24),
`sessao_max_dias` 7 (1-30), `exigir_2fa` false, `token_max_dias` 365 (1-365), `token_padrao_dias` 90,
`dominios_email` [] (até 20), `compartilhar_publico` false (D24).

### 4.8 Funções `SECURITY DEFINER` da identidade

Todas de posse de `postgres`, `SET search_path = plat, public`, `EXECUTE` só para `plat_app`. Dois grupos:

- **Pré-contexto, chaveadas por segredo**: `auth_login(slug, login)` (filtra por `t.slug` e `u.login`, devolve o hash
  para a API comparar), `auth_sessao(hash, ociosa_horas)`, `auth_token(hash, ip)`, `auth_desafio_2fa_resolver(hash)`,
  `auth_sessao_encerrar(hash)`, `tenant_publico(slug)`, `plataforma_operador(hash)`. Rodam antes de haver inquilino
  na sessão; a chave é o próprio segredo.
- **Com contexto obrigatório**: `auth_sessao_criar`, `auth_falha`, `auth_ok`, `auth_desafio_2fa_criar`,
  `sessoes_encerrar_usuario`, `evento_registrar`, `log_registrar`, `log/evento_particao_garantir`, `tenant_*` de
  superadmin, `job_cancelar`, `job_progresso`, `jobs_expurgar`: chamam `plat.contexto_confere(usuario)` ou
  `plat.tenant_atual()`. Chamadas com contexto de `demo` sobre usuário de `demo2` falham com
  `contexto_de_outro_inquilino` (`tests/api/test_funcoes_seguras.py`; adversário por `psql` como `plat_app`).

### 4.9 LDAP/Active Directory (item L0-08-d-ldap, ADR 0008, migração 025)

Módulo isolado `app/auth/ldap.py` (`ldap3` puro Python, sem dependência de sistema): `POST /api/login/ldap`
faz bind de serviço opcional (ou anônimo) contra o diretório do inquilino → busca por `filtro_usuario` com o
login sempre escapado (`ldap3.utils.conv.escape_filter_chars`, RFC 4515 — sem isso `*)(uid=*` viraria um
filtro sempre-verdadeiro) → exige exatamente 1 resultado → bind do usuário com a senha informada (nunca com
senha vazia: corta antes de abrir qualquer conexão) → `memberOf` mapeado para 1 dos 4 perfis via
`plat.provedor_ldap.mapa_grupo_perfil` (maior alcance quando mais de um grupo mapeado bate,
`app.auth.privilegios.ORDEM_PERFIL`) → upsert em `plat.usuario` (`plat.ldap_provisionar`, nunca sobrescreve
conta `origem='local'` homônima: `409 login_em_uso_local`) → `plat.auth_login` de novo (mesmo formato do
login local) → **reaproveita** `app.auth.rotas_login._abrir_sessao` para abrir a sessão, sem duplicar
cookie/política/evento. Tabela `plat.provedor_ldap` (RLS por inquilino, como `papel_personalizado`): url,
base_dn, start_tls, bind_dn/bind_senha_cifrada (AES-GCM sob `PLAT_SECRET`, nunca texto puro), filtro_usuario,
atributo_grupos, perfil_padrao, mapa_grupo_perfil; `PLAT_LDAP_URL`/`PLAT_LDAP_BASE_DN` (env) são só o PADRÃO
usado quando a linha do inquilino não informa os seus. Rotas de administração (privilégio `org.integracoes`,
já reservado pela ADR 0002): `GET/PUT /api/org/ldap` (nunca devolve a senha de bind, só `tem_bind_senha`) e
`POST /api/org/ldap/importar` (grupo do diretório → usuários locais desabilitados, ativados no 1º login).
Força bruta contra o bind: contador em memória por processo, chave `(tenant_id, login)`, reaproveitando
`bloqueio_tentativas`/`bloqueio_minutos` da política do PRÓPRIO inquilino (cobre também login ainda não
provisionado localmente). Diretório de teste: contêiner Docker `glauth` efêmero (`tests/ldap_fixture/`, nunca
em produção), 4 usuários sintéticos + 1 conta de serviço, 3 grupos (um por perfil); 14 testes em
`tests/api/ldap/test_login_ldap.py` (marcados `lento`) provam bind OK com mapeamento de perfil, senha errada
recusada, injeção de filtro neutralizada, bind com senha vazia nunca tentado, força bruta bloqueada como o
login local, colisão com conta local recusada, importação em massa (desabilitado → ativo no 1º login), e o
portão duro do item: **desligar o contêiner LDAP não derruba o login local** (outra rota, outro caminho).

---

## 5. Fila de trabalhos (item L0-05, ADR 0003, migrações 004, 006, 007, 008, 010)

### 5.1 `plat.job`

Colunas principais: `id uuid`, `tenant_id`, `usuario_id` (nulo em job de agenda), `tipo`, `parametros jsonb`,
`estado` (`pendente`, `rodando`, `concluido`, `falhou`, `cancelado`), `prioridade` 1-9, `chave` (lock lógico: mesma
chave nunca roda em paralelo), `pesado`, `memoria_mb`, `timeout_s`, `executor` (`local`; `gpu` reservado ao L1-05),
`max_tentativas`, `tentativa`, `reinicios`, `agendado_para`, `agenda_id` + `programado_para` (UNIQUE),
`iniciado_em`, `heartbeat_em`, `terminado_em`, `worker`, `processo_pid`, `progresso` 0-100, `mensagem` (≤ 200),
`cancelar_solicitado`, `cancelado_por/em`, `resultado jsonb`, `erro`, `proveniencia jsonb` (versão, commit, GDAL
quando declarado, entradas com sha256, `repetido_de`, `reinicios`), `linhas_log`. Índices para a retirada
(`prioridade, agendado_para, criado_em WHERE pendente`), para a ceifa (`heartbeat_em WHERE rodando`), por inquilino e
por chave. `pesado`, `memoria_mb`, `timeout_s`, `executor` e `max_tentativas` são copiados do registro do tipo na
criação (o job é auditável depois que o código mudou).

### 5.2 Quem muda o quê (migração 006, achado do testador)

O testador provou, com `ROLLBACK`, que `plat_app` com contexto de inquilino levava um job `pendente → rodando →
concluido` com resultado forjado, sem worker (o gatilho da 004 só protegia o estado final). Correção em três
camadas, verificáveis por `tests/api/jobs/test_jobs_transicoes.py`:

1. role `plat_worker` (seção 3.1) é a única com `EXECUTE` nas funções que mudam estado; `plat_app` perdeu;
2. `REVOKE UPDATE ON plat.job FROM plat_app`: a API cancela por `plat.job_cancelar(id, usuario)` (pendente →
   cancelado; rodando → `cancelar_solicitado`; exige o contexto do inquilino do job) e o filho reporta por
   `plat.job_progresso(id, worker, pct, mensagem)` (só progresso, mensagem e heartbeat do job rodando deste worker e
   deste inquilino);
3. gatilho `plat.job_transicao` BEFORE INSERT OR UPDATE: job nasce `pendente` e limpo; entrar em `rodando`,
   `concluido` ou `falhou`, ou mudar `resultado`, `tentativa`, `reinicios`, `worker`, `iniciado_em`, `proveniencia`,
   `processo_pid`, exige o GUC `plat.via_worker = 'sim'`, ligado e desligado só dentro das funções do worker
   (`via_worker_ligar/desligar`, sem `EXECUTE` para ninguém além de `postgres`).

Depois da 006 o testador repetiu o ataque: `UPDATE` como `plat_app` = `permission denied for table job`; `INSERT`
já `concluido` = recusado pelo gatilho; `job_pegar`/`job_terminar` como `plat_app` = `permission denied`;
`plat_worker` com `SELECT` ou `UPDATE` direto em `plat.job` = `permission denied`.

### 5.3 Máquina de estados

```
pendente --(job_pegar: tentativa += 1)--> rodando --(job_terminar)--> concluido | falhou | cancelado
   ^                                          |
   |   job_devolver / job_ceifar (reinício, worker sem sinal; desfaz o incremento de tentativa: migração 008;
   |   reinicios += 1; reinicios >= PLAT_JOB_MAX_REINICIOS (5) --> falhou "devolvido 5 vezes sem terminar")
   +------------------------------------------+
pendente --(job_cancelar)--> cancelado
```

Exceção comum na tarefa: `job_devolver(conta_tentativa = true)` com espera `2^tentativa` s (2, 4, 8) até
`max_tentativas`, depois `falhou` com o traceback em `job_log` nível `ERRO`. `FalhaDefinitiva` (código 4): `falhou`
sem retentativa. `timeout_s`: SIGTERM, +10 s SIGKILL, `falhou "tempo esgotado"`. `MemoryError` (código 5) ou −9 pelo
cgroup: `falhou "memória excedida (limite N MB)"`. Estado final é imutável (gatilho `job_estado_final_imutavel`;
"repetir" cria job novo). Gatilhos `job_notificar` e `job_log_notificar` fazem `pg_notify` em `plat_job` (para o
SSE) e `plat_worker` (pendente novo, cancelamento).

Medido pelo testador na rodada 17:15-17:29 UTC (`40_testes.md`, seção 3, `psql` sobre `plat.job` e journal da
unidade): `systemctl restart plat-worker` no meio do job → devolvido "worker reiniciado", retomado com `tentativa 1`,
`reinicios 1` (`reinicio_retomada_s` 1,0 s); `kill -9` no pai → filho morto por PDEATHSIG, ceifa na partida
devolveu, concluído com marcador (medido em `90d03c0`; desde a migração 012 a partida não devolve nada por nome e o
job de um pai morto por `kill -9` é recolhido pela ceifa por heartbeat vencido em até cerca de 90 s); 5 × `kill -9` → `falhou "devolvido 5 vezes sem terminar (worker sem sinal)"`;
`prova.memoria(600)` com limite 256 MB → `falhou "memória excedida"` com o mesmo pid do worker antes e depois
(`NRestarts` da unidade só contou os reinícios do teste). O marcador de `prova.progresso` (gravado só no último
passo) existiu em todo job `concluido` e em nenhum `cancelado` ou `falhou`: nunca `concluido` sem execução inteira,
que é a refutação literal do item.

### 5.4 Worker (`app/jobs/worker.py`, unidade `plat-worker`)

Processo pai com conexão própria (`plat_worker`, autocommit, nunca o pool da API), `LISTEN plat_worker`, laço por
`select()` de até 1 s acordado também por self-pipe de `SIGCHLD`/`SIGTERM`. Por tick: `worker_heartbeat`; a cada
30 s `job_ceifar(60)`, `worker_ceifar(90)` e o relógio das agendas; para cada filho vivo `job_heartbeat` a cada 10 s
(devolve `cancelar_solicitado` → 30 s SIGTERM, +10 s SIGKILL) e o `timeout_s`; se há vaga (`PLAT_WORKER_PROCESSOS`,
padrão 1), `job_pegar(nome, pesado_ok)` com `pesado_ok = pg_try_advisory_lock(hashtext('plat.job.pesado'))`
("1 pesado por vez" por banco). Job recebido → `fork`. Parada por SIGTERM: devolve os filhos vivos
(`conta_tentativa = false`), SIGTERM ao filho, 20 s, SIGKILL, `worker_desregistrar`. Partida (migração 012, commit `9be9c6a`): identidade `<nome-base>:<pid>` (`nome_base` = `PLAT_WORKER_NOME` ou
nome do host) registrada em `plat.worker`; `job_ceifar(limite, max_reinicios)` devolve só job com heartbeat vencido
cujo worker dono também está sem sinal em `plat.worker` no mesmo prazo, nunca por igualdade de nome; dois workers com
o mesmo nome-base não roubam jobs um do outro (`tests/api/jobs/test_jobs_identidade.py`);
`agenda_periodica_sincronizar`. `GET 127.0.0.1:8153/saude` atendido no próprio
laço: `{worker, pid, versao, git_sha, processos, rodando[], pesado_em_curso, ultimo_tick_ms, rss_kb, em}`.

Processo filho (`app/jobs/filho.py`): `prctl(PR_SET_PDEATHSIG, SIGKILL)`; `OPENBLAS/OMP/MKL_NUM_THREADS =
threads_blas` (1); `resource.setrlimit(RLIMIT_DATA, memoria_mb)` (não `RLIMIT_AS`: numpy e OpenBLAS reservam
endereço por thread e travam sob 256/512 MB, medido no ADR); `app.db._pool = None`; SIGTERM vira `Cancelado` na
próxima checagem; conexão própria como `plat_app` sob `set_config('plat.tenant_id', <tenant do job>)` — o código
de qualquer tipo de job enxerga só o inquilino dono do job; `ContextoJob.progresso()` (no máximo 1×/s, chama
`plat.job_progresso`, levanta `Cancelado` quando pedido), `log()`, `entrada()`, `subprocesso()`, `db()`; códigos de
saída 0 concluído, 3 cancelado, 4 falha definitiva, 5 memória, 1 outra exceção; sempre `os._exit`. Trabalho longo
fica fora do bloco `with ctx.db()` porque o servidor tem `idle_in_transaction_session_timeout = 60 s`.

Unidade `deploy/plat-worker.service`: `Restart=always`, `RestartSec=3`, `TimeoutStopSec=40`, `KillMode=mixed`
(SIGTERM só ao pai; SIGKILL ao cgroup no timeout), `OOMPolicy=continue` (filho morto pelo OOM não derruba o
serviço), `MemoryHigh=1536M`, `MemoryMax=2G`, `Nice=5`, `PYTHONNOUSERSITE=1`. Limite de RAM declarado:
`PLAT_WORKER_MEMORIA_MB=1536` é o teto que o registro aceita para `memoria_mb`; tipo leve até 1024.

Registro de tipos (`app/jobs/registro.py`): `@tarefa(nome, descricao, parametros (pydantic), pesado, memoria_mb,
timeout_s, tentativas, chave, executor, versao, threads_blas, perfil_minimo, ferramentas)`; recusa na importação
nome repetido ou fora do padrão `a.b`, `memoria_mb` fora de `[128, PLAT_WORKER_MEMORIA_MB]`, `executor='gpu'` sem
`pesado` ou sem `PLAT_GPU_SSH`. `GET /api/jobs/tipos` expõe o registro com `parametros_schema`. Tipos deste turno:
`prova.progresso`, `prova.memoria`, `prova.falha`, `prova.ignora_cancelamento`, `prova.pesado`,
`prova.tempo_esgotado` e o periódico `jobs.expurgo`.

Vazão medida: 2.135,9 jobs vazios por minuto com 2 workers (unidade + worker extra do teste, 3 processos;
`jobs_vazios_por_min`, `tests/api/jobs/test_jobs_fila.py`); o testador mediu 1.613,7 por minuto só com a unidade,
1 processo, pela URL pública (100 jobs em 3,7 s, `vazao_1worker.py` no `40_testes.md`, seção 6).

### 5.5 Progresso em tempo real (SSE)

`GET /api/jobs/{id}/eventos` (`app/jobs/eventos.py`): um thread `LISTEN plat_job` por processo da API, iniciado na
primeira conexão, com fan-out por `job_id` em filas `asyncio`; rota `async` (não gasta token do threadpool).
Eventos `estado` (mesmo JSON do `GET /api/jobs/{id}`; o primeiro é sempre lido do banco), `log` (`{id, em, nivel,
mensagem}`, `Last-Event-ID` reenvia as linhas perdidas) e `fim`; keepalive a cada 15 s; conexão fechada em 30 min;
10 conexões por usuário por processo (`429`); job de outro inquilino = `404`. Cabeçalho `X-Accel-Buffering: no` é
enviado pela API e **consumido pelo nginx** (lista padrão de `proxy_hide_header`); o teste o confere direto em
`:8150` e mede o efeito pela URL pública: primeiro evento em 0,022 s (`sse_primeiro_evento_publico_s`). Latência do
heartbeat gravado pelo filho até o evento no cliente: 0,065 s (`latencia_progresso_s`); o testador mediu mediana de
5 ms pela URL pública num job de 300 s (`sse_latencia.py`, 62 eventos `estado`, 61 progressos distintos crescentes).
O front (`web/js/jobs/eventos.js`) cai para consulta a cada 3 s depois de dois erros seguidos e limita 10
assinaturas por página.

### 5.6 Agendas e periódicos

`plat.agenda`: nome único por inquilino, tipo, parâmetros, `cron` (5 campos, croniter 6.2.4), `fuso` (IANA,
`zoneinfo`), `ativa`, `proxima_em`, `ultima_em`, `ultimo_job_id`, `ultimo_estado`, `falhas_seguidas`, `expira_em`.
O worker é o relógio (a cada 30 s): `agenda_vencidas()` com `FOR UPDATE SKIP LOCKED` → `agenda_enfileirar` (a
ocorrência vencida mais recente; `UNIQUE (agenda_id, programado_para)` como segunda trava; sem recuperar atraso);
5 falhas seguidas → `ativa = false`. Limites: intervalo mínimo 15 min, `cota_agendas` 50 por inquilino,
`cota_jobs_dia` 1.000 (checada no `POST /api/jobs` com `413` e pelo relógio). `pg_cron` não é usado. Periódicos da
plataforma vivem em código (`app/jobs/periodicos.py`) e são sincronizados para `plat.agenda` do inquilino
`plataforma` na partida do worker: neste turno só `jobs.expurgo` (`30 3 * * *` America/Sao_Paulo: apaga `job` > 90
dias, `job_log` > 30 dias, diretórios órfãos > 7 dias e marcadores/passos órfãos de `plat_trabalho`; só roda no
contexto de `plataforma`). `PLAT_RELOGIO_TESTE` substitui `now()` do relógio só em `PLAT_AMBIENTE=dev`
(`tests/api/jobs/test_jobs_agenda.py`: 3 ocorrências com 2 relógios = 1 job cada).

### 5.7 API da fila

`GET/POST /api/jobs`, `GET /api/jobs/resumo`, `GET /api/jobs/tipos`, `GET /api/jobs/{id}`, `POST .../cancelar`
(`202`), `POST .../repetir` (`201`), `GET .../log`, `GET .../eventos`; `GET/POST /api/agendas`,
`GET/PUT/DELETE /api/agendas/{id}`, `POST .../pausar`, `.../retomar`, `.../rodar-agora`; páginas `/tarefas` e
`/tarefas/{id}`. Todas exigem sessão ou token com `jobs.executar`; `jobs.gerir_todos` vê o inquilino inteiro;
o perfil mínimo do tipo é checado além do privilégio (`403 perfil_insuficiente`). Erros no formato de `app/erros.py`.
O testador varreu as 15 rotas por id com sessão de outro inquilino: 15 × `404`, 0 vazamento em lista, 17 × `401`
sem sessão (`cruzado_jobs.py`, `40_testes.md` seção 5).

### 5.8 Worker em contêiner (item L0-05-e, ADR 0010) — quando usar cada executor

O worker existe em DOIS executores possíveis para a MESMA fila: a unidade systemd `plat-worker` (padrão,
seção 8) e um contêiner Docker (`deploy/Dockerfile.worker` + `deploy/docker-compose.worker.yml`). Não é uma
substituição — é o mesmo pai, os mesmos filhos por fork() com `RLIMIT_DATA`, a mesma tabela `plat.job`; os
dois podem rodar ao mesmo tempo apontando para o mesmo banco (`job_pegar` com `FOR UPDATE SKIP LOCKED` já
resolve dois workers concorrentes, seção 5.3), desde que tenham `PLAT_WORKER_NOME` e porta de saúde distintos.

| | unidade systemd (padrão) | contêiner (`--worker-container`) |
|---|---|---|
| quando usar | produção hoje; menor superfície, `install.sh` já instala e verifica | quando o item que pede exigir isolamento de recursos POR EXECUÇÃO que uma unidade única não separa (hoje `MemoryMax=2G` é do worker inteiro, não por job — ex.: L2-16-b/c, um contêiner por job) ou uma imagem versionada para rodar noutra máquina sem repetir `install.sh` inteiro |
| dependências Python | `--system-site-packages` reaproveita dpkg (psycopg2/GDAL/cryptography/magic do sistema, Python 3.12 = o do host) | tudo via pip na própria venv (a base `python:3.12-slim` é Debian bookworm, Python de sistema 3.11 — apt e venv não combinam); só `gdal-bin`/`libmagic1`/`ca-certificates` continuam vindo de apt |
| rede | acesso direto (mesma máquina) | `network_mode: host` (Postgres/Garage só escutam 127.0.0.1; uma rede em ponte chegaria de outro IP e nem autenticaria — seção 3 do ADR 0010) |
| segredos | `LoadCredential=` do systemd (ajusta dono/ACL para o usuário da unidade) | os MESMOS arquivos (`/etc/plat/segredos/*`) montados como `secrets:` do Compose; como o Compose preserva o dono/permissão de origem (root:600), o contêiner PARTE como root e `deploy/entrypoint-worker.sh` lê os segredos e solta o privilégio (`setpriv`) antes de rodar uma linha do worker — o worker nunca roda como root |
| memória | `MemoryHigh=1536M`/`MemoryMax=2G` na unidade | `mem_limit`/`memswap_limit: 2g` no Compose — MESMO mecanismo de cgroup v2; `app/jobs/filho.limite_memoria_cgroup_mb()` lê o teto de qualquer um dos dois sem distinguir código e nunca deixa um filho pedir mais `RLIMIT_DATA` do que o cgroup tem (reserva fixa de 96 MB) |
| paridade Esri | nenhuma (não aplicável) | nenhuma (não aplicável) |

**O que a containerização corrigiu** (bug pré-existente, só aparece em contêiner): `app/jobs/filho._pdeathsig()`
decidia "meu pai morreu" checando `os.getppid() == 1`, certo fora de contêiner (reparentado para o init do
sistema) mas **sempre falso dentro de um contêiner sem `--init`, onde o próprio worker roda como PID 1** —
100% dos jobs falhavam, imediatamente, sem log. Corrigido comparando contra o PID que era o pai medido ANTES
do `fork()` (ADR 0010 seção 4), correto nos dois ambientes.

**Instalação**: `sudo bash install.sh <dominio> [porta] [--worker-container]`. Sem a flag, nada muda (só a
unidade systemd, como sempre). Com ela, ALÉM da unidade systemd (nunca no lugar dela), builda e sobe o
contêiner com `PLAT_WORKER_NOME=worker-container` e `PLAT_WORKER_URL=http://127.0.0.1:8155` (8154/8158 são
permanentes do ambiente de homologação, `docs/HOMOLOGACAO.md`; 8151/8152 de `martin`/`titiler`, reservadas).
Exige `docker`/`docker compose` (plugin v2) já instalados — o script confere e para com mensagem clara, nunca
instala Docker sozinho.

---

## 6. Migrações

Arquivos `db/migracoes/NNN_nome.sql`, idempotentes, sem `BEGIN/COMMIT` (o aplicador `db/migrar.sh` abre uma
transação por arquivo, registra o sha256 em `plat.versao_migracao` e para com código 3 se um arquivo aplicado
mudou). O número é escolhido na hora de criar o arquivo (regra do turno 2, depois de uma colisão); 005 não existe
(número reservado no plano e não usado). Estado ao vivo em 05/09/2026 17:54 UTC: 12 aplicadas, 0 pendentes,
`ultima_migracao = 013_jobs_execute_reafirma`; `git_sha` de `/saude` ainda `abbb03d` (API sem reinício desde então;
o worker já roda `a06ca71`).

| migração | sha256 (`sha256sum db/migracoes/*.sql`, igual ao da tabela) | o que faz |
|---|---|---|
| `001_fundacao` | `74fcdc90a28c…` | schema `plat`, role `plat_app`, `versao_migracao`, `tenant_atual()`, `usuario_atual()`, grants e privilégios padrão |
| `002_identidade` | `418736611e8a…` | `tenant`, `usuario`, `sessao`, `token_servico`, `log_acesso`; RLS; 9 funções `auth_*`; inquilinos `demo` e `demo2` |
| `003_identidade_acesso` | `725192af189b…` | 46 privilégios e tetos por perfil; papéis personalizados; colunas novas de `usuario`; `senha_historico`; grupos e membros; gatilhos do último administrador, do superadmin só em `plataforma` e da coerência de grupo; `evento_tipo` e `evento` particionada; `log_acesso` recriada particionada (guarda `count(*) = 0`); inquilino `plataforma` com 2FA obrigatório; funções `SECURITY DEFINER` reescritas com `contexto_confere`, `plataforma_operador`, `tenant_publico`; `REVOKE EXECUTE FROM PUBLIC` em todas e no privilégio padrão |
| `004_jobs` | `ddc21b358ed9…` | `job`, `job_log`, `worker`, `agenda`; RLS; gatilhos de estado final e de NOTIFY; funções do worker, cotas, `fila_estado`, agendas; schema `plat_trabalho` com `passos` e `marcadores` |
| `006_jobs_transicoes` | `3b181c883a16…` | role `plat_worker`; `REVOKE UPDATE` em `job` para `plat_app`; `job_cancelar`, `job_progresso`, gatilho `job_transicao` com `via_worker`; `jobs_expurgar` apaga órfãos de `plat_trabalho` (achado 1 do testador) |
| `007_jobs_eventos` | `558bc552b15c…` | vocabulário de eventos da fila em `evento_tipo` (integração com a identidade) |
| `008_jobs_tentativa` | `92357250951c…` | devolução por reinício ou ceifa desfaz o incremento de `tentativa` feito por `job_pegar` (reinício não consome tentativa) |
| `009_inquilino_apagar` | `68f4506b5a41…` | `tenant_apagar_interno` (só `postgres`) e `tenant_apagar` (superadmin por hash de sessão); rota `DELETE /api/plataforma/inquilinos/{id}` (achado do testador: inquilinos de teste sem rota de apagar) |
| `010_jobs_gatilhos_execute` | `ef54d52b29c5…` | revoga `EXECUTE` de `PUBLIC` e `plat_app` nas três funções de gatilho da 004 (achado de `test_funcoes_seguras`) |
| `011_catalogo` | `9da0bf91dfa3…` (arquivo em disco, 17:54 UTC) | catálogo de conteúdo do item L0-03 (ADR 0004): `item`, `tipo_item`, versões, relações, compartilhamento, busca, pastas, categorias, favoritos, lixeira. **Em construção por outra trilha: aplicada no banco (17:26 UTC), ainda não comitada**; o sha da tabela (`b997b0c26d8a…`, reaplicada 17:42 UTC) já difere de novo do arquivo em disco (`9da0bf91dfa3…`) porque a trilha continua editando; o aplicador vai exigir o registro certo antes do commit dela |
| `012_jobs_identidade_worker` | `a5ff04ed9343…` (commit `9be9c6a`, aplicada 17:40 UTC) | achado 2 do testador do L0-05: identidade do worker passa a `<nome-base>:<pid>`, registrada em `plat.worker`; `job_ceifar(limite, max_reinicios)` devolve só jobs com heartbeat vencido cujo worker dono está sem sinal, nunca por igualdade de nome; a assinatura por nome foi removida |
| `013_jobs_execute_reafirma` | `81b94d28421c…` (commit `9be9c6a`, aplicada 17:51 UTC) | reafirma `EXECUTE` só para `plat_worker` nas funções que mudam estado, desfeito pelo `GRANT ... ON ALL FUNCTIONS` da 011 (seção 3.1) |

`tests/api/test_migracoes.py` roda o aplicador duas vezes e exige 0 linhas novas; enquanto a 011 estiver aplicada
sem estar no repositório em estado final, esse teste falha (registrado pelo testador do L0-05).

---

## 7. `install.sh`

Uso: `sudo bash install.sh <dominio> [porta]`. Root, idempotente, `set -euo pipefail`. Passos a-j descritos no
`MANUAL.md` seção 11.2; o que mudou no turno 2:

- d: `.env` ganha `PLAT_WORKER_URL`, `PLAT_WORKER_PROCESSOS`, `PLAT_WORKER_MEMORIA_MB`, `PLAT_DSN_WORKER`; a senha
  de `plat_worker` é gerada e realinhada a cada execução (`ALTER ROLE` por stdin), como a de `plat_app`.
- e: segunda linha no `pg_hba.conf`, para `plat_worker`.
- f: confere `python3-cryptography` (dpkg).
- g: semeia `plataforma/admin` (superadmin) e `demo`/`demo2` sem superadmin; reinicia 2FA, senha temporária e
  bloqueio dos semeados; apaga `tests/credenciais_totp.txt`; garante partições de `log_acesso` e `evento` de 4
  meses; em `dev` apaga resíduos `zt-*`; `cota_jobs_dia = 100000` nos inquilinos de demonstração.
- h2: `var/jobs`, unidade `plat-worker`, espera `:8153/saude`.
- i: `/etc/nginx/conf.d/plat_limites.conf` (zona `plat_login`); `location = /api/login` e `= /api/login/2fa` com
  `limit_req`; `Referrer-Policy` em toda `location` (commit `abbb03d`; chega ao ar na próxima execução).
- j: além de 200, `noindex` e HSTS, exige `fila.workers_vivos >= 1` em `/saude`.
- e2 (turno 3, item L7-14): pacotes apt lidos de `deploy/pacotes_apt.txt` (7 no total — os 4 já conferidos
  antes mais `gdal-bin`, `python3-gdal`, `python3-magic`); `dpkg -s` antes e depois de `apt-get install -y`
  no que faltar. Detalhe e o que ficou fora de propósito: ADR 0007 seção 1.
- h4 (turno 3, item L0-05-e, opcional, flag `--worker-container`): builda e sobe o worker também em contêiner
  Docker, ALÉM da unidade systemd de h2 (nunca no lugar dela). Sem a flag, o passo é pulado e nada muda — o
  comportamento padrão é bit a bit o de antes. Detalhe, tabela de decisão e o que a containerização corrigiu:
  seção 5.8 e ADR 0010.

Tempo medido pelo adversário do L0-02 na reinstalação destrutiva do zero (schemas `plat` e `plat_trabalho` e as
duas roles apagados): "instalado em 50 s", serviço indisponível cerca de 63 s (17:14:17 a 17:15:20 UTC); depois,
27 tabelas, 60 funções, 25 políticas, partições de setembro a dezembro, três inquilinos, `/saude` 200 com `noindex`
e HSTS, login real pelo playwright com a senha regenerada e varredura cruzada de 34 rotas sem nenhum 2xx cruzado
(`refutacao.json`, rodada 2). No turno 1 o instalador do zero levava 6,24 s; a diferença é o DDL da 003 (24,2 s na
tabela `versao_migracao`) e da 002 (9,5 s) nesta instância compartilhada com disco a 98 %.

### 7.1 `scripts/` (ferramentas de operação)

`plat` (dispatcher) + `segredo_rotacionar.py` (item L7-19: `plat segredo rotacionar <nome>` para os 5
segredos — `PLAT_SECRET` com dupla-chave, `PLAT_DSN`, `PLAT_DSN_WORKER`, `PLAT_GARAGE_ADMIN_TOKEN`,
`PLAT_GARAGE_CHAVE_S3:<slug>`; substitui o antigo `rotacionar_segredo.sh`, que só cobria 2 dos 5 —
detalhe em `docs/SEGURANCA.md` §1-2 e `docs/RUNBOOKS/segredos.md`) e, do turno 3 (item L7-16, ADR 0007 seção 2-3):
`assinar_pacote.sh` + `verificar_pacote.sh`, finos wrappers de `plat_assinatura.py` (Ed25519 via
`cryptography`). Assinar roda fora do appliance, gera o par de chaves na 1ª execução (privada fora do
repositório, pública registrada em `deploy/chaves_publicas_release.txt`); verificar roda no appliance, sem
rede, contra as chaves fixadas nesse arquivo. `chave_id = "k" + sha256(pública_crua)[:16]`; `.sig` é JSON
com `algoritmo`, `chave_id`, `assinatura_b64`.

---

## 8. systemd e nginx

`plat-api`: `uvicorn app.main:app --host 127.0.0.1 --port 8150 --workers 2 --proxy-headers --forwarded-allow-ips
127.0.0.1 --no-access-log`, `Restart=on-failure`, `MemoryHigh=768M`, `MemoryMax=1G`, `PYTHONNOUSERSITE=1`.
`plat-worker`: seção 5.4. `NRestarts` do worker cresce com os testes lentos (`kill -9` do `test_jobs_reinicio.py`);
não é sinal de falha por si.

nginx (`deploy/nginx.conf` + `plat_limites.conf`): cabeçalhos `X-Robots-Tag: noindex, nofollow`,
`Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin` repetidos em cada `location` (um `add_header` dentro de
`location` cancela os herdados; o testador pegou a ausência de `Referrer-Policy` em `/api/*` por isso e o commit
`abbb03d` a repetiu nas 4 `location`, com teste vivo em `test_cabecalhos.py`); `Cache-Control: no-store` em
`/static/` e no proxy; `client_max_body_size 200m`; `proxy_read_timeout 120s` (maior que o keepalive de 15 s do
SSE). `X-Accel-Buffering` da API é consumido pelo nginx e não chega ao cliente; o efeito (sem buffer) está medido.
`Cache-Control` do SSE sai duplicado pela URL pública (`no-store, no-store, must-revalidate`).

---

## 9. Contratos

### 9.1 `/saude`

Ver `MANUAL.md` seção 1.2. Campos novos do turno 2: `servicos.worker` (sonda `PLAT_WORKER_URL`) e `fila`
(`plat.fila_estado()`: `pendentes`, `rodando`, `workers_vivos`, `ultimo_heartbeat`). Informativos: não mudam o
status HTTP (o L7-06 decide alerta).

### 9.2 Erros da API (`app/erros.py`)

Toda resposta de erro é `{"erro": "<codigo_curto>", "mensagem": "<frase em português>", "detalhe": <opcional>,
"req_id": "<16 hex>"}`; `RequestValidationError` vira `422 validacao` com o detalhe do pydantic; 404 também para
recurso de outro inquilino e para rota de superadmin chamada por quem não é. Paginação `limite` (padrão 50, máximo
1.000; 200 na fila) e `deslocamento`, resposta `{total, itens}`. Datas ISO 8601 UTC com `Z`. Cookie OU Bearer,
nunca os dois.

### 9.3 OpenAPI

`docs/openapi.json` gerado por `make openapi` e comitado; igual ao servido em `/api/openapi.json` (adversário: 74/74
rotas idênticas em `abbb03d`). Cada rota traz `x-auth` (`-`, `S`, `T`, `S/T`) e `x-privilegio`. É a lista que o teste
cruzado (`tests/api/test_cruzado.py` com `cruzado_casos.py`) varre com 4 vetores por rota (sessão A, token A com
`admin:inquilino`, sessão A com `X-Plat-Inquilino`, anônimo) comparando o digest md5 de todo o dado de B antes e
depois; rota sem caso = teste falha. Medido: 74 rotas no OpenAPI, 73 com caso (`rotas_total`, `rotas_cobertas`,
sobre `90d03c0`; o caso da rota `DELETE /api/plataforma/inquilinos/{id}` entrou em `abbb03d`, e o adversário rerodou
o teste isolado nesse commit com 80 aprovados). Ao vivo, o testador varreu 73 rotas com 411 chamadas e 0 acesso
cruzado indevido, md5 das linhas de B intacto (`testador_rotas_varridas_cruzado_vivo`,
`testador_chamadas_cruzadas_vivo`, `testador_2xx_cruzados_indevidos`, `testador_linhas_de_B_alteradas`).

---

## 10. Configuração, log, testes e medidas

### 10.1 `.env` (`app/settings.py`)

| chave | obrigatória | uso |
|---|---|---|
| `PLAT_DSN`, `PLAT_SECRET`, `PLAT_AMBIENTE`, `PLAT_URL_PUBLICA` | sim | como no turno 1; `PLAT_SECRET` também deriva a chave do segredo TOTP |
| `PLAT_DSN_WORKER` | sim para o worker | `postgresql://plat_worker:...`; role do processo pai da fila |
| `PLAT_GIT_SHA`, `PLAT_MARTIN_URL`, `PLAT_TITILER_URL`, `PLAT_GARAGE_URL`, `PLAT_LOG_NIVEL` | não | como no turno 1 |
| `PLAT_WORKER_URL` | não | sonda de `/saude` (`http://127.0.0.1:8153`) |
| `PLAT_WORKER_NOME` | não | nome-base do worker; padrão = nome do host; a identidade registrada é `<nome-base>:<pid>` (migração 012) |
| `PLAT_WORKER_PROCESSOS` | não | filhos simultâneos (1) |
| `PLAT_WORKER_MEMORIA_MB` | não | teto de `memoria_mb` aceito pelo registro (1536) |
| `PLAT_JOBS_DIR` | não | diretório de trabalho (`var/jobs`) |
| `PLAT_JOB_MAX_REINICIOS` | não | devoluções sem terminar até `falhou` (5) |
| `PLAT_GPU_SSH`, `PLAT_GPU_DIR` | não | reservadas ao executor remoto (L1-05); ausentes, tipos `gpu` são recusados na importação |
| `PLAT_RELOGIO_TESTE` | não | relógio injetado das agendas, só em `dev` |
| `PLAT_DADOS_DIR` | não | acrescentada pela trilha do catálogo (L0-03, em construção) |

Variáveis de teste lidas do ambiente do processo só em `dev`: `PLAT_TESTE_BLOQUEIO_MIN`, `PLAT_TESTE_OCIOSA_S`;
da suíte: `PLAT_OPENAPI_ARQUIVO`, `PLAT_GRAVAR_MEDIDAS`.

### 10.2 Log

Uma linha JSON por evento em stdout, recolhida pelo journal (`app/log.py`): `ts`, `nivel`, `msg`, `logger`; na
linha de acesso `req_id`, `metodo`, `rota` (redigida), `status`, `tempo_ms`, `ip`; no worker `job_id`, `tipo`,
`tenant_id`, `pid_filho`. Segredos nunca aparecem: o adversário leu 3 h de journal (1.290 linhas) com 0 valor de
cookie ou token; o testador, 15 min (1.034 linhas) com senha, cookie e tokens ausentes.

### 10.3 Testes

`make check` = `lint` (ruff) → `sem-marcador` (grep de `tests/marcadores.regex` em `app web db docs deploy
install.sh Makefile requirements.txt pyproject.toml *.md`) → `teste` (`pytest -m "not lento"`) → `e2e` (`pytest -m
lento --base-url`). `make e2e-worker` roda só os lentos da fila. `make medidas` grava `tests/medidas/*.json`
(`PLAT_GRAVAR_MEDIDAS=1`). Regra da casa: qualquer `pytest` roda sob `flock /home/dev/plataforma/laco/.pytest.lock`
(dois em paralelo na mesma árvore invalidam sessões de demonstração e disputam o único slot do worker).

| diretório | o que prova |
|---|---|
| `tests/unit/` | settings, versão, instalador (inclusive `Referrer-Policy` em todo bloco), dependências, log, senha, vendor, política de senha (12 recusas nomeadas), TOTP (vetor RFC, janela, replay, cifra), redação, escopos, erros, registro de tipos, cron (fuso, troca de horário, intervalo mínimo) |
| `tests/api/` | saúde, banco, migrações, RLS, cabeçalhos HTTP vivos, docs, páginas, login (códigos, força bruta, tempo constante, bloqueio que expira), sessão (cookie, alterado, após logout, ambíguo, 415, origem), `/api/eu`, tokens (escopo, restrição, revogação, rotação), usuários (último admin, lote, domínio de e-mail), grupos, papéis, log e eventos, log de acesso por `User-Agent` único, plataforma (criar, suspender, reativar, apagar inquilino), funções seguras (0 `PUBLIC`; chamadas cruzadas por `psql`), privilégios declarados, eventos declarados, varredura cruzada gerada do OpenAPI |
| `tests/api/jobs/` | fila (100 jobs exatamente uma vez com 2 workers, retentativa 2/4/8, falha definitiva, chave, pesado), cancelamento (cooperativo, pendente, final = 409, ignora a flag, timeout), memória, RLS A→B, agendas com dois relógios, SSE local e público, progresso do job de 5 min (lento), reinício e `kill -9` (lento), transições (006), identidade (x-auth/x-privilegio) |
| `tests/e2e/` | saúde, login (2), 2FA, conta, usuários, grupos, papéis, tokens, log, chaves de tradução cruas (`test_i18n_cru.py`), tarefas (5: lista com progresso ao vivo e detalhe, cancelar pela tela, filtro = API, 1.000 jobs, agendas) |

Estado da suíte inteira no fim do turno (P3): o testador do L0-02 obteve 407 aprovados e 2 falhas em `make teste`
(16:32 UTC; as 2 por resíduo de outra sessão) e o adversário 402 aprovados e 7 falhas em `make check` na instalação
nova (17:2x UTC; 4 em `tests/api/jobs` sob contenção do próprio `make check`, 3 por corrida da árvore compartilhada,
rerodadas isoladas em `abbb03d` com 80 aprovados). O testador do L0-05 obteve 422 aprovados e 8 falhas em `make
medidas` (17:15-17:28 UTC; nenhuma do produto, seção 1 do `40_testes.md` dele). A suíte inteira ainda não ficou
verde numa rodada única: o gerente reavalia P3 no fechamento do turno.

### 10.4 Medidas

Fixture `medida(item)(nome, valor, unidade, comando)` grava `tests/medidas/<item>.json` só com
`PLAT_GRAVAR_MEDIDAS=1`. `L0-02-tenant-auth.json` tem 35 chaves (16 do backend e da fixture, 19 `testador_*`);
`L0-05-jobs.json` tem 14. Os dois arquivos da árvore de trabalho (17:28 UTC, `90d03c0`) ainda não foram comitados
pelo testador; a versão comitada de `L0-02` (`12b2c2e`, sobre `ffedc05`) traz 73 rotas cobertas de 73, login
128,7 ms, log 0,67 ms e token 3,16 ms, valores que diferem dos citados aqui por décimos de milissegundo.

---

## 11. Front (`web/`)

Módulos ES nativos sem bundler, importação relativa, nunca `?v=` (cache resolvido por `no-store`). Tema único em
`web/estilo/` (tokens, base e componentes; antes `style.css`) (painel de instrumento: chrome escuro, barra lateral de 232 px que vira barra superior abaixo de 800 px,
IBM Plex se instalada). Base reutilizável em `js/base/`: `api.js` (`chamar/obter/enviar/alterar/apagar`, contrato
de erro), `estado.js` (loja sobre `EventTarget`, `tem(privilegio)`), `i18n.js` (`carregar/t/aplicar`, evento
`plat:i18n` para componentes que renderizam antes do dicionário), `dom.js` (`h()` sem HTML em texto, `htmlSeguro`
por DOMPurify, `copiar`), componentes `plat-aviso`, `plat-busca`, `plat-paginacao`, `plat-tabela`,
`plat-formulario`, `plat-dialogo` (Custom Elements com rótulo por `for/id`, `aria-live`, foco devolvido, Escape),
`layout.js` (`TELAS` por privilégio, `montarLayout`, `pronto`). `js/auth/sessao.js`: `exigirSessao` (401 →
`/entrar?inquilino=&proximo=`; pendência → `/conta#senha|#2fa`; privilégio ausente → "sem permissão"). A tela
Tarefas usa a mesma base. Orçamento de 60 kB por módulo: o maior é `grupos.js` (17,9 kB). Vendor: MapLibre GL
4.7.1 e `pmtiles-4.5.0.js` (item L2-01-a; primeira tela a carregá-los é `/mapa`, por `<script>` clássico — os
dois expõem `window.maplibregl`/`window.pmtiles`, não são módulo ES), Swagger UI 5.32.15, DOMPurify 3.4.14;
`make vendor` confere 6 sha256. `js/mapa/` (`mapa.js`, `estilo.js`): mapa MapLibre sobre PMTiles local; painel
de identidade visual "instrumento" (`web/estilo/tokens.css`, `class="instrumento"` no `<body>`, item L0-14) —
`/mapa` é a primeira tela do produto a nascer já com ele, sem passar pelo tema azul antigo.

Páginas prontas no chromium do playwright (`pagina_pronta_ms_*`, `goto` até `body[data-pronto=1]`): login 54,3 ms,
conta 37,8, 2FA 9,7, usuários 59,4, grupos 60,8, papéis 58,7, tokens 78,9, log 73,7; tarefas 142,9
(`pagina_tarefas_pronta_ms`).

---

## 12. Convenções que valem para todo item

1. Número em README, MANUAL, ARQUITETURA ou PARIDADE sai de `tests/medidas/*.json` ou de `refutacao.json`, com o
   comando.
2. Identificadores expostos em português; inglês só onde a biblioteca ou o mercado exigem (`tenant_id`, `token`,
   `slug`, `hash`, `cron`).
3. Nenhum nome de cliente, parceiro ou piloto em código, dado, teste, captura ou documento. Inquilinos de
   demonstração: `demo`, `demo2`; inquilino técnico: `plataforma`.
4. Nada manual fora de script: o que o `install.sh` não faz, não existe.
5. Serviço novo = unidade `plat-<nome>` em `deploy/`, porta da faixa 8150-8159, campo em `/saude`, linha na seção 1,
   no mesmo turno.
6. Migração aplicada é imutável; correção vem em arquivo novo, numerado na hora de criar. Toda tabela com
   `tenant_id` nasce com RLS `FOR ALL TO plat_app USING ... WITH CHECK ...`; partição herda política própria.
7. Função `SECURITY DEFINER` nova: `REVOKE EXECUTE FROM PUBLIC`, `GRANT` só à role que a chama, e checagem de
   contexto quando há contexto (`plat.contexto_confere`); superadmin sempre por hash de sessão, nunca por GUC.
8. Toda rota declara `x-auth`, `x-privilegio`, `response_model` e, se escreve, o evento em `eventos_esperados.py`;
   toda rota tem caso em `cruzado_casos.py`.
9. Toda tarefa de job tem de poder recomeçar do zero; efeito parcial em área de trabalho e entrada atômica no fim.
10. Toda função visível tem e2e playwright com captura em `tests/e2e/capturas/<item>_<tela>.png`; 0 erro de console;
    nenhuma chave de tradução crua na tela.

---

## 13. O que ainda não existe

- Catálogo de conteúdo, camadas, mapa, tiles, edição, serviços OGC e Esri-compatíveis, motor multicritério, rede de
  utilidades, construtores, conectores, operação (linhas L0-03 em diante; o L0-03 está em construção nesta árvore).
- `plat-martin` (8151): existe desde o item L2-01-b (corrigido aqui em 07/09/2026 — esta linha estava desatualizada). `plat-titiler` (8152): porta reservada, serviço inexistente.
- Tela de configuração do inquilino (L0-07-a), console do superadmin (L0-07-f), e-mail (L0-07-d), relatórios
  (L0-07-e), login externo SAML/OIDC/gov.br (L0-08-a/b/c), apagar usuário com transferência de conteúdo
  (L0-03-j), perfil estendido do membro (L0-02-g), CLI de administração (L0-14), `docs/LIMITES.md` gerado de
  `app/limites.py` (L0-12).
- `L0-08-d-ldap` (LDAP/Active Directory): construído (seção 4.9), mas sem tela — a rota
  `GET /api/login/provedores` ainda não lista o LDAP (é fluxo próprio, `POST /api/login/ldap`, não o "botão de
  provedor" genérico do L0-08-a/b/c); botão na tela de entrada e formulário de configuração em `/admin` são o
  `L0-08-f` (frontend), fora deste item; StartTLS e `sAMAccountName` (Active Directory de verdade) não foram
  testados contra um diretório real, só contra o glauth de teste (`tests/ldap_fixture/`).
- Periódicos além do expurgo de jobs (expurgo de sessões, partições futuras de `log_acesso` e `evento`, retenção de
  12 meses): as funções existem, o registro em `app/jobs/periodicos.py` é o L0-05-d.
- Executor remoto no GPU box (`executor='gpu'`): só a coluna, o CHECK e a recusa na importação (L1-05).
- Veredito do testador e do adversário sobre a correção 012/013 (identidade única do worker, cláusula acrescentada
  ao portão do L0-05 pelo achado 2): o código e o teste estão comitados em `9be9c6a`, mas o `40_testes.md` do L0-05
  ainda não os cobre e o adversário do item não rodou; ver `CHANGELOG.md`.
- `Content-Security-Policy` (L7-03); rotas `/svc/`, `/ogc/`, `/tiles/` que aceitam `?token=` (L2-04, L1-02);
  `Referrer-Policy` no ar depende da próxima execução do `install.sh`.
- Paridade com ArcGIS Pro e ArcGIS Online reais: pendente da decisão D20 (credencial de teste).
- `L2-01-mapa-web` (visualizador completo: camadas do catálogo por Martin/RLS, raster, legenda, popup, busca,
  impressão) — só a fatia `L2-01-a-basemap-local-pmtiles` existe (seção 11 e `MANUAL.md` seção 13). Sem base
  cartográfica nacional (D27, travado por disco); sem rótulo de texto no mapa (glifos, `L2-02-e`). `plat-martin`
  (8151) está no ar desde o L2-01-b (esta linha estava desatualizada; corrigida em 07/09/2026).
- `L2-11-c-rota-matriz-isocrona`: só `/api/rota`, `/api/matriz` e `/api/isocrona` sobre um OSRM de teste com
  perfil `carro` (`MANUAL.md` seção 14). Sem pgRouting instalado, sem `/mais-proximo`/`/ajuste-de-trajeto`,
  sem perfil pé/bicicleta, sem NAServer Esri-compatível, sem UI no mapa (isso é o `L2-05-f`), sem teste de
  1.000×1.000 nem a validação de 200 pontos amostrados do portão completo — ver `laco/handoffs/T3/L2-11-c-rota.md`.
  Exceção à convenção 5 abaixo: o serviço `plat-osrm-guarulhos` fala o protocolo próprio do `osrm-routed`
  (não HTTP da API do produto), por isso segue a numeração 50xx que as outras 4 frentes de OSRM da casa já
  usam (5000-5003), em vez da faixa 8150-8159 — documentado, não é porta reservada esquecida.
- `L2-10-c-linguagem-expressao` (linguagem de expressão própria, equivalente ao Arcade da Esri): só o NÚCLEO
  existe — gramática publicada (`docs/EXPRESSAO.md`), AST tipada + avaliador em `app/expressao/avaliador_py.py`
  e o MESMO analisador em `web/js/expressao/avaliador.js` (os dois sem `eval`/`exec`/`compile`/`Function`
  dinâmico), 18 funções, 41 vetores comparados byte a byte entre os dois avaliadores
  (`tests/expressoes/vetores.json`, `tests/unit/test_expressao_equivalencia.py`). Sem integração com popup,
  rótulo, formulário, regra de atributo, restrição/validação (isso é `L5-11` e outros itens do L2-10); sem
  tipos lista/dicionário/geometria; sem os ≥ 40 funções e ≥ 200 vetores da hipótese cheia; sem tabela de
  paridade completa com o Arcade function reference — ver `laco/handoffs/T3/L2-10-c-expressao.md`.
- `L0-09-metadado-catalogo`: só a exportação ISO 19139 por item (`GET /api/itens/{id}/metadado.xml`,
  `app/catalogo/metadado.py`, XSD oficial cacheado offline em `docs/xsd/cache/`) e o catálogo externo **OGC
  API Records** (`/ogc/records`, `app/catalogo/rotas_ogc.py`) existem — os dois autenticados por
  `catalogo:ler` (sessão ou token de serviço), nunca abertos; isolamento por inquilino vem da RLS de
  `plat.item` já existente (mesmo mecanismo de `GET /api/itens`), provado em
  `tests/api/catalogo/test_metadado_ogc.py`. Sem: editor de metadado na tela (`dados.procedencia` e os demais
  campos MGB 2.0 ainda são escritos por API, não por formulário), ISO 19115-3 (só 19139), **CSW** (decisão
  registrada em `app/catalogo/rotas_ogc.py`: RAM no limite, nenhuma lib CSW instalada, protocolo legado),
  varredura cruzada A→B automática das duas rotas novas (pendente de `make openapi` + `cruzado_casos.py`,
  adiado porque outras trilhas do turno regravavam os dois arquivos ao vivo) — ver
  `laco/handoffs/T3/L0-09-metadado.md`.

O placar do laço, a tabela dos itens do backlog e a fronteira por linha estão em
`/home/dev/plataforma/laco/PAINEL.md`, gerado por `laco/gera_painel.py` a partir de `laco/estado.json`.

## 14. Documento de construtor (item L5-05-documento-versoes, ADR 0011)

Não é um mecanismo novo: é `plat.item.dados` (o envelope `{tipo, esquema_versao, corpo}`) + `plat.tipo_item.
esquema`/`esquema_versao` (JSON Schema por tipo, ADR 0004) + `plat.item_versao` (versão imutável com sha256,
publicar = `versao_publicada`), todos de L0-03, reaproveitados por inteiro. `app/catalogo/documento.py`
acrescenta só o que JSON Schema puro não expressa: unicidade de id de nó e referência pendente entre nós
(`validar_grafo`, chamado logo depois de `tipos.validar` em `criar`/`editar_item`), migração de esquema
`migrar_<tipo>_v<N>_v<N+1>` aplicada NA LEITURA (`ver()`, nunca gravada de volta), e um hash canônico
`sha256_canonico` (json.dumps ordenado, sem espaço) separado do `sha256` de `item_versao` (que é o de
`corpo::text` do jsonb do Postgres — estável dentro dele, não reproduzível fora sem reimplementar a
serialização do banco: ordena chave por comprimento-depois-alfabeto, espaço depois de `:`/`,`, MEDIDO
diretamente nesta máquina antes de decidir por um hash à parte).

Migração `028_documento_grafo.sql` substitui o esquema trivial de `app`/`painel` (`corpo:{}`) por um esquema
de grafo (`corpo.nos`/`corpo.ligacoes` opcionais — documento sem nó nenhum continua válido; quando `nos`
existe, cada um precisa de `id` ULID); `corpo.mapas`/`mapa_id` continuam declarados porque são o contrato já
entregue de `app/catalogo/relacoes.py::_app` (item L0-03-i, "usado-por" de app/painel→mapa) — a migração NÃO
podia quebrá-lo. `docs/gerar_esquemas.py` espelha o esquema vigente de cada tipo com `familia` em
`documento.FAMILIAS_GRAFO` para `docs/esquemas/<tipo>-v<N>.json` (mesma disciplina de `docs/gerar_limites.py`:
arquivo é `repr()` do banco, `--check` falha se divergir); versões históricas (v1) são mantidas à mão, nunca
regeradas. Novo endpoint `GET /api/itens/{id}/integridade`: recomputa em SQL (`digest(corpo::text,'sha256')`)
e compara com o `sha256` gravado — detecta edição direta em `plat.item_versao` por fora do gatilho (que só
quem tem acesso de superusuário ao Postgres consegue: `plat_app` tem INSERT/UPDATE/DELETE revogados na
tabela desde a 011).

## 15. Registro de camadas do acervo e modelo de conexão externa (itens L6-01-a-registro e
L6-02-a-modelo-conexao-e-seguranca, ADR 0012)

Dois modelos independentes que compartilham a mesma pergunta ("como uma camada de fora entra no catálogo sem
virar risco"), construídos no mesmo turno.

**`plat.acervo_camada`** (migração 030, renumerada de 028 por colisão com a migração `028_documento_grafo`
da trilha concorrente — "migração numerada na hora", nunca reservada) é registro GLOBAL, sem `tenant_id`/RLS,
do mesmo tipo de `plat.acervo_ficha` (021): metadado da CASA, igual para todo inquilino. Diferença: a ficha
(021) é por FONTE (376 linhas, sem geometria); `acervo_camada` é por TABELA canônica com geometria — join de
`acervo.objeto` (`tipo='fonte'`, `canonico`) com `geometry_columns`. Escrita só por
`scripts/acervo_sync.py`, um processo Python fora da API (roda como `postgres`, psycopg2 do dpkg, sem venv —
não depende de FastAPI); `plat_app` tem só `SELECT` (mesmo padrão de `plat.versao_migracao`). `COUNT(*)`
exato com `SET LOCAL statement_timeout = 25000` por tabela (nunca `reltuples`); tabela fantasma é regra
dinâmica (`linhas_exatas = 0 AND linhas_estimadas > 0`), nunca lista de nomes. Prazo duro de 270 s dentro do
script (`PRAZO_TOTAL_S`): candidatas que sobram entram como `bloqueada`/`nao_processada_no_prazo`; a ordem de
processamento é por `sincronizado_em` mais antigo primeiro, para que rodadas sucessivas cubram tabelas
diferentes sob carga da máquina. A poda de linhas obsoletas (`DELETE ... WHERE acervo_camada_id <> ALL(...)`)
compara contra o universo COMPLETO de candidatas (antes de qualquer `--limite` de depuração), nunca contra o
que a rodada atual processou — um `--limite` pequeno chegou a apagar o registro inteiro antes dessa correção.

**`plat.conexao`** (mesma migração 030) é dado do INQUILINO (`tenant_id` + RLS, políticas por dono/
`conteudo.editar_tudo`, mesmo padrão de `plat.pasta`): tipo em vocabulário fechado (`wms`, `wmts`, `wfs`,
`ogc_api`, `esri_rest`, `stac`, `geoparquet`, `pmtiles`, `postgres_fdw`, `s3`, `http`), `config` JSONB livre
(validação por tipo é dos itens de conector futuros), `credencial_cifrada` (AES-GCM, `app/conexao/
credencial.py`, mesmo padrão de `app/auth/totp.py`/`app/auth/ldap.py` — chave derivada de `PLAT_SECRET`,
nunca `pgp_sym_encrypt`). Rotas em `app/conexao/rotas.py` (`/api/conexoes`); nenhuma delas faz `SELECT
credencial_cifrada` para responder. `app/conexao/seguranca.py` é o núcleo de defesa: `validar_url` resolve o
host (thread com timeout — `getaddrinfo` da stdlib não tem timeout nativo) e recusa qualquer IP resolvido
que seja privado/loopback/link-local/CGNAT (100.64.0.0/10, gap de `ipaddress.is_private` nesta versão do
Python)/reservado/multicast; `_BackendPinado` (subclasse de `httpcore.SyncBackend`) troca, só para o
`(host, porta)` já validado, o alvo de `connect_tcp` pelo IP resolvido — o TLS continua verificando o
hostname ORIGINAL (`server_hostname`, inalterado), fechando DNS-rebinding sem reimplementar TLS;
`buscar_seguro` nunca segue redirecionamento automático, revalida cada `Location` do zero. `POST /api/
conexoes/{id}/testar` chama `buscar_seguro` com timeout curto e grava `saude`/`saude_mensagem`/
`saude_latencia_ms`/`saude_verificada_em`.

Ambos os itens entregam só o MODELO; a view com RLS por assinatura sobre a tabela original do acervo
(L6-01-b) e os 14 conectores concretos restantes que de fato leem WMS/WFS/STAC/... (L6-02-b em diante) ficam
para os próximos turnos — **o primeiro conector concreto (`postgres_fdw`) foi construído no item
L0-04-i-fonte-registrada** (turno 4): `plat.conexao_fdw_publicar` (SECURITY DEFINER, migração
`20260907T0148`) cria `SERVER`+`USER MAPPING`+`FOREIGN TABLE`+`VIEW` por tabela publicada, porque `plat_app`
não tem `CREATE` nem `USAGE` na extensão. A defesa de alvo desse conector É DIFERENTE da defesa de SSRF HTTP
acima (TCP direto, não HTTP): bloqueia menos categoria de IP (um Postgres de cliente pode estar numa rede
privada de propósito) e mais por lista explícita (banco/host de produção da própria casa). Ver `docs/adr/
20260907T0148-fonte-registrada-postgres-fdw.md` e MANUAL.md §18.2a.
Ambos os itens entregaram só o MODELO; os 15 conectores concretos que de fato leem WMS/WFS/STAC/...
(L6-02-b em diante) ficam para os próximos turnos. A publicação da camada em si é a seção 15.1.

### 15.1 Publicação sem cópia (item L6-01-b-view-so-leitura)

Migração `20260906T15521aa_acervo_publicacao.sql`. Cada camada `estado = 'exposta'` do registro vira uma VIEW
em **`plat_acervo`**, criada por `scripts/acervo_publicar.py` (roda como `postgres`, idempotente; camada que
sai de `exposta` perde a view na rodada seguinte). A view tem só as colunas de `colunas_expostas` mais a
geometria, é dona do papel `NOLOGIN` **`plat_acervo_publicador`** (que recebe `SELECT` de uma tabela de origem
por vez) e leva `plat.acervo_pode_ler('<acervo_camada_id>')` no `WHERE`. `plat_app` recebe `GRANT SELECT` só
da view — nada em `public`, e nada de escrita: `INSERT`/`UPDATE`/`DELETE` na view são recusados pelo Postgres.

**`plat.acervo_assinatura`** (RLS por `tenant_id`, sem policy de `UPDATE`: assina ou cancela) é o que o
porteiro consulta; **`plat.acervo_publicacao`** registra o que está publicado (view, colunas, SRID), escrita
só pelo publicador. Rotas: `GET /api/acervo/camadas`, `POST`/`DELETE /api/acervo/camadas/{camada}/assinatura`
(privilégio `conteudo.registrar_fonte`), `GET /api/acervo/camadas/{camada}/feicoes` e
`GET /api/acervo/camadas/{camada}/tiles/{z}/{x}/{y}.mvt`. O caminho usa `view_nome` ([a-z0-9_]), não o
`acervo_camada_id` (que tem `/` e `.`).

Duas decisões medidas, detalhadas em `docs/adr/0018-publicacao-sem-copia-do-acervo.md`: a view **não** é
`security_invoker` (seria negada, porque o privilégio checado passaria a ser o da tabela de origem) e **não**
leva `security_barrier` (o `&&` de geometria não é `LEAKPROOF`, o índice GiST cai e a consulta vira varredura
sequencial). O que protege é o porteiro ser argumento constante sem coluna: vira `One-Time Filter` e, sem
assinatura, o nó do índice sai do plano como `(never executed)`. Medido sobre `public.car_area_imovel`
(8.406.837 linhas, `COUNT(*)`): 1,5 ms de mediana na consulta por caixa envolvente.

O que NÃO existe: `plat-martin` (porta 8151 reservada, seção 2) — o SQL de tile que ele publicaria é servido
pela própria API; FeatureServer/OGC API de feição (L2-04); camada do catálogo no visualizador (L2-01).

## 16. Ficha do acervo completa e gate de LGPD (itens L6-01-d-ficha-fonte e L6-01-f-lgpd)

**`plat.acervo_endpoint`** (migração 040): view `SECURITY INVOKER` sobre `acervo.endpoint`, mesma regra D17
de `plat.acervo_ficha` (join com `acervo.fonte`, só licença escrita). `vivo` é coluna calculada na view
(`confirmado AND http = '200'`), não em Python — evita duas definições divergentes de "vivo" no código.

**`plat.acervo_lgpd`** (migração 041): tabela curada à mão (`fonte_id` PK com FK para `acervo.fonte`,
`risco_pii boolean NOT NULL`, `motivo`/`decidido_por` `NOT NULL` com `CHECK (btrim(...) <> '')` — nunca
marcada, nem limpa, sem razão escrita). Sem GRANT de escrita a `plat_app` (mesmo padrão de
`plat.acervo_camada`, migração 027): só migração ou acesso direto ao banco escreve. `app/acervo/rotas.py`
faz `LEFT JOIN` desta tabela em `CAMPOS_FICHA`/`CAMPOS_FICHA_DE`, com `coalesce(risco_pii, false)` — fonte
sem linha em `acervo_lgpd` (67 das 68 licenciadas) nunca precisa de confirmação.

Novo evento de domínio: `acervo/adicionar_recusado_pii` (`plat.evento_tipo`, migração 041 — `plat.evento.tipo`
tem FK para essa tabela; sem a linha, o `INSERT` de `registrar_evento` quebraria com violação de FK na
primeira fonte marcada). `tests/api/eventos_esperados.py` ganhou a entrada para
`("POST", "/api/acervo/{fonte_id}/adicionar")`.

**Padrão de transação para "recusar e ainda assim auditar"** (`app/acervo/rotas.py::_recusar_pii`, copiado de
`app/auth/rotas_login.py::_falhou`/`_bloqueado`): `db.db()` faz `rollback()` em qualquer exceção não tratada
dentro do `with` — levantar `ErroAPI` no MESMO bloco que chamou `registrar_evento()` apagaria o evento junto
com o rollback. A rota faz o SELECT da ficha num bloco, fecha o bloco, decide fora dele, e — só se for
recusar — abre um bloco NOVO só para o evento (que fecha e comita normalmente) antes de levantar o erro.
Achado ao escrever o teste (`test_adicionar_fonte_marcada_risco_pii_sem_confirmacao_recusa`): a primeira
versão registrava e levantava no mesmo `with`, e o evento nunca aparecia em `GET /api/eventos` — corrigido
antes de declarar o item pronto.

**Migração numerada ao vivo, três vezes na mesma passagem**: a árvore tinha 4 trilhas concorrentes disputando
números (031 batido por duas, 034/036/037 batidos por outras) — os dois arquivos desta passagem nasceram
`034`/`035`, foram renumerados para `036`/`037` (colisão com uma trilha de conexão), e de novo para
`040`/`041` (colisão nova, incluindo uma aplicada ANTES da minha no mesmo slot 037) — sempre conferindo
`ls db/migracoes` + `SELECT nome FROM plat.versao_migracao` ao vivo antes de cada tentativa, nunca reservando
número com antecedência. `db/migrar.sh` não pôde ser usado diretamente numa dessas rodadas porque
`030_conexao.sql` estava DIVERGENTE (sha aplicado ≠ sha do arquivo, causado por outra trilha) e o script para
no primeiro divergente — as duas migrações desta passagem foram aplicadas manualmente
(`cat arquivo | psql -1 -f -` + `INSERT ... plat.versao_migracao`), replicando exatamente o que `migrar.sh`
faria, para que uma rodada futura do script (depois que a trilha dona do 030 resolver o próprio problema) as
reconheça como já aplicadas (mesmo nome, mesmo sha) e pule sem reaplicar.

Limite desta fatia: sem classificação por COLUNA em `plat.acervo_camada` (só por nome, ainda); sem tela
(L6-01-c).

## 17. Perfil próprio do usuário (item L0-02-g-perfil-usuario)

Filho do L0-02-tenant-auth: a tela `/conta` (auto-atendimento) já existia; o L0-02-f-tela-usuarios é o irmão
que dá ao ADMIN uma tela para editar OUTRO usuário (`/admin/usuarios`, `app/auth/rotas_usuarios.py`) — este
item nunca toca naquele arquivo, é só sobre o PRÓPRIO usuário.

**`plat.usuario` ganha 5 colunas (migração 042)**: `idioma_preferido`, `unidades`, `formato_data`,
`visibilidade_perfil` (texto com `CHECK` de vocabulário fechado, `NOT NULL DEFAULT`) e `foto_sha256`
(nullable, `CHECK` de formato hex64 — sem `FK` para `plat.arquivo`: mesmo padrão não-normalizado que
`plat.tenant.config->logo` já usa desde o L0-07-a, porque o valor é só uma referência de leitura, nunca uma
junção). `app/auth/comum.py::SQL_USUARIO` ganhou as 5 colunas no `SELECT`, mas só `eu_json()` (não
`usuario_json()`, que `rotas_usuarios.py` também chama para a listagem do admin) as expõe — são
preferências do PRÓPRIO usuário, nunca um campo que o admin vê/edita sobre outro. `app/auth/modelos.py::Eu`
(não `Usuario`) ganha os campos correspondentes.

**`PUT /api/eu` (`app/auth/rotas_eu.py::editar_eu`)**: a whitelist de `campos_json` (`_CAMPOS_EU`) cresce de
`{nome, email}` para incluir `idioma_preferido, unidades, formato_data, visibilidade_perfil` — o mesmo
mecanismo (não um novo) continua recusando `login`/`perfil`/`papel_id`/`ativo`/`superadmin` com
`400 campo_nao_editavel` antes de tocar o banco. Cada campo novo é validado contra a tupla correspondente em
`app/limites.py` (`PERFIL_IDIOMAS`, `PERFIL_UNIDADES`, `PERFIL_FORMATOS_DATA`, `PERFIL_VISIBILIDADES`) por
`_opcao_ok()`, que devolve `422 validacao` nomeando o campo. O `UPDATE` usa o mesmo padrão
`CASE WHEN %s THEN %s ELSE coluna END` que o e-mail já usava, um `%s` de presença por campo — só os campos
que vieram no corpo mudam, os outros mantêm o valor atual (permite `PUT` parcial sem reler o estado antes).

`PERFIL_IDIOMAS = ('pt-BR', 'en', 'es')` é maior que `ORG_IDIOMAS = ('pt-BR',)` DE PROPÓSITO: guardar a
preferência não promete tela traduzida — isso é o item `L7-10-a-i18n-pt-en-es` (pendente); o campo existe
para não obrigar uma segunda migração quando aquele item chegar.

**`POST/DELETE /api/eu/foto`**: reaproveita literalmente o padrão de `POST/DELETE /api/org/logo`
(`app/auth/rotas_org.py`, item L0-07-a) — JSON `{"conteudo": "<base64>"}` sob cookie de sessão (o CSRF do
ADR 0002 §5.3 exige `application/json` em todo verbo de escrita; bytes crus ficariam reservados à rota de
token de serviço `POST /api/arquivos`), decodificado e limitado a `PERFIL_FOTO_BYTES_MAX` (1 MiB) ANTES de
tentar abrir como imagem, e então revalidado/REDESENHADO pelo Pillow: `im.load()` dentro de
`warnings.catch_warnings()` com `DecompressionBombWarning` como erro (mesma defesa da miniatura/logo),
`formato not in {'PNG','JPEG','GIF','WEBP'}` → `415`, `EXIF` removido (`exif_transpose`) e a imagem final é
sempre um PNG nascido do Pillow, nunca os bytes do cliente — por isso um SVG com `<script>` nunca é servido
de volta como imagem: o Pillow simplesmente não sabe abrir SVG (não é raster), cai no `except Exception` e
vira `415` antes de qualquer gravação em `app/objetos.py::guardar` (classe `usuario_foto`, sem `item_id`:
mesmo objeto genérico por conteúdo que o logo usa, dedup por sha256 dentro da classe).

Única diferença de propósito vs. o logo: `ImageOps.fit(im, (200, 200))` (recorte central que preenche o
quadro) em vez de `ImageOps.contain` (encaixa sem cortar, com fundo transparente) — um rosto cortado fica
melhor que emoldurado com barras; o logotipo de uma organização, ao contrário, não pode perder conteúdo nas
bordas. `PERFIL_FOTO_LADO = 200` (a hipótese do item), `ORG_LOGO_LADO = 300` — números diferentes por
propósitos diferentes, não um esquecimento.

**Front**: `web/js/auth/conta.js::montarFoto()`/`lerComoBase64()`/os dois `addEventListener` de
`#foto-arquivo`/`#foto-remover` são uma cópia quase literal de
`web/js/auth/organizacao.js::montarLogo()` (mesmo padrão, endpoint diferente). `web/js/base/layout.js::
montarLayout()` ganha um `<img id="pessoa-foto" class="foto-perfil">` opcional dentro de um novo
`.pessoa-topo` (sem foto: nenhum `<img>`, nunca um ícone genérico fingindo ser a foto de alguém) — CSS novo
em `web/estilo/base.css` (`.foto-perfil { border-radius: var(--i-raio-redondo); object-fit: cover }`).

**Cobertura de teste**: `tests/api/test_eu.py` ganhou os testes de preferências (edição válida/inválida,
persistência), foto (enviar/ler/remover, SVG recusado, >1 MiB recusado), escalada de acesso
(`login`/`perfil`/`papel_id`/`ativo`/`superadmin` continuam fora da whitelist) e domínio de e-mail do PRÓPRIO
inquilino (não só o teste unitário de `email_permitido` em `tests/unit/test_politica.py` — o caminho HTTP
inteiro, restringindo e restaurando o inquilino `demo`). `tests/api/cruzado_casos.py` ganhou os dois casos de
`POST/DELETE /api/eu/foto` na varredura cruzada A→B (mesmo padrão do `org_logo`). `tests/e2e/test_conta.py`
ganhou `test_perfil_nome_unidades_foto_na_barra_e_email_fora_do_dominio` (captura
`L0-02-tenant-auth_perfil.png`, verificada visualmente: foto redonda no cartão Dados E na barra lateral,
quatro selects novos, mensagem de domínio recusado no campo).

**Bloqueio ambiental encontrado (não causado por este item)**: o fixture `autouse` de sessão
`limpeza_de_residuos` (`tests/api/conftest.py`) depende de `sessao_plat` (superadmin do inquilino
`plataforma`), e o segredo TOTP guardado em `tests/credenciais_totp.txt` não bate mais com o que está no
banco — toda tentativa de login (mesmo com o retry anti-replay já embutido em `conftest.entrar`) devolve
`401 codigo_invalido`, e tentativas repetidas (inclusive as deste turno, ao diagnosticar) acionam o bloqueio
de força bruta (`423`, ver `plat.auth_falha`). Isso bloqueia `pytest tests/api/` inteiro — não só este item —
até alguém religar o 2FA do superadmin pela via legítima (login com o segredo certo, ou um admin da
plataforma desligando e religando o fator). A cobertura de API acima foi confirmada por um script equivalente
fora do pytest, usando o MESMO `TestClient` e o MESMO banco, autenticado como admin do inquilino `demo` (que
não exige 2FA) — suficiente porque nenhuma rota nova deste item depende do superadmin. Os e2e (que batem no
serviço `plat-api` ao vivo, não no `TestClient`) não são afetados por este bloqueio; o serviço foi reiniciado
uma vez (`systemctl restart plat-api`) para servir o código novo, com RAM conferida antes e depois.

## 18. Modelo de estilo (item L2-02-a-modelo-estilo; ADR `20260907T1200-modelo-de-estilo.md`)

`app/estilos/compilador.py` é o único lugar que traduz `plat_construtor` (7 tipos) em camadas MapLibre;
`app/estilos/validador.py` roda depois de `tipos.validar('estilo', dados)` nas duas rotas de escrita de
`app/catalogo/rotas_itens.py` (mesmo padrão de `documento.validar_grafo`): valida o `maplibre` ENVIADO contra
o vocabulário de campos e o validador oficial `@maplibre/maplibre-gl-style-spec` 20.4.0 (subprocesso Node,
`ferramentas/estilo/validar.mjs`), valida que `plat_construtor` compila sem erro, e então REESCREVE
`corpo.maplibre` com o resultado da compilação — a forma que fica gravada é sempre a canônica, nunca a
literal que o cliente mandou. `app/estilos/padrao.py` gera o estilo padrão determinístico (hash sha256 do
uuid do item); `app/estilos/sld.py` converte o subconjunto declarado para SLD 1.0.

Migração `db/migracoes/20260907T1148_estilo_modelo.sql` aperta o esquema do tipo `estilo` (antes `corpo` era
um objeto livre); `docs/gerar_esquemas.py` publica `docs/esquemas/estilo-v1.json` (acrescentado a
`TIPOS_PUBLICADOS`, ao lado de `mapa`). Achado de ambiente, não deste item:
`CursorSchemaAmbiente` reescreve a palavra `plat` mesmo dentro de string humana (o `title` do JSON Schema),
então `docs/gerar_esquemas.py --check` só bate se rodado no schema `plat` de produção, nunca dentro de uma
trilha isolada — `docs/esquemas/mapa-v1.json` (item L2-01-a) já está commitado com esse defeito
(`title` contaminado com o nome de outra trilha); registrado no ADR deste item para quem for corrigi-lo.

**Decisão deliberada, não bug**: `maplibre` enviado pelo cliente é validado mas DESCARTADO — o que fica
gravado é sempre `compilador.compilar(plat_construtor)`. Isso fecha a ida-e-volta sem perda de graça (dois
saves do mesmo construtor são idênticos byte a byte) ao custo de o cliente não poder gravar uma camada
MapLibre inteiramente à mão fora do vocabulário do construtor — aceitável nesta passagem porque nenhum editor
visual deste construtor foi construído ainda (a interface é item seguinte).
## 18. Ladrilho raster por token (item L1-02-tiles-token, ADR 20260907T0300)

Fluxo de uma requisição de ladrilho, do cliente ao pixel:

```
cliente ->  nginx  ->  auth_request /api/tiles/autorizar  (cache 2 s, chave com o token)
                   ->  proxy_cache plat_tiles             (chave SEM o token: tipo|item|z/x/y|query)
                   ->  aplicação  app/imagens/rotas_tiles.py
                                  -> plat.raster_item (RLS) -> item no pgstac -> asset -> chave do objeto
                                  -> app/objetos.fonte_gdal -> /vsis3/<balde>/<objeto> + chave só-leitura
                                  -> app/imagens/tiles.ladrilho (rio-tiler 9.4.3, WebMercatorQuad)
                                  -> app/imagens/leitura.contar -> plat.tile_leitura (lote de 2 s)
```

Arquivos: `app/imagens/tiles.py` (motor), `app/imagens/wmts.py` (GetCapabilities gerado da mesma grade
que serve o ladrilho), `app/imagens/rotas_tiles.py` (rotas e autorização), `app/imagens/leitura.py`
(registro agregado), migração `20260907T0249_tile_leitura.sql`, bloco `/svc/.../raster|mosaico/` em
`deploy/nginx.conf` e as duas zonas de cache criadas pelo `install.sh`.

Três decisões que não se refazem sem ler o ADR: token no caminho (não em query, não URL que expira);
chave de cache sem o token, o que OBRIGA a subrequisição de autorização a conferir também o dono do
item; e recusa em 403, nunca 401.
## 18. Construtor de camada por esquema (item L5-31-construtor-de-camada-esquema, migração `20260907T1509_camada_esquema.sql`)

`app/catalogo/camada_esquema.py` (router `/api/camadas/*`) reaproveita inteiramente as primitivas do
L0-04-ingest-vetor para criar uma camada vazia: `plat.camada_schema_garantir(slug)` garante o schema
`d_<slug>`, e uma `CREATE TABLE` própria (fid identity + geom + colunas do usuário) é seguida por
`plat.camada_preparar(schema, tabela, srid, tipo, usuario_id)` — a MESMA função `SECURITY DEFINER` que a
ingestão chama depois do `ogr2ogr`, adicionando `globalid`/`versao`/`tenant_id`/auditoria, `FORCE ROW LEVEL
SECURITY`, índice GIST e os gatilhos `tg_tenant`/`tg_versao`. Nome de campo passa por
`app.ingestao.nomes.normalizar` (mesma função do L0-04, sem duplicar regra).

O que o PostgreSQL não guarda sobre um campo — alias de tela e domínio (lista código→rótulo, formato já
compatível com o `domain` de um FeatureServer Esri) — vive em `plat.camada_campo_meta`, tabela nova com FK
simples `item_id REFERENCES plat.item (id) ON DELETE CASCADE` (a chave primária que já existe; nenhuma
constraint única nova é criada em `plat.item`). A coerência de inquilino é garantida por GATILHO,
`plat.tg_camada_campo_meta`, no mesmo padrão de `plat.item_relacao` e `plat.item_grupo`: uma linha de
metadado que aponte para item de OUTRO inquilino é recusada com `metadado_de_outro_inquilino`, mesmo que
uma política de RLS falhe silenciosamente em algum caminho futuro — defesa em profundidade, não o único
mecanismo (a RLS de `camada_campo_meta`, `FORCE`, com a política padrão `tenant_id = plat.tenant_atual()`,
é a linha de frente). `GET
compatível com o `domain` de um FeatureServer Esri) — vive em `plat.camada_campo_meta`, tabela nova com
**FK composta** `(tenant_id, item_id) REFERENCES plat.item (tenant_id, id)` em vez de só `item_id`: exigiu
acrescentar `UNIQUE (tenant_id, id)` em `plat.item` (a PK já bastava para toda referência simples por id
até agora). A vantagem sobre uma FK simples: mesmo que uma política de RLS falhe silenciosamente em algum
caminho futuro, a própria constraint do banco recusa a inserção de uma linha de metadado apontando para um
item de OUTRO inquilino — defesa em profundidade, não o único mecanismo (a RLS de `camada_campo_meta`,
`FORCE`, com a política padrão `tenant_id = plat.tenant_atual()`, é a linha de frente). `GET
/api/camadas/{id}/campos` junta as duas fontes: tipo/tamanho/obrigatoriedade vêm de
`information_schema.columns` (autoridade única — nunca uma cópia que desalinha de um `ALTER TABLE` feito
por fora), alias/domínio vêm de `camada_campo_meta`.

Alterar esquema é sempre "avaliar, depois aplicar só o que passou": `_avaliar_mudanca` decide por cláusula
(`adicionar_campo`/`renomear_alias` sempre aplicam; `mudar_tamanho`/`mudar_tipo` aplicam se alargam — tabela
`ALARGAMENTO_SEGURO`, ex. `integer -> {integer, bigint, double precision, real, text}` — ou se a tabela está
vazia). O mesmo código serve o `POST .../esquema/plano` (só avalia) e o `PUT .../esquema` (avalia e aplica
as `aplicavel`), então os dois nunca podem divergir sobre o que é seguro.

Frontend: `web/construtor_camada.html` + `web/js/catalogo/camada_esquema.js`, paleta de tipos com Drag and
Drop API nativa do HTML5 (sem biblioteca, mesmo princípio "0 byte" do L5-08) e clique como via sem mouse.
Armadilha encontrada e corrigida: um módulo ES cujo topo faz `await algo(); iniciar();` ANTES de declarar
com `let` uma variável que `iniciar()` usa por baixo dos panos estoura `ReferenceError: Cannot access
'x' before initialization` (TDZ do `let`, hoisted mas não inicializado) — a ordem certa é declarar o estado
inteiro do módulo antes de qualquer chamada de nível superior que possa lê-lo, mesmo que a chamada esteja
"antes" textualmente de onde o estado é usado dentro de uma função. Só apareceu no e2e real (o `TestClient`
da API não carrega JS); nenhum teste de API pega esse tipo de erro.
## 18. Conector de feição externa: WFS 2.0 e OGC API - Features (item L6-02-c-wfs-ogcapi, ADR 0018)

Primeiro conector que lê dado de serviço de terceiro. Três módulos novos em `app/conexao/`:

- **`vetor_externo.py`** — o protocolo. `listar_colecoes`, `descrever_campos`, `contar` e a classe
  `Paginador`, para os dois protocolos. WFS 2.0 fala `GetCapabilities` / `DescribeFeatureType` /
  `GetFeature` (`COUNT`, `STARTINDEX`, `BBOX`, `RESULTTYPE=hits`), em GeoJSON ou GML 3.2; OGC API - Features
  fala `/collections`, `/collections/{id}/queryables` e `/collections/{id}/items` (`limit`, `bbox`,
  `datetime`, link `rel=next`). **Todo I/O de rede é `seguranca.buscar_seguro`** — não há cliente HTTP
  próprio neste módulo, e os drivers `WFS:`/`OAPIF:` do GDAL foram recusados de propósito (fariam a
  requisição fora da defesa contra requisição forjada pelo servidor; ADR 0018 seção 1).
- **`copia.py`** — o job `conexao.copiar_vetor` (pesado, 1 GiB, `ferramentas=("gdal",)`). Baixa as páginas
  por `vetor_externo`, grava GeoJSON por linha no diretório do job e só então chama `ogr2ogr` sobre esse
  arquivo LOCAL, com `-s_srs`/`-t_srs` (CRS nativo declarado → 4326) e `GDAL_HTTP_PROXY` em porta fechada, de
  modo que nenhuma requisição do GDAL possa sair da máquina. Depois leva cada coluna ao tipo que o serviço
  declarou, chama `plat.camada_preparar` (mesmas colunas obrigatórias, RLS e índices da ingestão de arquivo) e
  publica o item `camada_vetorial` com `dados.conexao` e `dados.procedencia`.
- **`cache.py`** — cache de 30 s no processo para o modo referenciado, com chave por (inquilino, conexão);
  editar ou apagar a conexão esquece o que ela cacheou.

Rotas novas (só leitura, modo referenciado): `GET /api/conexoes/{id}/colecoes`,
`.../colecoes/{c}/campos`, `.../colecoes/{c}/feicoes`. A cópia **não** tem rota própria — é `POST /api/jobs`
com `tipo: conexao.copiar_vetor`, para herdar fila, cota, cancelamento, log e progresso.

Mudança no L0-05 exigida por este item: o advisory lock de "1 pesado por vez" (`app/jobs/worker.py`,
`LOCK_PESADO`) passou a carregar o nome do schema. Ele é um lock do BANCO, e o banco é um só para produção,
homologação e as bases por trilha — com o nome fixo, um job pesado de um ambiente segurava o único lugar de
todos os outros ambientes (medido em 06/09). Em produção, onde só existe o schema `plat`, o comportamento não muda.
Todos os outros (medido em 06/09). Em produção, onde só existe o schema `plat`, o comportamento não muda.
todos os outros (medido em 06/09). Em produção, onde só existe o schema `plat`, o comportamento não muda.

Válvula de teste: `PLAT_TESTE_CONEXAO_ALVOS` (`app/conexao/seguranca.py::alvos_de_teste`), lista de pares
`host:porta` exatos aceita só fora de produção, para a suíte falar com um WFS e um OGC API de verdade subidos
no loopback (`tests/api/conexao/servidor_ogc.py`) em vez de depender do serviço de um órgão estar de pé.

## 18.1 CDN de ladrilho (item L7-26-cdn-tiles, ADR 20260907T1522)

Camada NOVA na frente do fluxo acima, num hostname separado (`tiles-<x>`, proxied pela Cloudflare;
`<x>` da aplicação continua DNS-only, D19):

```
cliente -> CDN (hostname tiles-<x>; simulada localmente por scripts/cdn_simulada.py)
             chave de cache = CAMINHO sem query string
             cache elegível se Cache-Control da origem permitir (respeita o TTL da origem)
        -> [MISS] origem (o fluxo do §18, sem alteração)
```

`item@versao` (`versao` = 12 chars do sha256 de `plat.raster_item`) faz `_servir`
(`app/imagens/rotas_tiles.py`) responder `Cache-Control: public, max-age=31536000, immutable` —
elegível a ficar na CDN para sempre, porque o endereço nunca muda de conteúdo. A checagem de
INQUILINO (`_fonte_do_item`, RLS via `plat.raster_item`) acontece SEMPRE antes da checagem de
VERSÃO — inverter isso vaza, pela diferença 403×404, que um item de outro inquilino existe com um
sha256 conhecido (achado corrigido nesta bancada, com teste de regressão em
`tests/api/imagens/test_cdn_tiles.py::test_versao_de_item_de_outro_inquilino_e_403_nunca_404`).

Purge por prefixo de caminho (`/svc/<token>/`) tem de repetir por ≥ `AUTH_TTL_S` (2 s) depois de
revogar um token — a origem ainda cacheia a autorização por esses 2 s, e uma chamada dentro dessa
janela recacheia um 200 morto por mais 1 ano (ver ADR 20260907T1522 §3 e `docs/CDN.md`). Sem acesso
à conta Cloudflare real, o DNS/Cache Rule/purge de produção são PENDENTE DO DONO, documentado em
`docs/CDN.md` com o passo a passo exato.
## 18. Limite de taxa em três camadas (item L7-03-b-rate-limit-abuso)

Três defesas independentes contra abuso de volume, cada uma provada com pedidos HTTP reais (não só
unitário) — detalhe operacional completo em `docs/SEGURANCA.md §9`, decisões em
`docs/adr/20260907T1500-limite-de-taxa-tres-camadas.md`.

1. **Borda, por IP** — `deploy/nginx.conf`: `location /api/` (zona `plat_api`, 120r/m burst 60) e
   `location /tiles/` (zona `plat_tiles`, 600r/m burst 200), somadas à `plat_login` já existente do
   L0-02; `install.sh` grava as zonas em `/etc/nginx/conf.d/plat_limites.conf`. `limit_req` roda ANTES
   do `proxy_pass`, então nunca invalida um `proxy_cache` que a rota venha a ter.
2. **API, por inquilino/plano** — `app/limite_taxa.py` + `plat.limite_taxa_verificar` (migração
   `20260907T1444_limite_taxa.sql`, janela deslizante em Postgres, mesmo desenho de
   `plat.redefinicao_solicitar` da migração 047), chamada de dentro de `app/auth/sessao.py::resolver` —
   por isso cobre TODA rota autenticada da casa, sem precisar tocar cada rota uma a uma. Chave
   `tenant:<id>`; teto por `tenant.config.limites.<escopo>_por_minuto`, cortado para a faixa de
   `limites.LIMITE_TAXA_PADROES` (mesma regra de corte de `AUTH_PADROES`). 429 com `Retry-After`
   (RFC 6585).
3. **Reincidência** — fail2ban, jail `plat` (`deploy/fail2ban/filter.d/plat-abuso.conf` +
   `jail.d/plat.conf`), `backend=auto` sobre um `access_log` DEDICADO do vhost do plat
   (`/var/log/nginx/plat_access.log`) — nunca o log genérico da máquina nem o `backend=systemd`/journal
   que a jail `nginx-limit-req` de outro produto, já instalada nesta máquina, usa.

`X-Forwarded-For` forjado: nada novo em Python. `deploy/plat-api.service` já sobe o uvicorn com
`--proxy-headers --forwarded-allow-ips 127.0.0.1` (item anterior); `app/auth/sessao.py::ip_de()` já lê
só `request.client.host`, nunca um cabeçalho. Este item prova que a cadeia inteira (nginx por socket →
uvicorn confiando só no peer `127.0.0.1` → `ip_de()`) resiste a cabeçalho forjado, com nginx e fail2ban
reais (`scripts/bench_limite_taxa.sh`) — não inventa mecanismo novo.

**Pendência nomeada**: a cláusula "tile acima do limite do plano" está `parcial` — `L1-02-tiles-token`
(rotas `/tiles/...`/`/svc/<token>/raster/...`) não está mesclado nesta base; a zona `plat_api` já
protege `/tiles/` na borda mesmo sem a rota, e o escopo `tiles` da camada 2 já existe e está testado
diretamente contra a função SQL — falta só a fiação na rota real quando aquele ramo mesclar.

## 19. Mosaico por busca registrada e pegadas (item L1-07-mosaico-por-colecao-e-pegadas, ADR 20260910T2330)

Um mosaico é uma busca STAC REGISTRADA: `app/imagens/mosaico.py::registrar` chama
`pgstac.search_query()` (a função SQL que o `POST /searches/register` do titiler-pgstac usa por
baixo) para obter o hash determinístico da busca (coleções, bbox, datetime, filtro CQL2, ordenação),
e guarda a autorização numa tabela-espelho `plat.mosaico` (padrão de `raster_item.py`: pgstac guarda
conteúdo, uma tabela própria com RLS decide quem vê o quê). O id exposto ao cliente é um `uuid`
PRÓPRIO (não o hash md5), porque o vocabulário de escopo de token só aceita `tiles:ler:<uuid>` — todo
mosaico registrado também vira uma linha em `plat.item` (tipo `mosaico`) com o mesmo id, o que faz um
token poder ganhar escopo fino `tiles:ler:<uuid-do-mosaico>` sem nunca ganhar acesso às cenas que o
compõem (mesmo mecanismo genérico de `app/auth/escopos.py`, nada mudou lá). Idempotência (mesma busca
→ mesmo id) vem de `UNIQUE(tenant_id, hash)` com upsert; registrar de novo uma busca cujo mosaico foi
removido REATIVA a linha (`estado='ativo'`), não cria uma segunda.

Composição do pixel roda em CASA, não delegada ao TiTiler-pgstac (que é uma pilha ASGI assíncrona com
pool próprio, sem o padrão de RLS síncrono por `SET LOCAL plat.tenant_id` que o resto da aplicação usa
— ver ADR §1 para a decisão completa): `app/imagens/tiles.py::ladrilho_composto` reaproveita
`rio_tiler.mosaic.mosaic_reader` com `FirstMethod` (a mesma função que o `titiler.mosaic`/
`titiler-pgstac` chamam por baixo) para compor VÁRIAS fontes PIXEL A PIXEL — não cena a cena: onde a
primeira cena candidata não cobre, o pixel vem da próxima, o que faz a JUNTA entre duas cenas mostrar
as duas, em vez de uma cena inteira com o resto em branco (o defeito do esqueleto ad-hoc de "mosaico
da coleção" que existia antes deste item e que `app/imagens/rotas_tiles.py::_servir_composto`
substitui, preservando a mesma URL para as duas formas — coleção inteira ad-hoc OU busca registrada,
distinguidas pelo formato do segmento do caminho, `mo.eh_uuid`).

Contrato de URL (reaproveita o prefixo já existente, ADR §4):
```
/svc/<token>/mosaico/<uuid-ou-colecao>/{z}/{x}/{y}[.ext]   ladrilho composto (item L1-07 se uuid)
/svc/<token>/mosaico/<uuid>/tilejson.json                  TileJSON 3.0.0
/svc/<token>/mosaico/<uuid>/wmts[/1.0.0/WMTSCapabilities.xml]  WMTS 1.0.0
/svc/<token>/mosaico/<uuid>/pegadas                        GeoJSON das cenas que compõem a busca
/svc/<token>/stac/mosaicos                                 POST registra, GET lista
/svc/<token>/stac/mosaicos/<uuid>                          GET detalhe, DELETE remove (soft)
```
As rotas de ladrilho (genéricas, `{z}/{x}/{y}`) são registradas DEPOIS das rotas literais
(`tilejson.json`/`wmts`/`pegadas`) no arquivo — as duas formas de caminho têm a MESMA quantidade de
segmentos (`WMTSCapabilities.xml` bate no padrão `{y}.{ext}`), e o FastAPI casa pela forma do caminho
na ordem de registro antes de validar tipo; a ordem errada dá 422 em vez de resolver a rota certa
(defeito real desta bancada, corrigido — mesma ordem que o item L1-02 já usava para o item avulso).

Fora deste item (nomeado, não escondido): regras de seleção de pixel além de "primeira com dado"
(`median`/`mean`/`lock raster`/"mais recente sem nuvem" — item irmão L1-08); pegadas como camada
vetorial por Martin (só GeoJSON pela API neste turno); tela "Coleção → Mosaico" no construtor de mapa
(L2); `mosaicRule` do ImageServer compatível Esri (L1-25) continua recusando — agora por falta de
ligação entre as duas rotas, não mais por falta do L1-07 em si.

Arquivos: `app/imagens/mosaico.py` (registro/listagem/pegadas), `app/imagens/tiles.py`
(`ladrilho_composto`), `app/imagens/rotas_tiles.py` (`_servir_composto`, rotas de tile/tilejson/wmts/
pegadas do mosaico), `app/imagens/rotas_stac.py` (CRUD de `/stac/mosaicos`), migrações
`20260910T2330_mosaico.sql` e `20260910T2340_mosaico_tipo_item.sql`, testes
`tests/api/imagens/test_mosaico.py` e `tests/api/imagens/apoio_mosaico.py` (semeadura de grade
adjacente sintética).

## 20. Proveniência verificável da imagem — Lastro (item L1-01-j-proveniencia-da-imagem-lastro)

`app/imagens/proveniencia.py` concentra as três peças do Lastro aplicado à imagem: (1) montagem —
`montar_cadeia_ingestao`/`preencher_propriedades_proveniencia`/`selar_manifesto`, chamadas por
`ingestao._item_stac` no MESMO job que já converte (nenhum round-trip extra: o argv de cada
`gdal_translate` já é conhecido ali, `cog.ProdutoCOG` ganhou o campo `comando` só para isto); (2)
conferência — `conferir_item`, que resta CADA asset do balde em stream (`objetos.sha256_remoto`, novo,
mesmo padrão de `parte_concluir`) e compara com `file:checksum`, ativo a ativo; (3) canonicalização —
`canonicalizar`/`manifesto_sha256` (`json.dumps(sort_keys=True, separators=(",",":"),
ensure_ascii=False)`, documentado na íntegra no docstring do módulo porque o hash só é reproduzível se
gerar e conferir usarem a MESMA serialização).

Achado que decidiu a forma do campo: `pgstac.create_item`/`update_item` DESCARTA chave de `properties`
com valor `null` na gravação (STAC convencionalmente omite campo ausente em vez de `null`). Uma ficha
selada com `"plat:cadeia": null` local e gravada como tal teria o manifesto calculado sobre um dict que
o banco NUNCA devolve de volta igual — `conferir_item` acusaria divergência de manifesto em todo item
sem cadeia, sempre, sem byte nenhum alterado. `preencher_propriedades_proveniencia(cadeia=None, ...)`
por isso OMITE a chave (`novas.pop("plat:cadeia", None)`) em vez de gravar `null`; o lado de leitura
(`properties.get("plat:cadeia")`) devolve `None` de qualquer jeito, então nenhum consumidor externo
percebe a diferença — só a geração/conferência do manifesto precisava saber.

Dois caminhos de preenchimento retroativo, ambos usando `preencher_leve`/o próprio `conferir_item` por
baixo:
- **leve** (`app/imagens/reexecucao.py::imagens_preencher_proveniencia`, job, e
  `POST /api/imagens/proveniencia/preencher-pendentes`, rota síncrona de administração): só metadado —
  `processing:software` vem do `plat:versoes` que a ingestão original JÁ media (não uma medição nova),
  `plat:cadeia` fica ausente. `prov.itens_pendentes` busca só na coleção `<tenant_id>-imagens`
  (`content -> 'properties' ? 'plat:cadeia_origem'` no jsonb do pgstac) — NUNCA "toda coleção do
  inquilino": `pgstac.items` é particionado POR coleção, e esta trilha compartilhada tinha 236 coleções
  (a maioria efêmera, de outras suítes de teste) e 16.713 itens pendentes fora de escopo; escopar para
  só `imagens` levou a mesma varredura de 165 s para 2,8 s (MEDIDO, ver CHANGELOG).
- **pesado** (`app/imagens/reexecucao.py::imagens_reexecutar`, job só de fila, nunca rota HTTP — GDAL
  não roda dentro de uma requisição nesta casa): baixa o bruto já armazenado, reconverte com o `cog.py`
  ATUAL, compara sha256 obtido × registrado. Bate → `plat:cadeia` fica com o argv MEDIDO de verdade
  (`cadeia_origem=reexecucao_retroativa`); os assets/checksums originais NUNCA são sobrescritos, batam
  ou não — a comparação mora só em `plat:reexecucao`, ao lado.

`app/imagens/pgstac.py` ganhou `item_atualizar` (fino sobre `pgstac.update_item`, mesmas duas checagens
de posse de `item_criar`: coleção do inquilino, item já existe).

Rotas: `POST /api/imagens/<item>/conferir` (sessão/token `imagens:ler`, síncrona — conferir é leitura
em stream, nunca GDAL) e `POST /api/imagens/proveniencia/preencher-pendentes` (`conteudo.publicar_camada`).
`GET /api/imagens/<item>` ganhou o bloco `proveniencia` na resposta; `web/js/catalogo/tipos/raster.js`
mostra a cadeia em texto simples na aba Visão geral com um botão "conferir".

Adversário independente rodou ao fim do turno e achou um segundo buraco de design (não alcançável por
cliente da API, mas real): num item com `cadeia_origem=reexecucao_retroativa`, `processing:software`
continuava sendo o `plat:versoes` da ingestão ORIGINAL mesmo que a reexecução tivesse rodado com outro
GDAL/rio-cogeo — nada cruzava os dois blocos, e `selar_manifesto` sela essa combinação sem reclamar (o
manifesto prova integridade pós-selagem, nunca veracidade do conteúdo selado). Corrigido:
`imagens_reexecutar` agora grava `plat:reexecucao.versoes_mudaram_desde_a_ingestao` (booleano,
`plat:versoes` × `cog.versoes_software()` medido na hora) — a divergência vira campo explícito. A
refutação PRESCRITA pelo item (1 byte trocado no balde, chave RW) foi tentada e FALHOU: `/conferir`
acusou só o ativo certo, manifesto e outros ativos intactos.

Fora deste item (nomeado): `plat raster reexecutar/verificar <item>` como comando de linha só (hoje:
job de fila + rota HTTP cobrem o mesmo caso de uso); reexecução em lote (só um item por chamada); teste
automatizado de `versoes_mudaram_desde_a_ingestao` (hoje só verificado na instância viva).

Arquivos: `app/imagens/proveniencia.py` (novo), `app/imagens/reexecucao.py` (novo, 2 jobs), `app/imagens/
cog.py` (`ProdutoCOG.comando`), `app/imagens/ingestao.py` (`_item_stac` monta e sela a proveniência),
`app/imagens/pgstac.py` (`item_atualizar`), `app/objetos.py` (`sha256_remoto`), `app/imagens/
rotas_imagens.py` (2 rotas + bloco `proveniencia` em `GET /api/imagens/<item>`), `app/jobs/tipos.py`
(registro dos 2 jobs novos), migração `20260910T2345_imagens_proveniencia_evento_tipo.sql`, testes
`tests/api/imagens/test_proveniencia.py` (20 casos).

---

## 21. Comparar: cortina, lado a lado, lupa e tempo (item L2-01-j-comparacao-cortina-tempo)

Módulo novo `web/js/sig/comparar.js`, sem NENHUMA rota de backend nova. Duas peças independentes:

**Motor de comparação espacial** (`MotorComparacao`): reaproveita `Catalogo` (`web/js/mapa/catalogo.js`)
em DUAS instâncias — uma por mapa secundário (`#comparar-mapa-a`/`#comparar-mapa-b`, dois `maplibregl.
Map` novos com o mesmo estilo de base de `construirEstilo({tipo:'raster'})`) — em vez de reescrever
lógica de fonte/TileJSON/ordem de camada. Os quatro modos (cortina vertical, cortina horizontal, lado a
lado, lupa) são só geometria CSS por cima do MESMO par de mapas sincronizados:
- cortina: os dois mapas cheios e sobrepostos, `#comparar-mapa-b` recortado por `clip-path: inset(...)`
  cuja posição a alça arrastável escreve numa custom property (`--comparar-clip`);
- lado a lado: os dois em metades reais (`right:50%`/`left:50%`), sem `clip-path`;
- lupa: só o mapa B existe como container pequeno (260 px, `border-radius:50%`), o mapa PRINCIPAL
  (`window.plat.sig.map`) continua a tela normal — o "mapa A" da lupa é o mapa principal de verdade, não
  uma terceira instância.

Sincronismo: `_sincronizar(origemRef, destinoRef)` registra `'move'` nos dois lados e copia
centro/zoom/bearing/pitch com `jumpTo` (sem animação — `easeTo` perderia passo em movimento contínuo),
com uma trava booleana (`ocupado`) para o laço de retroalimentação: `jumpTo` dispara `'move'` de novo,
de forma SÍNCRONA, e sem a trava os dois mapas alternam `'move'` para sempre. Medido: diferença de
centro entre os dois mapas depois de 20 movimentos aleatórios (centro/zoom/rotação, só no mapa A) =
**0,0 grau nos 20** (`window.plat.sig.comparar.motor.diferencaMaximaCentro`/`.movimentosSincronizados`,
expostos para o e2e ler direto, sem parsear DOM).

Achado corrigido em 10/09 (achado do e2e, não do adversário — a suíte não tinha rodado ainda quando
escrito): `_aplicarVisual()` (que põe a classe `modo-<x>` no container — dela depende
`.comparar-area.modo-lupa { pointer-events: none }` em `sig.css`, que é o que deixa o `pointermove`
alcançar o mapa principal por baixo do container cheio de `#comparar-area`) só era chamada no ramo
cortina/lado-a-lado de `ligar()`; no ramo lupa a classe nunca mudava e a lupa ficava presa no canto
0,0 — corrigido chamando `_aplicarVisual()` uma vez, incondicional, antes do `if (modo === 'lupa')`.

**Controle de tempo** (`MotorTempo`): NENHUMA mudança na função de tile do Martin
(`plat.camada_tile_garantir`) nem no schema — a hipótese original do item cogitava filtro por parâmetro
na função de tile; descartado a favor de reusar a operação `query` do FeatureServer Esri-compatível já
existente (`app/consulta/motor.py`/`where_ast.py`, item L2-04-c), que já faz filtragem 100% no servidor
com `where` parametrizado e `returnCountOnly`. Cada passo monta `<campo> >= TIMESTAMP '...' AND <campo> <
TIMESTAMP '...'` (dialeto Esri de `where_ast`, literal `TIMESTAMP` vira `datetime` Python NAIVE — por
isso o cliente sempre manda o instante em UTC, `Date.toISOString().slice(0,19).replace('T',' ')`; a
sessão do Postgres desta instância é `Etc/UTC`, conferido `SHOW TIME ZONE`, então naive=UTC é seguro) e
faz DUAS chamadas em paralelo: `returnCountOnly=true` (contagem exibida) e `f=geojson&returnGeometry=
true&outFields=*&resultRecordCount=5000` (o que desenha, camada `circle` numa fonte GeoJSON só). Nulo
nunca aparece em janela nenhuma (comparação com NULL é sempre falsa no SQL); fuso de origem do dado não
importa (o campo é `timestamptz`, a comparação é sobre o instante armazenado). Medido contra `COUNT(*)`
direto no banco (não contra a mesma rota — provaria só que a rota concorda consigo mesma): 5 passos
instantânea + 3 acumulativa, **8/8 batendo exatamente** (ver MANUAL.md §27.2). "Reproduzir" é um laço que
AWAITS cada `_aoPasso` inteiro antes de agendar o próximo (nunca `setInterval` cego) — medido: último
passo 104-322 ms, sempre abaixo do intervalo de 500 ms (2 passos/s) usado como cadência.

Bancada: nenhuma das 3 camadas reais do inquilino demo tem campo de data TIPADO (`dt_entrada` de
"Subestações SP" é `text`). `scripts/comparar_demo_tempo.py criar/apagar` semeia/remove uma camada de
TESTE (100.000 pontos, `data_evento timestamptz`, ~3% NULL, 1/4 das linhas gravadas via `AT TIME ZONE` de
4 fusos diferentes de UTC) só para provar o controle — apagada ao final deste item (marca
`comparar-demo-l2-01-j` no `dados` do item, mesmo padrão de `scripts/martin_demo_camadas.py`).

Fora deste item (nomeado): controle de tempo para série raster/STAC (item irmão L1-04-serie-temporal,
`pendente` — a hipótese original prevê o MESMO controle de tela quando ele existir); alça arrastável no
divisor do "lado a lado" (hoje fixo 50/50); indicador de carregamento na lupa enquanto o mapa B monta
(existe uma janela de 1-3 s em que o círculo não segue o cursor, entre `ligar()` tirar `hidden` do
container e `_ativarSeguirCursor()` terminar de montar o mapa B + catálogo — o e2e aprendeu a esperar
`pararSync`/`_onMoveLupa` em vez do `hidden`, o produto ainda não tem um retorno visual disso).

Arquivos: `web/js/sig/comparar.js` (novo), `web/sig.html` (ícone + painel "Comparar" + containers dos
mapas secundários), `web/sig.css` (`.comparar-*`), `web/js/sig/sig.js` (import + chamada de
`instalarComparar`, atalho `c`), `web/js/i18n/pt-BR.json` (chaves `comparar.*`), `scripts/
comparar_demo_tempo.py` (novo, bancada), `tests/e2e/test_comparar.py` (novo, 5 casos).

## 22. OGC API — Tiles e OGC API — Maps por token (item L1-02-i-ogc-api-tiles-e-maps, ADR 20260910T2056)

Segunda fachada sobre o MESMO motor de pixel do item 18 (`app/imagens/tiles.py`) — sem tabela nova, sem
migração: `app/imagens/ogc_tiles.py` só monta JSON (landing, conformance, `tileMatrixSets`, coleção,
tileset), `app/imagens/rotas_ogc_tiles.py` autoriza pela mesma porta (`rotas_tiles._autorizar`, token
no caminho) e delega toda leitura de pixel:

```
ladrilho de item     -> rotas_tiles._servir            (a MESMA função do XYZ)
ladrilho de mosaico  -> rotas_tiles._tile_mosaico_impl  (a MESMA função de /svc/<token>/mosaico/<alvo>/...)
/map (bbox livre)    -> tiles.recorte()                 (a MESMA função do GetMap do WMS)
```

`{item}` no caminho de `/collections/{item}/...` resolve para item raster OU mosaico
(`rotas_ogc_tiles._resolver_colecao`): tenta `plat.raster_item` primeiro (consulta leve, mesmo
tenant_id do token); se não achar, tenta mosaico REGISTRADO (`mo.eh_uuid` + `mo.obter`) e por último
coleção completa ad-hoc (`ps.colecao_pertence`, o modo pré-L1-07). As três formas nunca colidem porque
um nome de coleção nunca é um uuid sintaticamente válido, e o item raster é sempre tentado ANTES do
mosaico (evita a ambiguidade de um uuid de item raster também "parecer" um uuid de mosaico).

Contrato de URL:
```
/svc/<token>/ogc/tiles                                                          landing
/svc/<token>/ogc/tiles/conformance
/svc/<token>/ogc/tiles/tileMatrixSets[/WebMercatorQuad]                         grade (definição REAL: TMS.model_dump())
/svc/<token>/ogc/tiles/collections[/<item>]                                     coleções (só itens raster são ENUMERADOS)
/svc/<token>/ogc/tiles/collections/<item>/map                                   OGC API Maps (só item raster)
/svc/<token>/ogc/tiles/collections/<item>/map/tiles/WebMercatorQuad             tileset metadata (item + mosaico registrado)
/svc/<token>/ogc/tiles/collections/<item>/map/tiles/WebMercatorQuad/{z}/{y}/{x}[.ext]  ladrilho (item + mosaico)
```

Duas armadilhas que valem registrar: (1) a ORDEM do caminho do ladrilho é `{tileMatrix}/{tileRow}/
{tileCol}` = z/y/x — o INVERSO do XYZ (z/x/y) — literalmente porque a Tabela 4 da OGC 20-057 define
assim; (2) `tileMatrixSetLimits` (por zoom, no tileset metadata) é calculado em O(1) por zoom com
`TMS.tile()` nos DOIS CANTOS do bbox, nunca por enumeração dos ladrilhos que intersectam — um item
cobrindo poucos graus em zoom alto teria milhões de ladrilhos, e só os dois cantos bastam para o
retângulo de linhas/colunas.

Dois achados corrigidos no próprio turno, ambos por auto-revisão antes do adversário externo: (a)
`width`/`height` do `/map` tinham `le=` no `Query` iguais ao teto (`WMS_LARGURA_MAX`/`WMS_ALTURA_MAX`)
— como o produto dos dois tetos é EXATAMENTE `WMS_PIXELS_MAX`, a checagem `width*height >
WMS_PIXELS_MAX` nunca disparava (código morto) e um pedido no canto do teto (4096×4096) caía direto no
render: medido em 142 s numa chamada. Corrigido para as MESMAS três condições OR'd de
`rotas_wms._get_map` (`width > MAX or height > MAX or width*height > PIXELS_MAX`), sem `le=` no Query
— a recusa acontece ANTES do render; (b) `/map` de item de outro inquilino caía direto em
`_eh_item_raster` (que só confirma "não é raster item DESTE tenant", não distingue "não existe" de "é
mosaico") e devolvia `422 mapa_nao_suportado` em vez de `403` — corrigido para chamar
`_resolver_colecao` primeiro (que já dá o 403 honesto) e só recusar por tipo depois de confirmar que o
item pertence ao inquilino.

Mais dois achados, estes do ADVERSÁRIO INDEPENDENTE (contexto próprio, não viu o código nem o
raciocínio acima — só o item, o portão e a instância viva): (c) `bbox=nan,nan,nan,nan` e
`bbox=-inf,-inf,inf,inf` não levantam `ValueError` em `float()` — passavam da checagem de "invertido"
(NaN nunca compara `>=`; `-inf < inf` é sempre verdadeiro) e só quebravam DENTRO de `tiles.recorte`,
saindo como 502 `leitura_falhou` (categoria errada: é entrada do cliente, não falha de leitura).
Corrigido com `math.isfinite` explícito antes de qualquer outra checagem, 400 `bbox_invalido`;
(d) `crs=EPSG:4326; DROP TABLE x` passava o `startswith("EPSG:")` inteiro — com o texto depois do
número incluso — e só quebrava dentro de `CRS.from_user_input`, ecoando a exceção crua no corpo do
502. Corrigido: o texto depois de `EPSG:` tem de ser só dígitos, senão 400 `crs_invalido` antes de
chegar perto de qualquer parser.

O adversário também mediu (não corrigido, registrado em `docs/PARIDADE.md`): o TETO PERMITIDO do
`/map` (4096×4096) renderiza em ~27 s nesta bancada — idêntico ao `GetMap` do WMS no mesmo tamanho
(~34 s), porque os dois chamam o MESMO `tiles.recorte`; não é regressão desta fachada, é o custo do
motor de base, que este item nem piora nem resolve (resolver pediria um teto de pixels PRÓPRIO menor
que o do WMS, o que quebraria a paridade byte-a-byte que é o próprio portão do item). E que zoom
abaixo do `minzoom` nativo do item é catastroficamente lento (até 18 s) tanto no XYZ quanto no
equivalente OGC — pré-existente no motor `tiles.ladrilho` do item 18, reproduzido idêntico nos dois
caminhos, fora do escopo de uma fachada.

Fora deste item (nomeado, não escondido — `docs/PARIDADE.md`): OGC API Maps sobre mosaico (compor um
retângulo arbitrário de várias cenas exigiria motor de composição por bbox livre — o que existe,
`ladrilho_composto`, só compõe por CÉLULA da grade); tileset metadata do mosaico AD-HOC sem registro
prévio (mesma lacuna que `mosaico_tilejson`/`mosaico_wmts_rest` já tinham — por consistência, não por
esquecimento); `collections-selection`, `dataset-tilesets`, formatos vetorial/cobertura/netCDF, `/api`
(OpenAPI próprio desta família), HTML, dimensão `datetime` por coleção.

Arquivos: `app/imagens/ogc_tiles.py` (novo), `app/imagens/rotas_ogc_tiles.py` (novo, registrado em
`app/main.py`), `tests/api/imagens/test_ogc_tiles.py` (29 casos) e `tests/api/imagens/
test_ogc_tiles_schema.py` (5 casos, JSON Schema oficial — `tests/dados/ogc_schemas/`), `docs/adr/
20260910T2056-ogc-api-tiles-e-maps.md`.

## 23. Telemetria da rede de utilidades (item L4-13-integracao-telemetria)

Módulo novo `app/rede_medicao/` (modelos/servico/rotas/tarefas), sem depender de nenhuma tabela de
`app/rede_utilidades/` por FK — `ativo` é um uuid opaco, a mesma decisão de desenho do módulo campo
(`plat.campo_alvo`): a medição referencia a feição por id, nunca a exige viva. Isso deixa o módulo
reutilizável para qualquer ativo (trafo, poste, caixa), não só rede elétrica.

`plat.rede_medicao` particionada nativamente por mês (`PARTITION BY RANGE (ts)`), decisão espelhando
`plat.evento` (migração 003 + trinco de `20260907T0240_ddl_concorrente_trinco.sql`): função
`rede_medicao_particao_garantir(mes)` SECURITY DEFINER com `pg_advisory_xact_lock` antes do DDL (a
corrida acontece na primeira escrita de cada mês); cada partição nova leva `REVOKE ALL FROM plat_app`
+ RLS/policy próprias — acesso direto à tabela-partição pelo nome fica bloqueado, o caminho normal
(SELECT/INSERT nomeando o pai) usa só a policy do pai (documentado: privilégio e RLS de uma consulta
por tabela particionada são checados contra a relação NOMEADA na consulta, não contra a partição onde
a linha acaba caindo — por isso `p_rede_medicao_inserir` só existe no pai e ainda assim vale para toda
gravação roteada por ele). Diferença para `evento`: aqui INSERT fica liberado para `plat_app` direto
(sem função SECURITY DEFINER de escrita) porque a ingestão já é por sessão com RLS de tenant, sem
necessidade de um caminho de escrita mais privilegiado.

Catálogo de grandeza (`plat.rede_medicao_grandeza`, como `evento_tipo`: só o backend semeia,
`REVOKE INSERT/UPDATE/DELETE FROM plat_app`) fecha o vocabulário e a unidade esperada de cada
grandeza — a "recusa honesta" do portão é FK + conferência de unidade em Python
(`servico.publicar_leituras`), nunca uma lista solta duplicada em dois lugares. `carregamento_pct` é
`tipo='derivado'`: a mesma tabela de leituras serve tanto o que o sensor manda quanto o que o motor de
alarme calcula, então a ficha do ativo e o gráfico de 7 dias reusam o mesmo mecanismo sem rota nem
tabela paralela — só o `fonte='motor_alarme'` diferencia a origem.

Alarme (`avaliar_alarme_carregamento`) roda SÍNCRONO, dentro da própria rota de publicação, não como
job periódico — decisão deliberada: o portão pede "última leitura em ≤ 5 s" e "o alarme disparando"
na mesma prova; um periódico de 30 s a 1 min teria uma folga desnecessária contra esse número, e o
custo por publicação é baixo (algumas consultas SELECT + no máximo alguns INSERTs de leituras
derivadas). Achado do turno: a primeira versão computava `carregamento_pct` só para a leitura MAIS
RECENTE de cada chamada — funciona para um sensor publicando em tempo real, mas quebra para um lote
com histórico (o simulador desta prova manda 65 min de uma vez; um sensor que ficou offline e manda o
atraso todo faz o mesmo). Corrigido: a função recalcula `carregamento_pct` para cada `ts` de corrente
na janela de retrospecto (`REDE_MEDICAO_ALARME_LOOKBACK_MIN` = 90 min) que ainda não tem o derivado,
não só o último — sem isso a série de carregamento tinha um ponto só e o "surto contínuo de 30 min"
nunca teria como existir. `plat.rede_medicao_alarme_estado` guarda só o ESTADO atual (`disparado`,
`desde`) para que reavaliar com o alarme já ativo não reabra o evento a cada leitura — dispara/resolve
só na transição.

Agregação a jusante (`agregado_jusante`) não duplica nenhum motor de traçado: chama
`app.rede_utilidades.fluxo.tracar_fluxo(cur, tenant_id, rede_id, "jusante", [{"feicao_id": ativo,
"terminal": ...}], [])` tal como está (item L4-18) e filtra os elementos devolvidos por
`grupo == GRUPO_TRAFO`. Sem `direcao_fluxo` gravado em nenhum trecho (a rede de demonstração não é
"rede simples"), a direção default cai em `'digitalizada'` (ordem dos vértices) — documentado no
próprio `fluxo.py`, não uma decisão nova deste item. `terminal` existe porque um dispositivo ponto com
2+ terminais na MESMA coordenada gera um nó de topologia por terminal, e só um se conecta ao trecho
(medido: a topologia liga sempre ao nó do `terminal_num` que "ganhou" a fusão por tolerância — no
pacote `eletrica-br` isso é o terminal 1 quando os terminais colidem no mesmo ponto); sem informar,
`_resolver_ponto` (já existente em `tracado.py`) devolve `422 terminal_ambiguo`.

Privilégio novo `rede.medir` (grupo `rede`, ao lado de `rede.tracar`/`rede.editar`) — perfis campo/
editor/admin, espelhado em `app/auth/privilegios.py` (vocabulário 47→48,
`tests/api/test_privilegios_declarados.py` confere).

Tela `/rede/medicao/ficha` (`web/rede_medicao_ficha.html` + `web/js/rede/medicao_ficha.js`) é
standalone, fora do visualizador de mapa principal (`/mapa`, `/sig`): decisão de escopo para não mexer
em código de mapa compartilhado por outras trilhas em curso no mesmo worktree. Usa `estiloVazio()`
(o mesmo truque de `web/js/rede/diagrama.js`: um `background` MapLibre sem fonte de tile) — o ponto do
ativo é o que importa, não um mapa-base.

Arquivos: `db/migracoes/20260910T2351_rede_medicao.sql`, `app/rede_medicao/{__init__,modelos,servico,
rotas,tarefas}.py`, `app/main.py`/`app/jobs/tipos.py`/`app/paginas.py` (registro), `app/limites.py`
(seção `REDE_MEDICAO_*`), `app/auth/privilegios.py` (`rede.medir`), `web/rede_medicao_ficha.html`,
`web/js/rede/medicao_ficha.js`, `web/js/i18n/pt-BR.json` (chaves `rede_medicao.ficha.*`),
`web/style.css` (seção telemetria), `scripts/rede_medicao_simulador.py`, `tests/api/
test_rede_medicao.py` (11 casos).

## 24. Construtor de formulário de atributos, arrasta-e-solta (item L5-03-form-builder)

`plat.formulario` (1 por camada, `camada_id UNIQUE`) e `plat.formulario_versao` (N por formulário,
`desenho` jsonb, só uma `publicado=true` por vez — índice único parcial) na migração
`20260910T2350_formulario.sql`; RLS e GRANT no mesmo molde de `campo.sql`. Módulo `app/formulario/`:
`modelos.py` (pydantic), `servico.py` (CRUD/publicação — `_resolver_dominios_de_camada` resolve domínio
"vindo da camada" como SNAPSHOT na hora de publicar, uma `SELECT DISTINCT` na tabela física da camada),
`motor.py` (validação + compilação, sem I/O), `rotas.py` (`/api/camadas/{id}/campos`, `/formulario`,
`/formulario/versoes[/{versao}[/publicar]]`; leitura exige só `camada:ler`, escrita reusa
`comum.exigir_edicao` — nenhum privilégio novo).

Decisão central: `versao_publicar` COMPILA o desenho em três chaves de `plat.item.dados` da camada —
`regras_campo` (obrigatório incondicional + domínio, a MESMA chave que `app/edicao/servico.py::
validar_atributos` já lia desde o item L2-03-a: zero mudança de esquema aí) e duas chaves NOVAS,
`form_condicionais`/`form_calculados`, lidas pela mesma função sem mudar sua assinatura — só ativa
quando presentes (`dados.get(...)`, vazio por padrão). Isso evitou uma segunda passagem de leitura de
banco em toda edição: o motor de validação continua puramente sobre o `dados` que a rota já carrega.
Para o caminho de CAMPO (`app/campo/servico.py::visita_criar`, que grava `dados` jsonb LIVRE, não
colunas de tabela), não há compilação — `app/campo/rotas.py::criar_visita` busca o desenho publicado
(`app/formulario/servico.py::desenho_publicado`) e chama `motor.validar_dados_livre` direto sobre ele;
antes deste item essa rota não validava `dados` nenhuma.

Condicional (`visivel_se`/`obrigatorio_se`) e cálculo (`calculo`) são expressões da linguagem do item
L2-10-c-linguagem-expressao (`app/expressao/avaliador_py.py`/`web/js/expressao/avaliador.js`,
`$campo` + `Se`/comparação/aritmética) — a integração que `docs/EXPRESSAO.md` deixava para "itens
futuros do L5" é este item. `avaliar_texto`/`avaliar` do lado Python roda dentro do orçamento de passos/
tempo já existente na linguagem (nenhum limite novo); um erro de avaliação (`ErroExpressao`) vira
`409 formulario_expressao_invalida` (config quebrada é erro do publicador, não do usuário que preenche).

Front: um SÓ módulo de renderização, `web/js/formulario/motor.js` (sem I/O, só DOM + o avaliador JS),
importado por `web/js/mapa/edicao.js` (`_montarFormulario` passa a ramificar: com desenho publicado usa
`formularioMotor.renderizar`/`validarLocal`; sem desenho, o campo-a-campo genérico de sempre —
mudança aditiva, zero teste existente de L2-03-edicao quebrou) e por `web/js/campo/roteiro.js`
(`formularioVisita` ganha campos dinâmicos ao lado de status/texto/foto; sem formulário publicado o
comportamento é o de sempre, sem `dados`). Construtor em `web/js/formulario/construtor.js` +
`web/formulario_construtor.html` (`/camadas/{id}/formulario`, registrado em `app/paginas.py`), sobre as
primitivas de arrasto do item L5-08-editor-arrasto (`web/js/editor/arrasto.js`) — reaproveitadas tal e
qual, sem copiar a mecânica de `dragstart`/`dragover`/`drop`.

Achado do e2e (medido, não suposto): o 3º `page.drag_and_drop` consecutivo falhava sempre (qualquer
campo, só por posição) com o viewport padrão — o cartão de propriedades de cada campo (7 linhas) empurra
o alvo do grupo para baixo da dobra, e o Chromium confunde o ponto de soltura com o auto-scroll no meio
do gesto nativo de Drag and Drop; resolvido com viewport mais alto no teste (`1400×1800`) e
`scroll_into_view_if_needed()` antes de soltar num segundo grupo. Um segundo achado do e2e: `iniciar()`
limpava `#principal` (`limpar(principal)`) antes de reconstruir a tela, apagando o `<plat-aviso
id="aviso">` que já vinha no HTML — `document.getElementById('aviso')` do teste (e qualquer código que
dependesse do aviso persistir) passava a achar `null`; corrigido não limpando `#principal` (a tela só
renderiza uma vez, nunca precisou disso).

Arquivos: `db/migracoes/20260910T2350_formulario.sql`, `app/formulario/{__init__,modelos,servico,
motor,rotas}.py`, `app/main.py`/`app/paginas.py` (registro), `app/limites.py` (seção
`FORMULARIO_*`), `app/edicao/servico.py` (bloco novo em `validar_atributos`), `app/campo/rotas.py`
(validação em `criar_visita`), `web/js/formulario/{motor,construtor}.js`, `web/formulario_construtor.html`,
`web/js/mapa/edicao.js`/`web/js/campo/roteiro.js` (integração), `web/js/i18n/pt-BR.json` (chaves
`formulario.construtor.*`), `tests/api/test_formulario.py` (13 casos), `tests/e2e/
test_formulario_construtor.py`, `tests/api/cruzado_casos.py` (7 rotas novas, portão P6).
