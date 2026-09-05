# Arquitetura do `plat` (o que existe em 0.1.0)

Este documento descreve o que está construído, instalado e testado no repositório
`/home/dev/plataforma/enterprise` no fim do turno 1 do laço PLATAFORMA ENTERPRISE (setembro de 2026).
Decisões e motivos estão em `docs/adr/0001-fundacao.md`; aqui está o resultado. O que ainda não existe
está na seção final e em `/home/dev/plataforma/laco/PAINEL.md`, nunca misturado ao que existe.

Todo número citado vem de `tests/medidas/L0-01-repo.json` (rodada 2 do testador sobre o HEAD `8ffe950`,
commit `3083366`; instalação, RLS e pg_hba são da rodada 1, marcadas assim no campo `comando`), com o
comando que o gerou entre parênteses. Nenhum número foi digitado de cabeça.

Estado: análise / beta privado. URL interna `https://plat.iagrointel.com`, `noindex` em toda resposta,
nunca linkada de lugar público.

---

## 1. Componentes e portas

| componente | porta | existe hoje | o que é |
|---|---|---|---|
| `plat-api` | 127.0.0.1:8150 | sim | FastAPI 0.138.0 sob uvicorn 0.27.1, 2 workers, unidade systemd `plat-api` |
| nginx | 443 / 80 | sim | `server_name plat.iagrointel.com`; `/static/` servido do disco (`alias` para `web/`), o resto em proxy para :8150; HTTP 80 redireciona para HTTPS |
| PostgreSQL 16.13 + PostGIS 3.6.3 | 5432 | sim (banco `iagro_sat`, compartilhado) | schema `plat`, role `plat_app` |
| Garage (objetos S3) | 3900 | sim, serviço `plataforma-garage` já existente na máquina | só sondado por `/saude`; nenhum bucket do `plat` ainda |
| `plat-martin` (tiles vetoriais) | 8151 | **não existe** | porta reservada; `/saude` devolve `"martin": "ausente"` |
| `plat-titiler` (tiles raster) | 8152 | **não existe** | porta reservada; `/saude` devolve `"titiler": "ausente"` |
| `plat-worker` (fila de trabalhos) | 8153 | **não existe** | porta reservada; item L0-05 |

Faixa reservada ao produto: 8150-8159. Serviços vizinhos da máquina que o `plat` nunca toca: 8125, 8126,
8091, 8127-8135, 8141 (lista na skill do laço).

Fluxo de uma requisição hoje:

```
navegador --HTTPS--> nginx (443)
   /static/*  -> disco: web/  (Cache-Control: no-store; X-Robots-Tag: noindex)
   /          -> proxy 127.0.0.1:8150 -> FastAPI
                    GET /            -> web/index.html
                    GET /saude       -> banco (plat.versao_migracao) + sondas HTTP (martin, titiler, garage)
                    GET /api/versao  -> VERSAO + sha do git
                    GET /api/docs, /api/openapi.json (gerados pelo FastAPI)
```

Memória do serviço em repouso: 88,5 MB no cgroup (`systemctl show plat-api -p MemoryCurrent` =
92.827.648 bytes, pico 93.818.880, 2 workers, NRestarts=0). A soma de RSS dos 4 processos é 145,7 MB
porque páginas compartilhadas contam mais de uma vez; o número a citar é o do cgroup.

---

## 2. Repositório

```
VERSAO                 0.1.0 (uma linha, semver); lido por /api/versao
README.md              o que existe
ARQUITETURA.md         este arquivo
MANUAL.md              acesso, saúde, instalação (uma seção por tela quando houver tela)
CHANGELOG.md           por turno
install.sh             instalador idempotente (root)
Makefile               check, check-rapido, lint, sem-marcador, teste, e2e, medidas, vendor, migrar, openapi
pyproject.toml         pytest (marcadores, pythonpath) e ruff
requirements.txt       toda dependência da aplicação e da suíte fixada com ==; uvicorn e psycopg2 do sistema (dpkg)
.env.exemplo           todas as chaves de configuração, sem segredo
.env                   segredos reais, modo 600, fora do git (criado pelo install.sh)
app/                   API (pacote Python `app`)
  main.py              aplicação, middleware X-Req-Id + linha JSON de acesso, rota /
  settings.py          leitura e validação do .env
  db.py                pool psycopg2 com reconexão e contexto por inquilino
  log.py               logging JSON por linha
  versao.py            VERSAO e sha do git lidos sem subprocesso
  saude.py             /saude e /api/versao
  senha.py             hash pbkdf2_sha256 (600.000 iterações)
db/
  migrar.sh            aplicador de migrações por sha256
  migracoes/001_fundacao.sql
  migracoes/002_identidade.sql
deploy/
  plat-api.service     modelo da unidade systemd (APP_DIR, APP_USER, PORTA substituídos)
  nginx.conf           modelo do server block (DOMINIO, APP_DIR, PORTA substituídos)
web/
  index.html, app.js, js/core.js, style.css, favicon.svg
  vendor/maplibre-gl-4.7.1.js, maplibre-gl-4.7.1.css, swagger-ui-bundle-5.32.15.js, swagger-ui-5.32.15.css,
  vendor/VERSOES.txt (nome, versão, sha256, licença, origem; `make vendor` confere os sha256)
docs/
  adr/0001-fundacao.md decisões da fundação
  openapi.json         gerado por `make openapi`, comitado
  PARIDADE.md          tabela viva contra o ArcGIS Enterprise (vazia: nenhuma capacidade de usuário ainda)
tests/
  conftest.py          fixtures: env, cliente (TestClient), conexao_plat_app, base_url, medida
  unit/  api/  e2e/    ver seção 9.3
  medidas/<item>.json  números medidos; único lugar de onde documento cita número
  marcadores.regex     expressão da varredura de marcador de pendência (a mesma do driver do laço)
  e2e/capturas/        PNG do e2e (fora do git)
  credenciais.txt      senhas dos administradores de demonstração (600, fora do git)
```

---

## 3. Banco: schema `plat`

### 3.1 Role e permissões

- `plat_app`: `LOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE`. Não é dona de nada
  (`pg_roles`: rolsuper f, rolbypassrls f; 0 objetos de posse de `plat_app` em `pg_class`, `pg_proc`,
  `pg_namespace`; schema, 6 tabelas, 4 sequências e 11 funções são de `postgres`). Sem posse e sem
  BYPASSRLS a RLS vale para ela.
- Senha: nunca no SQL do repositório; o `install.sh` faz `ALTER ROLE plat_app PASSWORD` com o valor lido
  do `.env` a cada execução (a senha do banco é sempre a do `.env`).
- `pg_hba.conf`: linha `host iagro_sat plat_app 127.0.0.1/32 scram-sha-256`, acrescentada pelo
  `install.sh` se não existir, seguida de `pg_reload_conf()`. Conferido: 1 linha após três execuções
  (`sudo grep -c plat_app /etc/postgresql/16/main/pg_hba.conf` = 1).
- Grants: `USAGE` no schema; `SELECT, INSERT, UPDATE, DELETE` nas tabelas; `USAGE, SELECT` nas sequências;
  `EXECUTE` nas funções; `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat` para que tabela
  criada por migração futura nasça acessível. Exceções: `versao_migracao` e `log_acesso` têm
  `REVOKE INSERT, UPDATE, DELETE` (a primeira só o aplicador escreve; a segunda só a função
  `plat.log_registrar`).

### 3.2 Tabelas

| tabela | chave | tenant_id | RLS | política | observação |
|---|---|---|---|---|---|
| `versao_migracao` | `nome` | não | não | — | `sha256`, `aplicada_em`, `duracao_ms`, `aplicada_por`; só leitura para `plat_app` |
| `tenant` | `id` serial | (é o próprio `id`) | sim | `p_tenant`: `id = plat.tenant_atual()` USING e WITH CHECK | `slug` com CHECK `^[a-z0-9][a-z0-9-]{1,38}$`, `config jsonb`, `cota_bytes` (20 GiB) |
| `usuario` | `id` serial | sim | sim | `p_usuario` FOR ALL | `login` minúsculo, `senha_hash`, `perfil` em (`admin`,`editor`,`visualizador`,`campo`), `superadmin`, `totp_*`, `falhas_login`, `bloqueado_ate`; UNIQUE (tenant_id, login) |
| `sessao` | `token_hash` | sim | sim | `p_sessao` FOR ALL | guarda sha256 do token, nunca o token; `expira_em`, `ip`, `agente` |
| `token_servico` | `id` serial | sim | sim | `p_token_servico` FOR ALL | `token_hash` UNIQUE, `prefixo`, `escopos text[]`, `restricao jsonb`, `expira_em`, `revogado_em` |
| `log_acesso` | `id` bigserial | sim (nulo antes de autenticar) | sim | `p_log_acesso` FOR SELECT | escrita só por `plat.log_registrar`; índices por (tenant_id, em) e (token_id, em) |

Medido: 4 tabelas com coluna `tenant_id`, todas com `relrowsecurity = t` e 1 política, mais `tenant` com
RLS por `id` (`pg_class × pg_attribute` no schema `plat`). Sem contexto de inquilino, `plat_app` vê 0
linhas nas 5 tabelas (`psql` como `plat_app` sem `set_config`: `count(*)` = 0 0 0 0 0; como `postgres`:
tenant 2, usuario 2). INSERT com `tenant_id` de outro inquilino falha com `new row violates row-level
security policy`; UPDATE/DELETE cruzados devolvem 0 linhas; UPDATE que muda o `tenant_id` do próprio
registro falha da mesma forma.

Dado semeado pela migração 002 (aberto, sem nome de cliente): inquilinos `demo` e `demo2`. Os
administradores `admin` de cada um nascem no `install.sh` (passo g), com senha em `tests/credenciais.txt`.

### 3.3 Contexto por inquilino

A aplicação define o inquilino da transação com `set_config('plat.tenant_id', ..., true)`,
`plat.usuario_id` e `plat.login` (o `true` = `SET LOCAL`; a conexão devolvida ao pool não carrega o
inquilino da requisição anterior). Duas funções `STABLE` leem esses valores:

```sql
plat.tenant_atual()  RETURNS int  -- NULLIF(current_setting('plat.tenant_id', true), '')::int
plat.usuario_atual() RETURNS int
```

Consequência que o adversário do turno 1 registrou e que vale como regra para os itens seguintes: o
contexto é um GUC que a própria role define. Todo SQL da API é parametrizado e o contexto só é definido
em `app/db.py`; uma rota que aceitasse SQL do cliente trocaria de inquilino sem passar pela RLS.

### 3.4 Funções `SECURITY DEFINER` (`SET search_path = plat, public`)

Todas de posse de `postgres`; `plat_app` tem `EXECUTE`. São as únicas que enxergam além do inquilino, e
existem porque a autenticação roda antes de haver inquilino na sessão.

| função | devolve | uso previsto |
|---|---|---|
| `auth_login(p_tenant, p_login)` | usuario_id, tenant_id, senha_hash, perfil, nome, tenant_nome, totp_ativo, totp_secret, bloqueado_ate, falhas_login, superadmin | login (item L0-02) |
| `auth_falha(p_usuario, p_max, p_min)` | void | incrementa falhas e bloqueia |
| `auth_ok(p_usuario)` | void | zera falhas, `ultimo_login = now()` |
| `auth_sessao_criar(p_usuario, p_horas, p_ip, p_agente)` | token em claro (grava só o hash) | cookie de sessão |
| `auth_sessao(p_hash)` | usuario_id, tenant_id, login, perfil, nome, tenant_slug, tenant_nome, superadmin, config | resolve cookie |
| `auth_sessao_encerrar(p_hash)` | void | logout |
| `auth_token(p_hash, p_ip)` | usuario_id, tenant_id, login, perfil, escopos, restricao, token_id | token de serviço |
| `log_registrar(...)` | void | única escrita em `log_acesso` |
| `tenant_criar(p_slug, p_nome, p_config, p_admin_login, p_admin_nome, p_senha_hash)` | tenant_id, usuario_id | exige `superadmin` no contexto |

Hoje **nenhuma rota chama essas funções**: não há login, sessão nem token na API. Elas foram criadas e
testadas no banco para o item L0-02. O adversário do turno 1 mostrou que, chamadas com um `usuario_id`
de outro inquilino, elas obedecem (é o desenho de `SECURITY DEFINER`); o isolamento depende da API passar
o identificador certo, e essa é a obrigação do L0-02.

### 3.5 Pool e reconexão (`app/db.py`)

`ThreadedConnectionPool(1, 8)` por worker, criado na primeira chamada. `db(ctx)` é um gerenciador de
contexto que devolve um cursor `RealDictCursor` dentro de uma transação (commit no fim, rollback em
exceção). Só a preparação (pegar conexão, testar `closed`, `SET search_path = plat, public`,
`set_config` do contexto) repete, até 9 vezes, descartando a conexão que falhou (`putconn(close=True)`);
a consulta do chamador roda uma única vez, porque repetir cegamente um INSERT duplica. É o padrão que
sobreviveu a três quedas do Postgres por falta de memória nesta máquina.

---

## 4. Migrações

- Arquivos `db/migracoes/NNN_nome.sql`, idempotentes por construção (`CREATE TABLE IF NOT EXISTS`,
  `DROP POLICY IF EXISTS` + `CREATE POLICY`, `CREATE OR REPLACE FUNCTION`, `ON CONFLICT DO NOTHING`).
  Sem `BEGIN/COMMIT` dentro do arquivo: o aplicador abre uma transação por arquivo.
- `db/migrar.sh` roda como `postgres` (`sudo -u postgres psql -X -q -v ON_ERROR_STOP=1`), lista os
  arquivos em ordem lexicográfica, calcula `sha256sum` e, para cada um: ausente na tabela = aplica o
  arquivo mais o `INSERT` em `plat.versao_migracao` na **mesma** transação (`psql -1 -f -` por stdin);
  presente com o mesmo sha = `igual`, pula; presente com sha diferente = **para com código 3** (arquivo
  aplicado é imutável; correção vem em arquivo novo), salvo se a primeira linha for `-- reaplicavel`
  (só para arquivos que contêm apenas `CREATE OR REPLACE`), caso em que reaplica e atualiza o sha.
- A tabela de controle é criada pelo aplicador antes de ler (mesmo DDL da 001), para que a primeira
  migração não dependa dela.
- `/saude` compara os arquivos em disco com a tabela: pendência > 0 = `banco: desatualizado` = HTTP 503.

Aplicadas hoje (`sha256sum db/migracoes/*.sql` e `SELECT nome, sha256 FROM plat.versao_migracao`,
iguais nos dois lados):

| migração | sha256 | conteúdo |
|---|---|---|
| `001_fundacao` | `74fcdc90a28c470953f952b190168c75fe712dde78a09b0a5fbf32bbbbe4b3eb` | role, schema, `versao_migracao`, `tenant_atual()`, `usuario_atual()`, grants e privilégios padrão |
| `002_identidade` | `418736611e8a1256e95603b7cdf188a008d6da579606d778393e9450648ddce2` | 5 tabelas, 4 índices, RLS, 9 funções `SECURITY DEFINER`, inquilinos `demo` e `demo2` |

Medido: 2 migrações aplicadas; segunda execução do instalador = `aplicadas 0 · iguais 2`
(`plat.versao_migracao` e saída do `install.sh`). O teste `tests/api/test_migracoes.py` roda o aplicador
duas vezes e exige 0 linhas novas, e edita uma cópia em diretório temporário para provar o código 3.

---

## 5. `install.sh` passo a passo

Uso: `sudo bash install.sh <dominio> [porta]`, por exemplo `sudo bash install.sh plat.iagrointel.com 8150`.
Root, idempotente, `set -euo pipefail`. Variáveis de ambiente opcionais: `APP_DIR` (padrão: diretório do
script), `APP_USER` (padrão: dono do diretório), `PLAT_DB` (`iagro_sat`), `PG_HBA`
(`/etc/postgresql/16/main/pg_hba.conf`).

| passo | o que faz | como conferir |
|---|---|---|
| a | imprime disco (`df -h /`), memória (`free -g`), diretório, usuário, banco, porta, domínio | saída do script |
| b | `CREATE EXTENSION IF NOT EXISTS postgis; pgcrypto` | `\dx` no banco |
| c | `bash db/migrar.sh` | `SELECT * FROM plat.versao_migracao` |
| d | cria `.env` (modo 600, dono `APP_USER`) se não existir, com senha da role (`openssl rand -hex 16`) e `PLAT_SECRET` (`openssl rand -hex 32`), `PLAT_AMBIENTE=producao`, `PLAT_URL_PUBLICA=https://<dominio>`; **sempre** realinha a senha de `plat_app` à do `.env` (`ALTER ROLE`, via stdin do psql, nunca em argumento); grava `PLAT_GIT_SHA=<sha do HEAD>` no `.env` a cada execução (sem `.git` e sem sha válido no `.env`, para com 1) | `ls -la .env`; `grep PLAT_GIT_SHA .env`; conectar com o `PLAT_DSN` |
| e | acrescenta a linha `host <banco> plat_app 127.0.0.1/32 scram-sha-256` ao `pg_hba.conf` se não existir; `pg_reload_conf()` | `sudo grep -c plat_app <pg_hba>` = 1 |
| f | confere os pacotes dpkg `python3-uvicorn`, `python3-psycopg2`, `python3-venv` (falta = para com 1); cria a venv (`python3 -m venv --system-site-packages venv`) se não existir; `pip install -r requirements.txt` com `PYTHONNOUSERSITE=1`; prova `import app.main, fastapi, dotenv` sem o site do usuário e exige que `fastapi` venha da venv | saída `venv: Python 3.12.3 · fastapi 0.138.0 da venv · pytest 9.1.1` |
| g | cria `tests/credenciais.txt` (600) com senhas aleatórias para `demo admin` e `demo2 admin` se não existir; semeia ou atualiza os dois administradores (`ON CONFLICT DO UPDATE`), hash calculado por `app/senha.py` com a senha entregue por stdin (nada em argumento, nada no journal do `sudo`) | `SELECT tenant_id, login, perfil, superadmin FROM plat.usuario` como `postgres` |
| h | gera `/etc/systemd/system/plat-api.service` do modelo, `daemon-reload`, `enable`, `restart`; espera até 30 s por HTTP 200 em `http://127.0.0.1:<porta>/saude`; em falha imprime o journal e sai com 1 | `systemctl status plat-api` |
| i | gera `/etc/nginx/sites-enabled/<dominio>` do modelo (com `Strict-Transport-Security`); se já houver bloco do certbot, preserva as linhas `# managed by Certbot` do bloco 443 e o bloco 80 inteiro; sem certificado, escreve bloco em :80 sem HSTS; troca atômica: guarda o bloco anterior, `nginx -t`, e se reprovar restaura o anterior e sai com 5; `systemctl reload nginx` | `sudo nginx -t`; `diff` contra o modelo |
| i2 | só se `/etc/letsencrypt/live/<dominio>` não existir: `certbot --nginx -d <dominio> --non-interactive --agree-tos --redirect` | `ls /etc/letsencrypt/live/` |
| i3 | só depois do i2: reescreve o bloco de novo, agora em 443 com HSTS | idem i |
| j | até 15 tentativas (o reload do nginx é assíncrono) de `curl -sI https://<dominio>/saude`; exige HTTP 200, `X-Robots-Tag` com `noindex` e `Strict-Transport-Security` com `max-age=31536000`; senão sai com 4 | a última linha do script: `instalado em N s` |

Tempos medidos pelo testador na rodada 1 (`/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150`):
do zero após `DROP SCHEMA plat CASCADE; DROP OWNED BY plat_app; DROP ROLE plat_app` = 6,24 s; com
`.env`, `tests/credenciais.txt` e a linha do `pg_hba.conf` também apagados = 9,14 s; segunda execução
seguida = 4,69 s. Três execuções com rc=0 e passo j com HTTP 200 + noindex. O tempo carrega a variação do
DDL da 002 numa instância compartilhada (1,4 s a 3,5 s entre rodadas) e não é métrica estável.

O adversário reinstalou do zero sobre `8ffe950` em 9,66 s (`refutacao.json`, rodada 2) com 82 testes
verdes depois. Limite que fica: a "máquina que nunca viu o repositório" é simulada nesta (a prova é
`PYTHONNOUSERSITE=1` + origem dos módulos + unidade viva; venv, `.env` e certificado foram
reaproveitados); os caminhos i2 (certbot emitindo), i3 e a restauração do bloco nginx após `nginx -t`
reprovar foram lidos, não exercitados. Ver seção 12.

---

## 6. systemd

Unidade `plat-api` (gerada de `deploy/plat-api.service`):

```
[Unit]     After=network.target postgresql.service · Wants=postgresql.service
[Service]  User/Group=dev · WorkingDirectory=/home/dev/plataforma/enterprise
           ExecStart=venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8150 --workers 2
                     --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
           Environment=PYTHONNOUSERSITE=1 (nunca o site do usuário: só venv e pacotes dpkg)
           Restart=on-failure · RestartSec=3 · MemoryHigh=768M · MemoryMax=1G · saída no journal
```

`--no-access-log` porque o middleware da aplicação escreve a linha de acesso em JSON; o log de acesso do
uvicorn duplicaria em texto livre. Comandos: `systemctl status plat-api`, `journalctl -u plat-api -o cat`.
Quem comita sem reiniciar deixa `/saude` um commit atrás (o sha é lido uma vez na partida):
`sudo systemctl restart plat-api` ou `install.sh`.

---

## 7. nginx

Arquivo `/etc/nginx/sites-enabled/plat.iagrointel.com`, gerado de `deploy/nginx.conf` mais as linhas do
certbot. Cabeçalhos no bloco `server` e **repetidos em cada `location`**, porque um `add_header` dentro de
`location` cancela os herdados (doc do nginx):

- `X-Robots-Tag: noindex, nofollow` em toda resposta, inclusive 404 e estático. Medido: 11 de 11 rotas
  testadas (`curl -sI` em `/`, `/saude`, `/api/versao`, `/static/app.js`, `/static/vendor/maplibre-gl-4.7.1.js`,
  `/static/style.css`, `/static/js/core.js`, `/api/docs`, `/api/openapi.json`, `/naoexiste`,
  `/static/naoexiste.js`); `http://` devolve 301 para `https://`.
- `Strict-Transport-Security: max-age=31536000` no bloco 443 e em cada `location`. Medido: 11 de 11 rotas
  HTTPS (inclui 404 e o 405 de `HEAD /api/docs`); ausente no 301 de `http://`, como deve ser. O
  `install.sh` remove a linha quando o bloco só escuta em 80 (sem certificado).
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- `location /static/`: `alias <APP_DIR>/web/`, `Cache-Control: no-store` (regra da casa: nunca `?v=` em
  importação de módulo ES; o cache é resolvido aqui). Travessia de caminho conferida:
  `curl --path-as-is .../static/../.env` = 404, `/static/vendor/` = 403.
- `location /`: `proxy_pass http://127.0.0.1:8150`, `X-Forwarded-For`, `X-Forwarded-Proto`,
  `proxy_read_timeout 120s`, `Cache-Control: no-store, must-revalidate`.
- `client_max_body_size 200m` (upload de camada entra no item L0-04).

---

## 8. Contrato de `/saude` e `/api/versao`

`GET /saude` e `HEAD /saude` (sem autenticação, sem log de acesso em nível INFO, `Cache-Control: no-store`):

```json
{
  "versao": "0.1.0",
  "git_sha": "8ffe950516f5",
  "ambiente": "producao",
  "banco": "ok",
  "migracoes_aplicadas": 2,
  "migracoes_pendentes": 0,
  "ultima_migracao": "002_identidade",
  "servicos": {"martin": "ausente", "titiler": "ausente", "garage": "ok"},
  "tempo_ms": 1.7,
  "em": "2026-09-05T13:14:45Z"
}
```

- `banco`: `ok` (leitura de `plat.versao_migracao` respondeu e nada pendente), `desatualizado` (arquivo em
  `db/migracoes/` sem linha na tabela) ou `erro` (exceção; a mensagem vai para o log, não para a resposta).
- HTTP **200 só com `banco = ok`**; `desatualizado` e `erro` devolvem **503** com o mesmo JSON. O driver
  do laço faz `curl -fsS /saude` e trata 503 como falha visível.
- `servicos.<nome>`: `ausente` quando `PLAT_<NOME>_URL` não está no `.env`; `ok` quando um GET com
  timeout de 1 s devolve status < 500 (o Garage responde 403 sem assinatura, por isso o critério é
  "< 500"); `erro` caso contrário. Hoje os três são informativos e não mudam o status HTTP.
- `git_sha`: 12 primeiros caracteres do commit, lidos de `.git/HEAD` e da ref (ou `packed-refs`) na
  partida; sem `.git` (instalação por tarball), lê `PLAT_GIT_SHA` do ambiente ou do `.env`, que o
  `install.sh` grava a cada execução. Sem nenhum dos dois a aplicação não sobe. Medido: `git_sha` de
  `/saude` = `git rev-parse HEAD` = `8ffe950516f5`.
- `tempo_ms`: da entrada da rota à montagem do JSON.

`GET /api/versao` e `HEAD /api/versao` (sem banco, sempre 200):
`{"versao", "git_sha", "ambiente", "em"}`.

`GET /api/openapi.json` (2 caminhos: `/saude`, `/api/versao`) e `GET /api/docs` (só GET; `HEAD` devolve
405). O `docs/openapi.json` comitado é gerado por `make openapi` e igual ao servido. A interface Swagger
é servida de `web/vendor/swagger-ui-bundle-5.32.15.js` e `swagger-ui-5.32.15.css` (Apache-2.0, sha256 em
`VERSOES.txt`), com o validador externo desligado: 0 URL externa no HTML de `/api/docs` (medido pelo
testador e, em chromium real, pelo adversário); `/docs` e `/redoc` devolvem 404.

Latências medidas pelo testador (rodada 2, 20 chamadas cada, do próprio servidor):
`/saude` pela URL pública com conexão TLS nova a cada chamada = mediana 19,8 ms, p95 21,0 ms
(`curl -s -o /dev/null -w %{time_total}`); com conexão reaproveitada = mediana 1,9 ms, p95 2,8 ms;
direto em `http://127.0.0.1:8150/saude` = mediana 1,4 ms (rodada 1). Pelo `TestClient`
(`tests/api/test_saude.py`): `/saude` 1,87 ms, `/api/versao` 0,85 ms (medianas). Nenhuma dessas medidas representa um usuário remoto.

---

## 9. Configuração, log, testes e medidas

### 9.1 `.env` (`app/settings.py`)

Lido com `python-dotenv`; variável de ambiente do processo vence o arquivo. Chave obrigatória ausente ou
inválida aborta a partida nomeando a chave (`ErroConfiguracao`).

| chave | obrigatória | validação |
|---|---|---|
| `PLAT_DSN` | sim | começa com `postgresql://` |
| `PLAT_SECRET` | sim | 64 caracteres hexadecimais |
| `PLAT_AMBIENTE` | sim | `producao` ou `dev` |
| `PLAT_URL_PUBLICA` | sim | começa com `https://` |
| `PLAT_GIT_SHA` | não | gravado pelo `install.sh` com o sha do HEAD a cada execução; só é lido quando não há `.git` |
| `PLAT_MARTIN_URL`, `PLAT_TITILER_URL`, `PLAT_GARAGE_URL` | não | sondas de `/saude` |
| `PLAT_LOG_NIVEL` | não | `DEBUG`/`INFO`/`WARNING`/`ERROR`; `DEBUG` em `producao` é rebaixado para `INFO` com aviso |

Segredo nunca em argumento de linha de comando nem na unidade systemd: a senha do banco vai por stdin
ao `psql` e a senha dos administradores de demonstração vai por stdin ao Python (o adversário da rodada
1 tinha encontrado essa senha no `COMMAND=` que o `sudo` grava no journal; na rodada 2, 0 ocorrências
durante e depois da reinstalação).

### 9.2 Log (`app/log.py`, `app/main.py`)

Uma linha JSON por evento em stdout, recolhida pelo journal: `ts` (ISO 8601 UTC), `nivel`, `msg`,
`logger`; na linha de acesso, `req_id` (16 hex, também devolvido no cabeçalho `X-Req-Id`), `metodo`,
`rota`, `status`, `tempo_ms`, `ip`; exceção em `exc`. `/saude` e `/api/versao` são registradas em
`DEBUG` (o driver do laço as chama a cada 30 min). Leitura: `journalctl -u plat-api -o cat | jq`.
Medido na rodada 2: 3 linhas `ERROR` no journal, todas `saude: banco em erro` nos instantes em que outro
papel apagava o schema com o serviço no ar (a refutação destrutiva); o contrato devolveu 503, como deve.
Quem for reinstalar do zero para o serviço antes do `DROP` se quiser journal sem ruído.

O middleware **não grava** em `plat.log_acesso`; a função `plat.log_registrar` existe e está testada, e a
gravação por rota autenticada entra com o item L0-02.

### 9.3 venv e `make check`

- `venv/` criada com `--system-site-packages` (Python 3.12.3) para reaproveitar os pacotes dpkg
  (`python3-uvicorn 0.27.1`, `python3-psycopg2 2.9.9`), mas sempre com `PYTHONNOUSERSITE=1` (Makefile,
  unidade, `install.sh`): nada vem do diretório do usuário. `requirements.txt` fixa com `==` toda
  dependência da aplicação (`fastapi 0.138.0`, `starlette 1.3.1`, `pydantic 2.13.4`, `python-dotenv
  1.2.2` e transitivas) e da suíte (`httpx 0.28.1`, `pytest 9.1.1`, `pytest-playwright 0.9.0`,
  `playwright 1.59.0`, `ruff 0.16.6` e transitivas).
- `make check` = `lint` (ruff em `app` e `tests`) → `sem-marcador` (grep com `tests/marcadores.regex`
  sobre `app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md`; qualquer
  linha encontrada reprova) → `teste` (`pytest -m "not lento"`) → `e2e` (`pytest -m lento --base-url
  <PLAT_URL_PUBLICA>`). `make check-rapido` é o mesmo sem e2e (é o que o driver roda). `make medidas`
  roda a suíte inteira com `PLAT_GRAVAR_MEDIDAS=1`; `make vendor` confere os sha256 de `web/vendor/`
  contra `VERSOES.txt`.
- Medido (rodada 2, sobre `8ffe950`): 82 testes coletados (`pytest --collect-only -q`: unit 31, api 50,
  e2e 1); 81 rápidos passando + 1 e2e passando; `make check` rc=0, 2,86 s (`/usr/bin/time -f %e make
  check`); árvore limpa depois (`git status --short` = 0 linhas); 0 linhas de marcador de pendência com
  a expressão do driver no escopo ampliado; `make vendor` = 4 arquivos OK.

| diretório | o que prova | precisa de |
|---|---|---|
| `tests/unit/` | `settings` (10), `versao` (6), `instalador` (5), `dependencias` (4), `log` (2), `senha` (2), `vendor` (2) | nada |
| `tests/api/test_saude.py` | contrato de `/saude` e `/api/versao`, `Cache-Control`, `X-Req-Id`, mesma implantação | `.env`, banco |
| `tests/api/test_banco.py` | conexão TCP como `plat_app` (prova da linha do pg_hba), sem posse, sem BYPASSRLS, extensões, `versao_migracao` só leitura | banco |
| `tests/api/test_migracoes.py` | duas rodadas do `migrar.sh` = 0 linhas novas; cópia editada = código 3 e tabela intacta; toda tabela com `tenant_id` tem RLS e política | `sudo -u postgres` sem senha |
| `tests/api/test_rls.py` | 0 linhas sem contexto; `demo` só vê `demo`; INSERT cruzado falha; contexto morre no rollback; `log_acesso` só pela função | banco |
| `tests/api/test_cabecalhos.py` | HTTP real na URL pública (26 casos): noindex, HSTS, `no-store`, `nosniff`, `X-Req-Id` só na API (prova do `alias`), 301 do http | DNS e HTTPS (pulado se o nome não resolver) |
| `tests/api/test_docs.py` | `/api/docs` servido do disco, sem URL externa | `.env` |
| `tests/e2e/test_saude_pagina.py` | chromium do playwright em `/`: 0 erro de console, 0 resposta ≥ 400, versão da tela = `/api/versao`, captura `tests/e2e/capturas/L0-01-repo_inicio.png` | DNS e HTTPS |

### 9.4 Medidas

Fixture `medida(item)(nome, valor, unidade, comando)` em `tests/conftest.py` grava
`tests/medidas/<item>.json` (`{"item", "gerado_em", "git_sha", "medidas": {nome: {valor, unidade,
comando}}}`) **só com `PLAT_GRAVAR_MEDIDAS=1`** no ambiente, para que a suíte não suje a árvore do git
(o testador grava com `make medidas`; o driver e o `make check` não: `git status` fica limpo). O arquivo
`L0-01-repo.json` atual foi assinado pelo testador na rodada 2 e traz, além das medidas do teste, as
que ele fez por `curl`, `psql` e `systemctl`, cada uma com o comando e a rodada. Documento cita número
só por esse caminho.

---

## 10. Front (`web/`)

Módulos ES nativos sem bundler (`app.js` importa `./js/core.js`), MapLibre GL JS 4.7.1 (BSD-3-Clause) e
Swagger UI 5.32.15 (Apache-2.0) em `web/vendor/`, com a versão no nome do arquivo e sha256 em
`VERSOES.txt` (`make vendor` confere), servidos pelo nginx com `no-store`; `favicon.svg` próprio. A única tela é a página
inicial: nome, aviso "análise / beta privado", versão/git/ambiente de `/api/versao` e o JSON de `/saude`
com o estado colorido; marca `body[data-pronto=1]` quando as duas chamadas terminam. Nenhum botão,
nenhum mapa (o MapLibre está no repositório, mas nenhuma tela o carrega ainda). Medido no chromium do
playwright (rodada 2): página pronta em 62,6 ms (`goto('/')` até `body[data-pronto=1]`), primeira
pintura de conteúdo em 48 ms (`performance.getEntriesByType('paint')`).

Regras: importação relativa, nunca `?v=`; biblioteca nova entra em `vendor/` com linha em `VERSOES.txt`
(licença BSD, MIT, Apache 2.0 ou ISC); módulo próprio ≤ 60 kB.

---

## 11. Convenções que valem para todo item

1. Número em README, MANUAL, ARQUITETURA ou PARIDADE sai de `tests/medidas/*.json`, com o comando.
2. Identificadores expostos em português (rotas, colunas, mensagens, nomes de teste); inglês só onde a
   biblioteca exige ou onde o mercado usa o termo (`tenant_id`, `token`, `slug`, `hash`).
3. Nenhum nome de cliente, parceiro ou piloto em código, dado, teste, captura ou documento; o serviço de
   referência desta máquina é chamado "SIG de teste interno". Inquilinos de demonstração: `demo`, `demo2`.
4. Nada manual fora de script: o que o `install.sh` não faz, não existe.
5. Serviço novo = unidade `plat-<nome>` em `deploy/`, porta da faixa 8150-8159, campo em `/saude`, linha
   na seção 1 deste arquivo, no mesmo turno.
6. Migração aplicada é imutável; correção vem em arquivo novo. Toda tabela com `tenant_id` nasce com
   `ENABLE ROW LEVEL SECURITY` e política `FOR ALL TO plat_app USING ... WITH CHECK ...`.
7. Toda função visível tem e2e playwright com captura em `tests/e2e/capturas/<item>_<tela>.png`.

---

## 12. O que ainda não existe

Este repositório, em 0.1.0, é fundação: instala, sobe, responde saúde e isola inquilinos no banco. Não
tem login, catálogo, camada, mapa, tile, edição, serviço OGC ou Esri-compatível, fila, motor
multicritério, rede de utilidades, construtor, conector nem operação. Nomeadamente:

- `plat-martin` (8151), `plat-titiler` (8152) e `plat-worker` (8153): portas reservadas, serviços
  inexistentes (itens L2-01, L1-01, L0-05).
- Rotas autenticadas, cookie de sessão, 2FA, token de serviço com escopo, gravação em `log_acesso`
  (item L0-02); as funções SQL existem, a API não as chama.
- `docs/PARIDADE.md` só com cabeçalho: não há capacidade de usuário para comparar com o ArcGIS
  Enterprise. A paridade-alvo dos itens L0-02 e L0-03 está escrita no handoff
  `laco/handoffs/T1/21_esri.md` e entra na tabela quando esses itens forem entregues.
- Teste automático do modo `-- reaplicavel` do `migrar.sh` (entra com a primeira migração que o use).
- Medição em máquina realmente nova (a "máquina que nunca viu o repositório" foi simulada nesta, com
  venv e certificado já existentes); caminhos do `install.sh` só lidos: `.env` inexistente na rodada 2,
  certbot emitindo (i2/i3), `nginx -t` reprovando.
- Carga, concorrência e memória sob uso (só o repouso foi medido; item L7-02).

O placar do laço, a tabela dos 57 itens do backlog e a fronteira por linha (o que o produto NÃO faz ainda)
estão em `/home/dev/plataforma/laco/PAINEL.md`, gerado por `laco/gera_painel.py` a partir de
`laco/estado.json`.
