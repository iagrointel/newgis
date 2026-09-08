# T1 · 20_arquitetura — arquiteto · item L0-01-repo

## Objetivo

Escrever o ADR 0001 (fundação do repositório `plat`) com toda decisão apoiada em medição feita
nesta máquina, em código que já roda em produção aqui (`fgr/sig`, só leitura) ou em documento
oficial; deixar o contrato de esquema, de `/saude`, de testes e de configuração pronto para o
backend implementar sem perguntar nada.

## O que fiz

1. Li, na ordem pedida: `SKILL.md` do laço, `00_plano.md`, o item L0-01-repo e os blocos
   `produto`/`guardrails` do `estado.json`, a seção 17.2 do `DOC.md`.
2. Li (sem editar) o que já roda: `systemctl cat sigcorp`, `/etc/nginx/sites-enabled/fgrsig.iagrointel.com`,
   `/etc/nginx/sites-enabled/plat.iagrointel.com` (bloco inicial do gerente), `fgr/sig/db/schema.sql`,
   `schema_v2.sql`, `schema_v3.sql`, `fgr/sig/app/main.py` (pool com reconexão, `/api/saude`,
   `StaticFiles`), `fgr/sig/install.sh`, `fgr/sig/web/{index.html,app.js,js/,vendor/}`,
   `fgr/sig/pipeline/publicar.sh`, `fgr/sig/tests/test_api.py`, `laco/driver.sh`.
3. Medi: disco, RAM, portas 8150-8159, versão do Postgres/PostGIS, existência de role/schema
   `plat`, linhas do `pg_hba.conf`, RAM do `sigcorp`/`cbresig` em execução, estado de Garage e
   TiTiler, DNS e certificado de `plat.iagrointel.com`, um projeto Vite mínimo com MapLibre
   (disco, arquivos, tempo e RSS de build), o tamanho do front vanilla do `fgr`, a instalação de
   `ruff` na venv, o chromium do playwright a partir da venv e o pytest do Python do sistema.
4. Escrevi `/home/dev/plataforma/enterprise/docs/adr/0001-fundacao.md` (13 seções): layout,
   pilha, pool e RLS, systemd e nginx, migrações com `versao_migracao`, esquema base (tenant,
   usuario, sessao, token_servico, log_acesso, funções `auth_*`), contrato de `/saude` e
   `/api/versao`, `.env`, logging JSON, testes e `make check`, decisão do front por medição,
   regras transversais e custo de reverter.
5. Limpei o scratchpad: `node_modules`, `dist`, cache do npm e do pip apagados (184 MB → 72 kB).

## Evidência (comandos e saídas literais)

Disco e RAM:
```
$ df -h / /mnt/pgdata
/dev/vda2       469G  451G   13G  98% /
/dev/vdb        688G  672G   17G  98% /mnt/pgdata
$ free -g
Mem:              23          19           0           6           9           3
Swap:              7           7           0
```

Portas da faixa reservada (vazio = livres):
```
$ ss -ltnp | grep -E ":815[0-9]"
(nenhuma linha)
```

Banco:
```
$ sudo -u postgres psql -d iagro_sat -Atc "select version(); select postgis_full_version(); select rolname from pg_roles where rolname like 'plat%'; select nspname from pg_namespace where nspname in ('plat','sigcorp','cbresig','acervo'); show max_connections; select count(*) from pg_stat_activity;"
PostgreSQL 16.13 (Ubuntu 16.13-1.pgdg24.04+1) on x86_64-pc-linux-gnu ...
POSTGIS="3.6.3 3d12666" [EXTENSION] PGSQL="160" GEOS="3.12.1-CAPI-1.18.1" PROJ="9.4.0 ..."
plataforma_com_app
cbresig
acervo
sigcorp
100
12
```
Leitura: role `plat_app` NÃO existe (só `plataforma_com_app`, de outra frente); schema `plat`
NÃO existe; `max_connections` 100 com 12 sessões em uso.

pg_hba (roles vizinhas, formato a copiar):
```
$ sudo grep -n "sigcorp\|cbresig\|plat" /etc/postgresql/16/main/pg_hba.conf
24:host    iagro_sat       sigcorp_app     127.0.0.1/32            scram-sha-256
25:host    iagro_sat       cbresig_app     127.0.0.1/32            scram-sha-256
30:host    iagro_sat       plataforma_com_app    127.0.0.1/32            scram-sha-256
```

Unidade systemd de referência:
```
$ systemctl cat sigcorp
ExecStart=/home/dev/fgr/sig/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8125 --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
RestartSec=3
$ systemctl show sigcorp -p MemoryCurrent -p MemoryPeak -p NRestarts -p ActiveState
NRestarts=0
MemoryCurrent=166928384
MemoryPeak=250966016
ActiveState=active
$ systemctl show cbresig -p MemoryCurrent
MemoryCurrent=132935680
```
Leitura: 2 workers da mesma pilha = 167 MB em uso, 251 MB de pico → `MemoryMax=1G` no ADR.

Serviços vizinhos que `/saude` vai observar:
```
$ systemctl is-active plataforma-titiler plataforma-garage
active
active
$ curl -s -m 3 -o /dev/null -w "garage :3900 http %{http_code}\n" http://127.0.0.1:3900/
garage :3900 http 403
$ curl -s -m 3 -o /dev/null -w "titiler :8131 /healthz http %{http_code}\n" http://127.0.0.1:8131/healthz
titiler :8131 /healthz http 200
$ which martin ruff titiler
(nenhum no PATH)
```
Leitura: Garage responde 403 sem assinatura S3 → critério de "ok" em `/saude` é status < 500.
Martin não está instalado (item L2-01). O TiTiler que existe é o da frente `plataforma/pipeline`
(:8131), que NÃO se toca; o do produto será `plat-titiler` em :8152 (item L1-01).

nginx e TLS:
```
$ ls /etc/nginx/sites-enabled/
app.iagrointel.com brusque-cpsi.iagrointel.com cbre.iagrointel.com cpsi-demo.iagrointel.com edpes.iagrointel.com fgrsig.iagrointel.com hacarthon.iagrointel.com iagrosat-db lastrofarma.com plat.iagrointel.com sigcorp.iagrointel.com upload.iagrointel.com
$ cat /etc/nginx/sites-enabled/plat.iagrointel.com   (trecho)
    server_name plat.iagrointel.com;
    add_header X-Robots-Tag "noindex, nofollow" always;
    location / { return 503; }
    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/plat.iagrointel.com/fullchain.pem; # managed by Certbot
$ sudo test -d /etc/letsencrypt/live/plat.iagrointel.com && echo "cert plat: EXISTE"
cert plat: EXISTE
$ getent hosts plat.iagrointel.com
216.238.123.14  plat.iagrointel.com
$ curl -s -m 5 -o /dev/null -w "https://plat.iagrointel.com -> http %{http_code}\n" https://plat.iagrointel.com/saude
https://plat.iagrointel.com -> http 503
$ certbot --version
certbot 2.9.0
```
Leitura: DNS, certificado e bloco inicial já existem (gerente); o `install.sh` só precisa
reescrever o bloco a partir de `deploy/nginx.conf` preservando as linhas do certbot.

Front vanilla do `fgr/sig` (o que roda hoje):
```
$ du -sh /home/dev/fgr/sig/web/js /home/dev/fgr/sig/web/vendor
240K    /home/dev/fgr/sig/web/js
2.5M    /home/dev/fgr/sig/web/vendor
$ ls -la /home/dev/fgr/sig/web/vendor/maplibre-gl.js
-rw-rw-r-- 1 dev dev  803086 Aug 27 18:07 maplibre-gl.js
$ head -c 400 .../maplibre-gl.js | grep -i maplibre
 * @license 3-Clause BSD. Full text of license: https://github.com/maplibre/maplibre-gl-js/blob/v4.7.1/LICENSE.txt
$ cat /home/dev/fgr/sig/web/app.js   (1ª linha)
/* incorporadora de teste SIG — entrada. MapLibre GL JS (BSD-3) + modulos ES sem build. O cache e resolvido por no-store no nginx: NUNCA por ?v= nos imports (duas URLs = duas instancias do modulo). */
```

Projeto Vite mínimo (scratchpad; `vite ^6.3.5` + `maplibre-gl ^5.6.0`):
```
$ time npm install --no-audit --no-fund --loglevel=error
real    0m5.450s
$ du -sh node_modules $SCRATCH/npm-cache; find node_modules -type f | wc -l
78M     node_modules
95M     /tmp/claude-1001/.../scratchpad/npm-cache
1660
$ /usr/bin/time -v npx vite build
dist/assets/index-C3rCLtPo.js  1,056.01 kB │ gzip: 285.43 kB
✓ built in 2.29s
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02.73
        Maximum resident set size (kbytes): 391628
$ du -sh dist
1.1M    dist
```
Limpeza:
```
$ du -sh $SCRATCH; rm -rf $SCRATCH/vite-min/node_modules $SCRATCH/vite-min/dist $SCRATCH/npm-cache $SCRATCH/pip-cache; du -sh $SCRATCH
184M
72K
```

venv do repositório e ruff:
```
$ venv/bin/python -c "import sys; print(sys.version)"
3.12.3 (main, Jun 19 2026, 12:46:00) [GCC 13.3.0]
$ venv/bin/pip list | grep -iE "pytest|playwright|fastapi|psycopg|uvicorn|pydantic|starlette|httpx"
fastapi 0.138.0 · httpx 0.28.1 · playwright 1.59.0 · psycopg2 2.9.9 · pydantic 2.13.4 · pytest 9.1.1 · pytest-base-url 2.1.0 · pytest-playwright 0.9.0 · starlette 1.3.1 · uvicorn 0.27.1
$ time venv/bin/pip install -q ruff
real    0m2.559s
$ venv/bin/ruff --version
ruff 0.16.6
$ du -sh venv/bin/ruff venv
23M     venv/bin/ruff
43M     venv
$ venv/bin/pip list | grep -iE "^(python-dotenv|bcrypt|PyJWT)"
bcrypt 3.2.2 · PyJWT 2.7.0 · python-dotenv 1.2.2     (herdados do sistema via --system-site-packages)
```

Chromium do playwright a partir da venv (sem baixar nada):
```
$ ls ~/.cache/ms-playwright/
chromium-1217 chromium-1223 chromium-1228 chromium-1234 chromium_headless_shell-1217 ... ffmpeg-1011
$ venv/bin/python -c "... p.chromium.launch(); page.goto('https://plat.iagrointel.com/saude'); print(page.title(), browser.version)"
chromium ok, status via título: 503 Service Temporarily Unavailable 147.0.7727.15
```

Pytest do Python do sistema (o que o `driver.sh` passo 4 chama):
```
$ python3 -m pytest --version
/usr/bin/python3: No module named pytest
```

Estado do repositório:
```
$ git log --oneline
a1d0c20 Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0)
$ find db docs tests -type f
docs/PARIDADE.md            (db/migracoes, docs/adr, tests/e2e/capturas, tests/medidas: vazios)
$ git config user.name; git config user.email
iAgroSat
contato@iagrosat.com
```

## Riscos

1. RAM: 3 GB disponíveis. O backend vai subir `plat-api` (≈ 170 MB pelos números do `sigcorp`)
   e o testador vai rodar chromium (centenas de MB). Não rodar backend e testador em paralelo com
   um terceiro agente pesado; `free -g` antes de cada lançamento (regra do laço).
2. `ThreadedConnectionPool(1, 8)` × 2 workers = 16 conexões numa instância com `max_connections`
   100 e 12 em uso; ao somar `plat-worker` e `plat-martin` nos próximos itens, o total da faixa
   `plat` deve ficar declarado em `ARQUITETURA.md` (o L7-02 mede).
3. O `driver.sh` chama `python3 -m pytest` do sistema, que não tem pytest: o passo 4 do driver
   vai gravar erro em `ultimo_check.txt` mesmo com a suíte verde na venv. Não editável por mim
   (fora de `enterprise/` e de `handoffs/T1`).
4. `--system-site-packages` na venv faz `requirements.txt` não descrever o ambiente inteiro; o
   item L7-01 (instalador limpo) vai precisar da lista completa. Mitigação escrita no ADR 2.1.
5. A decisão "sem framework" para os construtores (ADR 11.3) é adiada ao L5-01 com medição. O
   risco é chegar lá com muito código vanilla; a mitigação é a regra de orçamento por módulo.
6. A senha da role e o `PLAT_SECRET` nascem no `install.sh`; se alguém rodar o `install.sh` numa
   máquina onde o `.env` existe com senha diferente da que está no banco, a API sobe e quebra na
   primeira consulta. O `install.sh` deve, quando o `.env` já existe, fazer `ALTER ROLE plat_app
   PASSWORD` com a senha lida do `.env` (idempotência de verdade).

## Pendências (para o gerente)

- P1. `driver.sh` passo 4: trocar `python3 -m pytest` por `/home/dev/plataforma/enterprise/venv/bin/pytest`
  (ou `make check-rapido`), senão `ultimo_check.txt` mente. Fora do meu perímetro.
- P2. Decidir se o `.env` fica na raiz do repositório (padrão `fgr`, adotado no ADR) ou em
  `/etc/plat/`; o ADR escolhe a raiz por ser o que o `sigcorp` faz e por o `.gitignore` já cobrir.
- P3. O `docs/openapi.json` comitado muda a cada rota nova; confirmar que o cronista o regenera
  (`make openapi`) em todo turno.

## Para o próximo papel (backend, handoff 30): construir exatamente isto, arquivo por arquivo

Ler antes: `docs/adr/0001-fundacao.md` inteiro (é o contrato) e `fgr/sig/app/main.py` linhas
36-68 (copiar a substância do pool; nunca editar o `fgr`).

1. `VERSAO` — conteúdo `0.1.0`.
2. `pyproject.toml` — bloco `[tool.pytest.ini_options]` e `[tool.ruff]` exatamente como ADR 10.
3. `requirements.txt` — só o que foi instalado por cima do sistema: `pytest==9.1.1`,
   `pytest-playwright==0.9.0`, `playwright==1.59.0`, `ruff==0.16.6`, mais o que você instalar
   (nada além do necessário; disco a 98 %).
4. `.env.exemplo` — as 9 chaves da tabela do ADR 8, com valores de exemplo, sem segredo.
   `.gitignore`: acrescentar `!.env.exemplo` e `docs/openapi.json` NÃO pode estar ignorado
   (hoje `docs/PARIDADE.md` está ignorado no esqueleto; deixar como está, é do gerente).
5. `app/__init__.py` — vazio.
6. `app/settings.py` — carrega `.env` da raiz com `python-dotenv`; valida obrigatórias
   (`PLAT_DSN`, `PLAT_SECRET` com 64 hex, `PLAT_AMBIENTE` em {producao, dev}, `PLAT_URL_PUBLICA`
   com `https://`); expõe `settings` (dataclass congelada). Falha com mensagem nomeando a chave.
7. `app/log.py` — `configurar()` instala handler JSON por linha em stdout com os campos do ADR 9;
   função `req_id()` (16 hex). Sem dependência externa.
8. `app/versao.py` — `VERSAO` lido do arquivo; `git_sha()` lendo `.git/HEAD` → ref → sha (sem
   subprocesso); fallback `PLAT_GIT_SHA`; abreviar para 7-12 caracteres na resposta.
9. `app/db.py` — `POOL`, `Contexto` (tenant_id, usuario_id, login), `db(ctx=None)` com a
   reconexão da seção 3.2 (só a preparação repete; 9 tentativas; `putconn(close=True)` na
   falha). Preparação: `SET search_path = plat, public` + `set_config(..., true)` ×3 quando há
   contexto. Função `migracoes_estado()` que devolve `(aplicadas, pendentes, ultima)` comparando
   `db/migracoes/*.sql` com `plat.versao_migracao`.
10. `app/saude.py` — `GET /saude` e `GET /api/versao` com o JSON e os códigos do ADR 7
    (200 só com `banco = ok`; 503 nos outros dois; `servicos` com timeout de 1 s por URL,
    `ausente|ok|erro`, critério status < 500).
11. `app/main.py` — cria `FastAPI(title='plat', docs_url='/api/docs', openapi_url='/api/openapi.json')`;
    middleware: `X-Req-Id`, linha JSON de acesso por requisição (sem gravar em `log_acesso`
    neste item; a função SQL nasce na 002 e a chamada entra no L0-02); inclui `saude`; rota `/`
    devolve `web/index.html` (a página mínima do item 13). NÃO montar `StaticFiles` em `/static`
    (o nginx serve).
12. `db/migracoes/001_fundacao.sql` — role (sem senha), schema, grants, `ALTER DEFAULT
    PRIVILEGES`, `versao_migracao`, `tenant_atual()`, `usuario_atual()`. Idempotente.
13. `db/migracoes/002_identidade.sql` — as 5 tabelas do ADR 6 com os índices, RLS
    (`ENABLE` + política `FOR ALL TO plat_app USING/WITH CHECK`), e as funções `SECURITY
    DEFINER` com as assinaturas listadas (corpo seguindo `fgr/sig/db/schema_v3.sql` 204-245,
    adaptado a `token_hash` e `tenant_id` em `sessao`). Semeia `tenant` `demo` e `demo2` com um
    admin cada, senha gerada e gravada em `tests/credenciais.txt` (modo 600, ignorado pelo git)
    pelo `install.sh`, não pelo SQL (senha nunca em SQL do repositório).
14. `db/migrar.sh` — o aplicador do ADR 5 (ordem, sha256, pular igual, código 3 em sha
    diferente, `-- reaplicavel`, uma transação por arquivo via stdin com `ON_ERROR_STOP=1`).
15. `deploy/plat-api.service` — texto do ADR 4.1 com `APP_DIR`, `APP_USER`, `PORTA` como
    marcadores de substituição do `install.sh`.
16. `deploy/nginx.conf` — texto do ADR 4.2 com `DOMINIO`, `APP_DIR`, `PORTA`.
17. `install.sh` — root, idempotente, `set -euo pipefail`; passos com `echo "== passo"`:
    (a) `df`/`free` impressos; (b) extensões `postgis`, `pgcrypto`; (c) `db/migrar.sh`;
    (d) `.env` 600 se não existir (senha `openssl rand -hex 16`, `PLAT_SECRET` `-hex 32`) e
    SEMPRE `ALTER ROLE plat_app PASSWORD` com a senha lida do `.env` (risco 6); (e) linha do
    `pg_hba.conf` se ausente + `pg_reload_conf()`; (f) venv com `--system-site-packages` +
    `pip install -r requirements.txt` (pular se já satisfeito); (g) unidade `plat-api` a partir
    do modelo, `daemon-reload`, `enable --now`, esperar `/saude` local responder 200 em ≤ 30 s
    ou falhar com o `journalctl -u plat-api -n 30`; (h) nginx a partir do modelo preservando as
    linhas `# managed by Certbot` do bloco existente, `nginx -t`, `reload`; `certbot` só se
    `/etc/letsencrypt/live/DOMINIO` não existir; (i) `curl -sI https://DOMINIO/saude` e
    conferência de `X-Robots-Tag`; imprime tempo total. Uso:
    `sudo bash install.sh plat.iagrointel.com 8150`.
18. `Makefile` — alvos do ADR 10 (`check`, `check-rapido`, `lint`, `teste`, `e2e`,
    `sem-marcador`, `migrar`, `openapi`) + `tests/marcadores.regex` com a expressão do
    `laco/driver.sh` (passo 2) em uma linha, usada por `grep -E -f`. A expressão NUNCA aparece
    literal em arquivo fora de `tests/` (o driver se autoacusaria; conferido neste turno). Cuidado
    também com palavras em maiúsculas no código e nos docs: a palavra "todos" escrita em
    maiúsculas casa com o padrão (aconteceu na primeira versão do ADR).
19. `web/index.html`, `web/app.js`, `web/js/core.js`, `web/style.css`, `web/vendor/maplibre-gl.js`
    + `.css` (cópia de `fgr/sig/web/vendor/`), `web/vendor/VERSOES.txt` (maplibre-gl 4.7.1,
    BSD-3, sha256 calculado com `sha256sum`). A página deste item mostra só: nome `plat`,
    "análise / beta privado", versão e git_sha lidos de `/api/versao` por `fetch`, e o JSON de
    `/saude` formatado. Nenhum botão inerte. `<meta name="robots" content="noindex, nofollow">`.
20. `tests/conftest.py` — fixtures: `cliente` (TestClient), `conexao_plat_app` (psycopg2 com
    `PLAT_DSN`), `medida(item)` que grava `tests/medidas/<item>.json` (formato do ADR 10),
    `base_url` do `.env`.
21. `tests/unit/test_versao.py` — `VERSAO` semver; `git_sha()` 7-40 hex.
22. `tests/unit/test_settings.py` — falha nomeando chave ausente; rebaixa DEBUG em producao.
23. `tests/api/test_saude.py` — 200 e campos do contrato; `tempo_ms` gravado como medida
    `latencia_saude_ms` (mediana de 20 chamadas); `/api/versao` 200.
24. `tests/api/test_banco.py` — conexão TCP como `plat_app` funciona (prova da linha no pg_hba);
    `SELECT current_user` = `plat_app`; `plat_app` não é dona de nenhuma tabela do schema; não
    tem BYPASSRLS.
25. `tests/api/test_migracoes.py` — `db/migrar.sh` duas vezes: segunda não insere linha; cópia
    editada em diretório temporário devolve código 3; toda tabela com coluna `tenant_id` tem
    `relrowsecurity = true` e pelo menos uma política.
26. `tests/api/test_rls.py` — como `plat_app`: sem contexto vê 0 linhas em `tenant`; com
    `plat.tenant_id = demo` vê só `demo`; com `demo2` só `demo2`; INSERT em `usuario` com
    `tenant_id` de outro inquilino falha (`WITH CHECK`).
27. `tests/api/test_cabecalhos.py` — HTTP real em `https://plat.iagrointel.com`: `X-Robots-Tag:
    noindex, nofollow` em `/`, `/saude`, `/api/versao`, `/static/app.js`; `Cache-Control` com
    `no-store` em `/static/app.js`; `X-Req-Id` presente. Marcado `lento`? Não: é rápido, mas
    exige rede; marcar `@pytest.mark.skipif` só se `PLAT_URL_PUBLICA` não resolver.
28. `tests/e2e/test_saude_pagina.py` — `lento` + `e2e`: abre `/`, espera a versão aparecer,
    0 erro de console (`page.on('console')` e `page.on('pageerror')`), captura
    `tests/e2e/capturas/L0-01-repo_inicio.png`; grava medida `primeira_pintura_ms`.
29. `docs/openapi.json` — gerado por `make openapi` e comitado.
30. `ARQUITETURA.md` — o cronista escreve; o backend deixa em `30_backend.md` a lista de
    portas, unidades, arquivos e comandos com saída literal (instalação do zero cronometrada,
    `systemctl status plat-api`, `curl -sI https://plat.iagrointel.com/saude`).

Ordem de execução recomendada: 1-9 e 12-14 (banco e núcleo) → `sudo bash db/migrar.sh` →
17 (install.sh) e rodar → 10-11 → 19 → 15-16 (já usados pelo install.sh) → 18 → 20-28 →
`make check` → 29. Nada de código com marcador de pendência: o que não couber, não entra.

## Resumo em 10 linhas (decisões)

1. Repositório com `app/ db/migracoes web/ deploy/ tests/{unit,api,e2e,medidas} docs/adr`, `VERSAO`, `install.sh`, `Makefile`, `.env.exemplo`.
2. FastAPI + uvicorn + psycopg2 síncrono com pool de reconexão copiado em substância do `fgr/sig` (só a preparação repete); 2 workers; `MemoryMax=1G` (pico medido do vizinho: 251 MB).
3. Schema `plat` de dono `postgres`, role `plat_app` sem BYPASSRLS e sem posse, `ALTER DEFAULT PRIVILEGES` para não repetir GRANT; linha `host iagro_sat plat_app 127.0.0.1/32 scram-sha-256` no pg_hba (hoje não existe; medido).
4. Migrações `NNN_*.sql` idempotentes e imutáveis, registradas em `plat.versao_migracao` com sha256; sha divergente = código 3.
5. Esquema base: `tenant`, `usuario` (perfis admin/editor/visualizador/campo + superadmin, 2FA, bloqueio), `sessao` (hash, com tenant_id), `token_servico` (hash, escopos, restrição, revogação), `log_acesso` (unifica auditoria de login e leitura por token); RLS `FOR ALL` com `USING` e `WITH CHECK` por `current_setting('plat.tenant_id')`.
6. `/saude`: 200 só com banco ok e 0 migrações pendentes, 503 caso contrário; `servicos.{martin,titiler,garage}` informativos (`ausente|ok|erro`, critério status < 500 porque o Garage responde 403); `/api/versao` sem banco.
7. nginx próprio copiado do `fgrsig`, com `alias` para `web/` e `no-store` nos módulos, `X-Robots-Tag` repetido em cada `location` (armadilha documentada do `add_header`); bloco, DNS e certificado já existem.
8. Front: módulos ES sem bundler, MapLibre 4.7.1 vendorizado com sha256 em `VERSOES.txt`. Medido: Vite custa 78 MB + 95 MB de cache, 392 MB de RSS por build, sem ganho visível; o layout ESM já é o que o Vite consome, logo ligar bundler depois custa zero código; trocar para framework custaria reescrever `web/js/` e fica adiado ao L5-01 com medição.
9. Testes na venv do repositório (pytest 9.1.1, playwright chromium 147 medido funcionando, ruff 0.16.6 instalado, 23 MB); `make check` = lint + varredura de marcador (mesma expressão do driver) + pytest + e2e; número em documento só via `tests/medidas/*.json`.
10. Pendências ao gerente: o `driver.sh` chama `python3 -m pytest` do sistema, que não existe (medido); e o `install.sh` deve realinhar a senha da role ao `.env` em toda execução.
