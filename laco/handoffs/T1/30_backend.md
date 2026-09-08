# T1 · 30_backend — backend · item L0-01-repo

## Objetivo

Implementar, arquivo por arquivo, a lista "Para o próximo papel" do `20_arquitetura.md` sobre o
contrato do `docs/adr/0001-fundacao.md`: API mínima (`/saude`, `/api/versao`, página inicial),
migrações idempotentes com aplicador por sha256, `install.sh` idempotente que sobe `plat-api`
(:8150) atrás de `https://plat.iagrointel.com` com `noindex`, `make check` verde de verdade e
testes que provam RLS, pg_hba, idempotência e cabeçalhos. Sem marcador de pendência em código
entregue. Commit em português.

## O que fiz

Repositório `/home/dev/plataforma/enterprise`, commits `904a849` (código) e `b22761e` (medidas
regeneradas). 42 arquivos, 2.529 linhas no primeiro commit. Lista do handoff 20 e o que cada item
virou:

| nº | arquivo | estado |
|---|---|---|
| 1 | `VERSAO` | `0.1.0` |
| 2 | `pyproject.toml` | bloco do ADR 10 **+ `pythonpath = ["."]`** (sem isso `tests/` não importa `app`; medido: `ModuleNotFoundError`) e `extend-exclude = ["venv", "web/vendor"]` no ruff |
| 3 | `requirements.txt` | só `pytest==9.1.1`, `pytest-playwright==0.9.0`, `playwright==1.59.0`, `ruff==0.16.6`; nada instalado além disso |
| 4 | `.env.exemplo`, `.gitignore` | 9 chaves; `!.env.exemplo`, `tests/credenciais.txt`, caches |
| 5-6 | `app/__init__.py`, `app/settings.py` | `carregar(dict) -> Settings` congelado; valida DSN, `PLAT_SECRET` 64 hex, ambiente, `https://`; rebaixa DEBUG em producao com aviso; `settings` é carregado na primeira leitura (módulo `__getattr__`) para os testes de unidade não exigirem `.env` |
| 7 | `app/log.py` | `FormatadorJSON` (ts UTC, nivel, msg, logger + campos de requisição), `configurar()`, `req_id()` 16 hex; sem dependência |
| 8 | `app/versao.py` | `versao()`, `git_sha()` lendo `.git/HEAD` → ref → `packed-refs`, alternativa `PLAT_GIT_SHA`; `git_sha_curto()` = 12 caracteres |
| 9 | `app/db.py` | pool criado na 1ª chamada; `Contexto`; `db(ctx)` com 9 tentativas só na preparação e `putconn(close=True)` na falha; `migracoes_estado()` |
| 10 | `app/saude.py` | contrato do ADR 7; 200 só com `banco = ok`; sondas com timeout 1 s e critério `< 500`; **HEAD aceito** em `/saude` e `/api/versao` fora do esquema OpenAPI (o pedido exige `curl -sI` = HEAD; `@router.get` devolvia 405, medido) |
| 11 | `app/main.py` | middleware `X-Req-Id` + linha JSON de acesso (`/saude` e `/api/versao` em DEBUG para não poluir o journal com o driver); `/` devolve `web/index.html`; sem `StaticFiles` |
| 12 | `db/migracoes/001_fundacao.sql` | role `LOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE`, schema, `versao_migracao`, `tenant_atual()`/`usuario_atual()`, grants + `ALTER DEFAULT PRIVILEGES`; `REVOKE INSERT/UPDATE/DELETE ON versao_migracao FROM plat_app` (o ADR diz "plat_app só lê") |
| 13 | `db/migracoes/002_identidade.sql` | 5 tabelas + 4 índices do ADR 6; RLS `FOR ALL TO plat_app USING/WITH CHECK` em tenant/usuario/sessao/token_servico; `log_acesso` com política `FOR SELECT` e `REVOKE` de escrita (escrita só por `plat.log_registrar`); 9 funções `SECURITY DEFINER` com as assinaturas do ADR; semeia `demo`/`demo2` com `ON CONFLICT DO NOTHING` |
| 14 | `db/migrar.sh` | ordem lexicográfica, sha256, `igual`/`aplicada`/`reaplicada`, código 3 em divergência, `-- reaplicavel`, uma transação por arquivo (`psql -1 -f -` por stdin, `ON_ERROR_STOP=1`); `duracao_ms` calculado no banco (`clock_timestamp() - now()`) dentro da mesma transação; variáveis `PLAT_DB`, `PLAT_MIGRACOES` |
| 15-16 | `deploy/plat-api.service`, `deploy/nginx.conf` | textos do ADR 4.1/4.2 com marcadores `APP_DIR`/`APP_USER`/`PORTA`/`DOMINIO` |
| 17 | `install.sh` | passos a-j; `.env` 600 criado uma vez e senha da role **sempre** realinhada (risco 6 do ADR); linha pg_hba por regex exata; venv; **passo g** semeia os admins de `demo`/`demo2` com senha em `tests/credenciais.txt` (600, fora do git) e hash calculado por `app/senha.py`; unidade + `restart` + espera ≤ 30 s; nginx reescrito preservando as 5 linhas do certbot (awk sobre o 1º bloco) e o bloco 80 verbatim; certbot só sem certificado; conferência pública com **até 15 tentativas** (o `reload` do nginx é assíncrono: o 1º `curl` imediato devolveu 503 do bloco velho, medido) |
| 18 | `Makefile`, `tests/marcadores.regex` | alvos do ADR 10; a expressão do driver vive só em `tests/` |
| 19 | `web/` | `index.html` (noindex), `app.js`, `js/core.js`, `style.css`, `vendor/maplibre-gl.{js,css}` (cópia do `fgr/sig`, sha256 em `VERSOES.txt`); a página mostra nome, "análise / beta privado", versão/git/ambiente de `/api/versao` e o JSON de `/saude` com estado; marca `body[data-pronto=1]` para o e2e; nenhum botão |
| 20 | `tests/conftest.py` | `env`, `cliente` (TestClient), `conexao_plat_app` (TCP, `PLAT_DSN`), `base_url` (sobrepõe o do pytest-playwright: `--base-url` ou `.env`), `url_publica_resolve`, `medida(item)` |
| 21-22 | `tests/unit/test_versao.py`, `test_settings.py` (+ `test_senha.py`, `test_log.py`) | 15 testes sem rede e sem banco |
| 23 | `tests/api/test_saude.py` | contrato completo, `Cache-Control`, `X-Req-Id`, mesma implantação, medidas `latencia_saude_ms`/`latencia_versao_ms` (mediana de 20) |
| 24 | `tests/api/test_banco.py` | TCP como `plat_app` (prova do pg_hba), `current_user`, sem posse, sem BYPASSRLS/superuser, extensões, `versao_migracao` só leitura |
| 25 | `tests/api/test_migracoes.py` | duas rodadas = 0 linhas novas; cópia editada → código 3 e tabela intacta; toda tabela com `tenant_id` com `relrowsecurity` e ≥ 1 política; `tenant` com RLS |
| 26 | `tests/api/test_rls.py` | 0 linhas sem contexto (5 tabelas); `demo` só vê `demo`, `demo2` só `demo2`; INSERT cruzado falha no `WITH CHECK`; INSERT próprio passa; contexto morre no rollback; `log_acesso` só pela função |
| 27 | `tests/api/test_cabecalhos.py` | HTTP real em `https://plat.iagrointel.com`: noindex em 8 rotas (inclui `/static/vendor/maplibre-gl.js`, `/api/docs`, `/api/openapi.json`), `no-store` + `nosniff` nos módulos, estático sem `X-Req-Id` (prova do `alias`), `X-Req-Id` na API, 301 do http, `X-Frame-Options` |
| 28 | `tests/e2e/test_saude_pagina.py` | `lento`+`e2e`; 0 erro de console/página, 0 resposta ≥ 400, versão da tela = `/api/versao`, captura `tests/e2e/capturas/L0-01-repo_inicio.png`, medidas `pagina_pronta_ms` e `primeira_pintura_ms` |
| 29 | `docs/openapi.json` | gerado por `make openapi`, comitado; 2 caminhos; 0 marcador |
| 30 | `ARQUITETURA.md` | não tocado (cronista); a lista de portas/unidades/arquivos está abaixo |

Arquivo fora da lista: `app/senha.py` (pbkdf2_sha256, 600.000 iterações, formato do ADR 6.6). É o
que o `install.sh` usa para semear os administradores sem senha em SQL; o L0-02 reusa no login.

Rodei eu mesmo a refutação literal do item antes de entregar: `DROP SCHEMA plat CASCADE; DROP OWNED
BY plat_app; DROP ROLE plat_app;` → `install.sh` → `make check` (evidência abaixo).

## Evidência (comandos e saídas literais)

### install.sh sobre máquina já instalada (idempotência; 5ª execução, após o commit)

```
$ sudo bash install.sh plat.iagrointel.com 8150
== a. máquina
/dev/vda2       469G  451G   13G  98% /
Mem:              23          19           0           6           9           3
app_dir=/home/dev/plataforma/enterprise usuario=dev banco=iagro_sat porta=8150 dominio=plat.iagrointel.com
== b. extensões
== c. migrações
igual      001_fundacao
igual      002_identidade
migracoes: aplicadas 0 · reaplicadas 0 · iguais 2 · pendentes 0
== d. .env e senha da role
.env já existe (mantido)
senha de plat_app alinhada ao .env
== e. pg_hba
linha já existe em /etc/postgresql/16/main/pg_hba.conf
== f. venv
venv: Python 3.12.3 · pytest 9.1.1
== g. administradores de demonstração
admin de demo semeado
admin de demo2 semeado
== h. systemd plat-api
/saude local respondeu 200 em 2 s
● plat-api.service - plat — API da plataforma SIG (FastAPI :8150). Interno. Análise / beta privado.
     Loaded: loaded (/etc/systemd/system/plat-api.service; enabled; preset: enabled)
     Active: active (running) since Sat 2026-09-05 12:42:22 UTC; 1s ago
   Main PID: 2425678 (python)
== i. nginx
bloco reescrito preservando 5 linhas do certbot
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
== j. conferência pública
https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow
== instalado em 4 s: https://plat.iagrointel.com (serviço plat-api, porta 8150)
```

### install.sh do zero (refutação literal simulada: schema e role apagados)

```
$ sudo systemctl stop plat-api
$ sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 -X -q -f - <<'SQL'
DROP SCHEMA IF EXISTS plat CASCADE;
DROP OWNED BY plat_app;
DROP ROLE IF EXISTS plat_app;
SQL
psql:<stdin>:1: NOTICE:  drop cascades to 17 other objects
$ sudo -u postgres psql -d iagro_sat -Atc "select count(*) from pg_namespace where nspname='plat'; select count(*) from pg_roles where rolname='plat_app';"
0
0
$ /usr/bin/time -f "tempo_real_s=%e" sudo bash install.sh plat.iagrointel.com 8150
== c. migrações
aplicada   001_fundacao (67 ms)
aplicada   002_identidade (1770 ms)
migracoes: aplicadas 2 · reaplicadas 0 · iguais 0 · pendentes 0
== d. .env e senha da role
senha de plat_app alinhada ao .env
== e. pg_hba
linha já existe em /etc/postgresql/16/main/pg_hba.conf
== g. administradores de demonstração
admin de demo semeado
admin de demo2 semeado
== h. systemd plat-api
/saude local respondeu 200 em 2 s
== i. nginx
bloco reescrito preservando 5 linhas do certbot
== j. conferência pública
https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow
== instalado em 7 s: https://plat.iagrointel.com (serviço plat-api, porta 8150)
tempo_real_s=6.63
```
(A 1ª instalação da máquina, 12:38, acrescentou a linha: `linha acrescentada em
/etc/postgresql/16/main/pg_hba.conf`; `.env criado`; `tests/credenciais.txt criado`.)

### migrar.sh duas vezes (antes do install.sh)

```
$ bash db/migrar.sh
aplicada   001_fundacao (2364 ms)
aplicada   002_identidade (5001 ms)
migracoes: aplicadas 2 · reaplicadas 0 · iguais 0 · pendentes 0
rc=0
$ bash db/migrar.sh
igual      001_fundacao
igual      002_identidade
migracoes: aplicadas 0 · reaplicadas 0 · iguais 2 · pendentes 0
rc=0
```

### make check (suíte inteira)

```
$ make check
venv/bin/ruff check app tests
All checks passed!
! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile
venv/bin/pytest -m "not lento"
.........................................................                [100%]
57 passed, 1 deselected, 1 warning in 1.04s
venv/bin/pytest -m lento --base-url https://plat.iagrointel.com
.                                                                        [100%]
1 passed, 57 deselected in 0.55s
check rc=0
```
O único aviso é `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
install httpx2` (starlette 1.3.1 do sistema); não instalei `httpx2` (disco a 98 %, nada além do
`requirements.txt`).

### curl na URL pública

```
$ curl -sI https://plat.iagrointel.com/saude
HTTP/1.1 200 OK
Server: nginx
Date: Sat, 05 Sep 2026 12:42:26 GMT
Content-Type: application/json
Content-Length: 270
Connection: keep-alive
cache-control: no-store
x-req-id: 6e130a3a86dea64a
Cache-Control: no-store, must-revalidate
X-Robots-Tag: noindex, nofollow
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
$ curl -s https://plat.iagrointel.com/saude
{"versao":"0.1.0","git_sha":"904a849d81a0","ambiente":"producao","banco":"ok","migracoes_aplicadas":2,"migracoes_pendentes":0,"ultima_migracao":"002_identidade","servicos":{"martin":"ausente","titiler":"ausente","garage":"ok"},"tempo_ms":1.6,"em":"2026-09-05T12:42:26Z"}
```
Depois do commit das medidas o serviço foi reiniciado pelo `install.sh` e mostra o HEAD:
```
$ curl -s https://plat.iagrointel.com/saude | python3 -c "import json,sys; print(json.load(sys.stdin)['git_sha'])"; git rev-parse --short=12 HEAD
b22761e1c785
b22761e1c785
```

### serviço, banco, log

```
$ systemctl status plat-api --no-pager -l | head -6
● plat-api.service - plat — API da plataforma SIG (FastAPI :8150). Interno. Análise / beta privado.
     Loaded: loaded (/etc/systemd/system/plat-api.service; enabled; preset: enabled)
     Active: active (running) since Sat 2026-09-05 12:41:34 UTC; 4s ago
     Memory: 89.9M (high: 768.0M max: 1.0G available: 678.0M peak: 90.6M)
$ systemctl show plat-api -p MemoryCurrent -p MemoryPeak -p NRestarts
NRestarts=0
MemoryCurrent=94273536
MemoryPeak=95031296
$ sudo grep -n "plat_app" /etc/postgresql/16/main/pg_hba.conf
35:host    iagro_sat       plat_app        127.0.0.1/32            scram-sha-256
$ ss -ltnp | grep 8150
LISTEN 0 2048 127.0.0.1:8150 0.0.0.0:* users:(("python",pid=2423240,fd=3),("python",pid=2423239,fd=3),("python",pid=2423234,fd=3))
$ sudo -u postgres psql -d iagro_sat -Atc "select rolname, rolbypassrls, rolsuper from pg_roles where rolname='plat_app'; select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='plat' and relkind='r' order by 1;"
plat_app|f|f
log_acesso|t
sessao|t
tenant|t
token_servico|t
usuario|t
versao_migracao|f
$ journalctl -u plat-api -o cat -n 1 --no-pager
{"ts": "2026-09-05T12:41:37.808+00:00", "nivel": "INFO", "msg": "acesso", "logger": "plat.acesso", "req_id": "0af936c2de977658", "metodo": "GET", "rota": "/", "status": 200, "tempo_ms": 0.6, "ip": "216.238.123.14"}
$ ls -la .env tests/credenciais.txt
-rw------- 1 dev dev 341 Sep  5 12:38 .env
-rw------- 1 dev dev  57 Sep  5 12:38 tests/credenciais.txt
$ sudo -u postgres psql -d iagro_sat -Atc "select count(*) from pg_stat_activity where usename='plat_app'"
2
```

### medidas (`tests/medidas/L0-01-repo.json`, gerado pelos testes)

```
latencia_saude_ms      1.67  mediana de 20 GET /saude pelo TestClient
latencia_versao_ms     0.66  mediana de 20 GET /api/versao pelo TestClient
pagina_pronta_ms       49.9  goto('/') até body[data-pronto=1] no chromium do playwright
primeira_pintura_ms    36    first-contentful-paint no chromium do playwright
```
Medido fora dos testes (não está no JSON; o testador decide se entra): instalação do zero 6,63 s
(`/usr/bin/time`), reinstalação 4-7 s, RAM do serviço 90 MB em uso / 95 MB de pico com 2 workers.

### commits

```
$ git log --oneline | head -3
b22761e Medidas do item L0-01-repo regeneradas sobre o commit 904a849
904a849 Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes
a1d0c20 Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0)
$ git status --short | wc -l
0
```

## Portas, unidades, arquivos (para o cronista pôr em ARQUITETURA.md)

- `plat-api` · systemd `/etc/systemd/system/plat-api.service` (gerado de `deploy/plat-api.service`) ·
  uvicorn 2 workers em `127.0.0.1:8150` · `MemoryHigh=768M`, `MemoryMax=1G` · `Restart=on-failure`.
- nginx `/etc/nginx/sites-enabled/plat.iagrointel.com` (gerado de `deploy/nginx.conf` + linhas do
  certbot) · `/static/` = `alias` para `web/` com `no-store` · `/` = proxy para :8150 · `X-Robots-Tag`
  em todo bloco.
- banco `iagro_sat`, schema `plat` (dono `postgres`), role `plat_app` (LOGIN, sem BYPASSRLS, sem
  posse), pg_hba linha 35, senha no `.env` (600), tabela de controle `plat.versao_migracao`.
- pool: 1-8 conexões por worker (2 em uso em repouso, medido).
- `/saude` sonda `PLAT_GARAGE_URL` (=`http://127.0.0.1:3900`, responde `ok`); martin e titiler `ausente`
  até L2-01/L1-01.

## Riscos

1. **`git_sha` é lido uma vez na partida** (ADR 7). Todo commit sem reinício deixa `/saude` um sha
   atrás do HEAD. O `install.sh` sempre reinicia, então o caminho oficial não sofre; quem comita e
   não roda `install.sh` vê a diferença. O testador deve comparar `/saude.git_sha` com `git rev-parse`.
2. **Reload do nginx é assíncrono**: por 1-3 s os workers antigos servem o bloco anterior. O
   `install.sh` espera até 15 s no passo j. Qualquer script que edite nginx e meça em seguida
   precisa da mesma espera.
3. `HEAD` em `/saude` e `/api/versao` é rota fora do esquema; a doc OpenAPI só lista GET. Se alguém
   trocar `add_api_route(..., methods=["HEAD"])` por `api_route(GET, HEAD)`, o OpenAPI acusa
   `Duplicate Operation ID` (medido) e o `curl -sI` continua 200; o inverso (só `@router.get`) dá 405.
4. `-- reaplicavel` do `migrar.sh` está implementado mas **sem teste automático**: testá-lo contra o
   banco real deixaria o sha registrado de `001` divergente do arquivo do repositório (o registro só
   volta com UPDATE como `postgres`, que os testes não fazem por regra). Fica para quando nascer a
   primeira migração legitimamente reaplicável (só `CREATE OR REPLACE`).
5. `tests/api/test_migracoes.py` executa `db/migrar.sh` de verdade (via `sudo -u postgres`): em
   máquina sem sudo sem senha para `dev`, o teste falha por permissão, não por defeito.
6. As duas primeiras aplicações de DDL levaram 2,4 s e 5,0 s (instância compartilhada com 12
   sessões; espera por lock), a reinstalação do zero levou 67 ms e 1.770 ms. Tempo de migração não
   é métrica estável nesta máquina.
7. `ip` no log de acesso vem do `X-Forwarded-For` que o nginx envia (`--proxy-headers
   --forwarded-allow-ips 127.0.0.1`): o e2e desta máquina aparece como `216.238.123.14` (saída
   pública do próprio servidor), o que é correto.
8. A venv usa `--system-site-packages`: fastapi 0.138.0, starlette 1.3.1, uvicorn 0.27.1, psycopg2
   2.9.9, httpx 0.28.1, python-dotenv 1.2.2 vêm do sistema e não estão fixados em `requirements.txt`
   (decisão do ADR 2.1; o L7-01 fecha).

## Pendências

- P1 (para o gerente, corrige a pendência P1 do arquiteto): o `driver.sh` passo 4 **já usa**
  `./venv/bin/python -m pytest` (lido hoje), não o Python do sistema; `ultimo_check.txt` vai
  refletir a venv. Nada a mudar.
- P2 (gerente/cronista): `ARQUITETURA.md`, `MANUAL.md`, `CHANGELOG.md`, `README.md` não foram
  tocados por mim (papel do cronista); a seção acima tem o material.
- P3 (L0-02): o middleware ainda não grava em `plat.log_acesso` (só a função SQL existe e está
  testada); `app/senha.py` está pronto para o login.
- P4: `docs/PARIDADE.md` não está ignorado pelo `.gitignore` (o handoff 20 dizia que estava); está
  versionado desde o turno 0. Deixei como está.

## Para o próximo papel (testador, handoff 40)

1. Rodar a refutação literal do zero, medindo: `sudo systemctl stop plat-api`, `DROP SCHEMA plat
   CASCADE; DROP OWNED BY plat_app; DROP ROLE plat_app;` (o `DROP OWNED` é obrigatório antes do
   `DROP ROLE`: os grants e os privilégios padrão dependem da role), depois
   `/usr/bin/time -f %e sudo bash install.sh plat.iagrointel.com 8150` e `make check`.
   Opcionalmente apagar também a linha 35 do pg_hba e `.env` e `tests/credenciais.txt` para ver
   os três caminhos "criado" (pg_hba, `.env`, credenciais); os admins de demonstração ganham senha
   nova nesse caso.
2. Conferir `curl -sI https://plat.iagrointel.com/saude` (200, `X-Robots-Tag`) e também
   `curl -s -o /dev/null -w '%{http_code}' https://plat.iagrointel.com/api/docs` (200, noindex).
3. Comparar `/saude.git_sha` com `git rev-parse --short=12 HEAD` (risco 1).
4. Escrever `tests/medidas/L0-01-repo.json` com o que o portão pede: tempo de instalação do zero,
   nº de testes (57 rápidos + 1 e2e), latência de `/saude` **pela URL pública** (a medida atual é
   TestClient, sem nginx/TLS), cabeçalho `X-Robots-Tag`, RAM do serviço (`systemctl show plat-api
   -p MemoryCurrent -p MemoryPeak`). A fixture `medida("L0-01-repo")` grava no mesmo arquivo.
5. Teste cruzado A→B (P6): `tests/api/test_rls.py` já prova `demo`→`demo2` no banco; não há rota
   autenticada ainda (L0-02), logo "em toda rota" só vale para `/saude`, `/api/versao` e `/`, que
   não devolvem dado de inquilino.
6. Verificar que `tests/e2e/capturas/L0-01-repo_inicio.png` mostra a página com `saúde ok`,
   `versao 0.1.0` e o git_sha (eu vi a captura: fundo escuro, dois painéis, estado `ok` em verde).
7. Não rodar backend e chromium com um terceiro agente pesado: `free -g` mostrou 3 GB disponíveis
   durante todo o turno; o `make check` completo levou 2,8 s e não passou de 100 MB no serviço.

## Resumo em 8 linhas

1. Lista inteira do handoff 20 construída no repositório `plataforma/enterprise`, commits `904a849` + `b22761e`, 42 arquivos, 0 marcador (varredura do driver = 0 linhas).
2. `sudo bash install.sh plat.iagrointel.com 8150` roda de verdade e é idempotente: 5 execuções, todas rc=0; do zero (schema e role apagados) 6,63 s; reinstalação 4-7 s.
3. `make check` verde: ruff, varredura de marcador, 57 testes rápidos (unit, api, RLS, migrações, cabeçalhos HTTP reais) e 1 e2e playwright com captura, 2,8 s no total.
4. `https://plat.iagrointel.com/saude` = 200 com o JSON do contrato (`banco ok`, 2 migrações, 0 pendentes, `git_sha` = HEAD) e `X-Robots-Tag: noindex, nofollow`; `curl -sI` (HEAD) também 200.
5. RLS provada como `plat_app` (0 linhas sem contexto, `demo`≠`demo2`, INSERT cruzado bloqueado pelo `WITH CHECK`, `log_acesso` só pela função); role sem BYPASSRLS, sem posse, linha 35 do pg_hba, conexão TCP funciona.
6. `migrar.sh` duas vezes = 0 linhas novas; cópia editada devolve código 3 sem tocar no banco; sha256 e duração por arquivo em `plat.versao_migracao`.
7. Desvios do handoff 20, todos com motivo medido: `pythonpath` no pytest, HEAD nas rotas, espera de 15 s após reload do nginx, `app/senha.py` para semear admins sem senha em SQL, teste de `-- reaplicavel` não escrito.
8. Serviço `plat-api` :8150 com 2 workers, 90 MB em uso / 95 MB de pico, 0 reinícios; log JSON no journal; `.env` e `tests/credenciais.txt` em 600 fora do git.
