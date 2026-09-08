# T1 · 40_testes — testador · item L0-01-repo

## Objetivo

Medir de forma independente o que o handoff `30_backend.md` afirma sobre o item L0-01-repo e julgar
cada cláusula do portão de pronto com evidência literal. Não construí nada e não consertei nada.
Repositório `/home/dev/plataforma/enterprise` em `b22761e1c785` (árvore limpa na partida). Todos os
números estão em `tests/medidas/L0-01-repo.json` (assinado por mim; sobrescrevi o do backend).

## O que fiz

1. `git status` (limpo) e `git log`; `make check` inteiro cronometrado.
2. Instalação do zero: `systemctl stop plat-api`, `DROP SCHEMA plat CASCADE; DROP OWNED BY plat_app;
   DROP ROLE plat_app`, `install.sh` cronometrado, `make check`, `curl` HTTPS, `X-Robots-Tag` em 11
   rotas (inclui estático, 404 e docs da API).
3. Segunda execução seguida do `install.sh` (idempotência: migrações, pg_hba, serviço, certbot).
4. Caminho "máquina que nunca viu o repo", que o backend NÃO tinha testado: além do DROP, apaguei
   `.env`, `tests/credenciais.txt` e a linha `plat_app` do `pg_hba.conf` (cópias no scratchpad da
   sessão), reinstalei e rodei `make check` com a senha nova.
5. RLS como `plat_app` (DSN do `.env`): sem contexto, com contexto `demo` e `demo2`, INSERT/UPDATE/
   DELETE cruzados, posse de objetos, `rolbypassrls`, escrita em `versao_migracao`/`log_acesso`.
6. Medições: RSS do serviço, latência de `/saude` (20 chamadas, três modos), tempo de instalação,
   contagem de testes, varredura de placeholder com a expressão do `driver.sh`, travessia do `alias`
   estático, nomes de cliente (P7), captura do e2e lida a olho.

## Evidência (comando + saída literal)

### 1. Repositório e suíte na partida

```
$ git status
On branch master
nothing to commit, working tree clean
$ git log --oneline | head
b22761e Medidas do item L0-01-repo regeneradas sobre o commit 904a849
904a849 Fundação do repositório plat (item L0-01-repo): API, migrações, instalador, testes
a1d0c20 Esqueleto do repositório da plataforma (laço PLATAFORMA ENTERPRISE, turno 0)
$ /usr/bin/time -f "tempo_make_check_s=%e" make check
venv/bin/ruff check app tests
All checks passed!
! grep -rnI ... -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile
venv/bin/pytest -m "not lento"
57 passed, 1 deselected, 1 warning in 1.07s
venv/bin/pytest -m lento --base-url https://plat.iagrointel.com
1 passed, 57 deselected in 0.55s
tempo_make_check_s=2.72
rc=0
$ git status --short
 M tests/medidas/L0-01-repo.json        <- a suíte suja a árvore (ver Riscos 1)
$ venv/bin/pytest --collect-only -q
tests/api/test_banco.py: 5 · test_cabecalhos.py: 18 · test_migracoes.py: 5 · test_rls.py: 7 · test_saude.py: 5
tests/e2e/test_saude_pagina.py: 1
tests/unit/test_log.py: 2 · test_senha.py: 2 · test_settings.py: 10 · test_versao.py: 3
(58 coletados = 57 rápidos + 1 e2e; 43 funções `def test_`)
```

### 2. Instalação do zero (schema e role apagados)

```
$ sudo systemctl stop plat-api; systemctl is-active plat-api
inactive
$ sudo -u postgres psql -d iagro_sat -v ON_ERROR_STOP=1 -X -q -f - <<'SQL'
DROP SCHEMA IF EXISTS plat CASCADE; DROP OWNED BY plat_app; DROP ROLE IF EXISTS plat_app;
SQL
psql:<stdin>:1: NOTICE:  drop cascades to 17 other objects
$ sudo -u postgres psql -d iagro_sat -Atc "select count(*) from pg_namespace where nspname='plat'; select count(*) from pg_roles where rolname='plat_app';"
0
0
$ /usr/bin/time -f "tempo_install_zero_s=%e" sudo bash install.sh plat.iagrointel.com 8150
== c. migrações
aplicada   001_fundacao (67 ms)
aplicada   002_identidade (1414 ms)
migracoes: aplicadas 2 · reaplicadas 0 · iguais 0 · pendentes 0
== d. .env e senha da role
.env já existe (mantido)
senha de plat_app alinhada ao .env
== e. pg_hba
linha já existe em /etc/postgresql/16/main/pg_hba.conf
== h. systemd plat-api
/saude local respondeu 200 em 2 s
     Active: active (running) since Sat 2026-09-05 12:46:32 UTC; 1s ago
== i. nginx
bloco reescrito preservando 5 linhas do certbot
nginx: configuration file /etc/nginx/nginx.conf test is successful
== j. conferência pública
https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow
== instalado em 6 s: https://plat.iagrointel.com (serviço plat-api, porta 8150)
tempo_install_zero_s=6.24
rc=0
$ make check
57 passed, 1 deselected, 1 warning in 1.03s
1 passed, 57 deselected in 0.56s
tempo_make_check_s=2.69   rc=0
```

Ruído visto na saída que o backend não relatou: `NOTICE: extension "postgis" already exists`,
`NOTICE: schema "plat" already exists` (a 001 recria o schema que o migrar.sh acabou de criar para a
tabela de controle) e 5 `NOTICE: policy ... does not exist, skipping` (DROP POLICY IF EXISTS na 002).
São avisos idempotentes, não erros; o rc é 0.

### 3. /saude por HTTPS e X-Robots-Tag em toda location

```
$ curl -sSI https://plat.iagrointel.com/saude
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
Content-Length: 270
cache-control: no-store
x-req-id: 11909f226e6bd3b3
Cache-Control: no-store, must-revalidate
X-Robots-Tag: noindex, nofollow
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
$ curl -sS https://plat.iagrointel.com/saude | python3 -m json.tool
{ "versao": "0.1.0", "git_sha": "b22761e1c785", "ambiente": "producao", "banco": "ok",
  "migracoes_aplicadas": 2, "migracoes_pendentes": 0, "ultima_migracao": "002_identidade",
  "servicos": {"martin": "ausente", "titiler": "ausente", "garage": "ok"},
  "tempo_ms": 1.6, "em": "2026-09-05T12:46:52Z" }
$ git rev-parse --short=12 HEAD
b22761e1c785                       <- igual ao git_sha do /saude (risco 1 do backend conferido)
$ for u in ...; do curl -s -o /dev/null -w '%{http_code} ' $u; curl -sI $u | grep -i x-robots-tag; done
/                                200 X-Robots-Tag: noindex, nofollow
/saude                           200 X-Robots-Tag: noindex, nofollow
/api/versao                      200 X-Robots-Tag: noindex, nofollow
/static/app.js                   200 X-Robots-Tag: noindex, nofollow
/static/vendor/maplibre-gl.js    200 X-Robots-Tag: noindex, nofollow
/static/style.css                200 X-Robots-Tag: noindex, nofollow
/static/js/core.js               200 X-Robots-Tag: noindex, nofollow
/api/docs                        200 X-Robots-Tag: noindex, nofollow
/api/openapi.json                200 X-Robots-Tag: noindex, nofollow
/naoexiste                       404 X-Robots-Tag: noindex, nofollow
/static/naoexiste.js             404 X-Robots-Tag: noindex, nofollow
$ curl -sI http://plat.iagrointel.com/saude | head -1
HTTP/1.1 301 Moved Permanently  (Location: https://plat.iagrointel.com/saude)
$ curl -s --path-as-is -o /dev/null -w '%{http_code}' https://plat.iagrointel.com/static/../.env
404   (corpo = {"detail":"Not Found"} do FastAPI; /static/..%2F.env e /static/%2e%2e/.env também 404; /static/vendor/ = 403)
```
O bloco real em `/etc/nginx/sites-enabled/plat.iagrointel.com` tem `add_header X-Robots-Tag ... always`
no `server`, em `location /static/` e em `location /` (lido); as 5 linhas `# managed by Certbot` estão
no lugar; `listen 80` só redireciona.

### 4. Segunda execução seguida (idempotência)

```
$ sudo grep -c plat_app /etc/postgresql/16/main/pg_hba.conf      -> 1  (antes)
$ /usr/bin/time -f "tempo_install_2_s=%e" sudo bash install.sh plat.iagrointel.com 8150
== c. migrações
igual      001_fundacao
igual      002_identidade
migracoes: aplicadas 0 · reaplicadas 0 · iguais 2 · pendentes 0
== d. .env já existe (mantido) · senha de plat_app alinhada ao .env
== e. linha já existe em /etc/postgresql/16/main/pg_hba.conf
== g. admin de demo semeado · admin de demo2 semeado
== h. /saude local respondeu 200 em 2 s
== i. bloco reescrito preservando 5 linhas do certbot
== j. https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow
== instalado em 4 s
tempo_install_2_s=4.69
rc=0
$ sudo grep -c plat_app /etc/postgresql/16/main/pg_hba.conf      -> 1  (depois; linha 35)
$ sudo -u postgres psql -d iagro_sat -Atc "select count(*) from plat.versao_migracao"   -> 2 (antes e depois)
$ systemctl is-active plat-api; systemctl show plat-api -p NRestarts
active
NRestarts=0
$ sudo grep -c "managed by Certbot" /etc/nginx/sites-enabled/plat.iagrointel.com   -> 8 (5 no 443 + 3 no 80, sem duplicar)
```

### 5. Caminho "máquina que nunca viu o repo" (não coberto pelo backend)

```
$ sudo cp pg_hba.conf <scratchpad>; cp .env tests/credenciais.txt <scratchpad>
$ sudo sed -i -E '/^host\s+iagro_sat\s+plat_app\s/d' /etc/postgresql/16/main/pg_hba.conf; rm -f .env tests/credenciais.txt
$ sudo systemctl stop plat-api; DROP SCHEMA ...; DROP OWNED ...; DROP ROLE ...   -> schema 0, role 0
$ psql "postgresql://plat_app:<senha antiga>@127.0.0.1:5432/iagro_sat" -Atc "select 1"
FATAL:  no pg_hba.conf entry for host "127.0.0.1", user "plat_app", database "iagro_sat", SSL encryption
$ /usr/bin/time -f "tempo_install_nunca_viu_s=%e" sudo bash install.sh plat.iagrointel.com 8150
== c. aplicada 001_fundacao (49 ms) · aplicada 002_identidade (3547 ms)
== d. .env criado · senha de plat_app alinhada ao .env
== e. linha acrescentada em /etc/postgresql/16/main/pg_hba.conf
== g. tests/credenciais.txt criado · admin de demo semeado · admin de demo2 semeado
== h. /saude local respondeu 200 em 2 s
== j. https://plat.iagrointel.com/saude -> HTTP 200 · X-Robots-Tag: noindex, nofollow
== instalado em 9 s
tempo_install_nunca_viu_s=9.14
rc=0
$ sudo grep -n plat_app /etc/postgresql/16/main/pg_hba.conf   -> 35:host    iagro_sat       plat_app        127.0.0.1/32            scram-sha-256  (35 linhas no arquivo, como antes)
$ ls -la .env tests/credenciais.txt
-rw------- 1 dev dev 341 .env      -rw------- 1 dev dev 57 tests/credenciais.txt
senha da role ROTACIONADA (nova .env)
$ psql "postgresql://plat_app:<senha antiga>@..." -> FATAL:  password authentication failed for user "plat_app"
$ psql "$(grep ^PLAT_DSN .env | cut -d= -f2-)" -Atc "select current_user"  -> plat_app
$ make check
57 passed, 1 deselected · 1 passed, 57 deselected · tempo_make_check_s=2.68 · rc=0
```

### 6. RLS e privilégios como `plat_app`

```
$ sudo -u postgres psql -Atc "select rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolcanlogin from pg_roles where rolname='plat_app'"
plat_app|f|f|f|f|t
$ ... posse: schema plat=postgres; tabelas log_acesso sessao tenant token_servico usuario versao_migracao=postgres;
    4 sequências=postgres; 11 funções=postgres (9 SECURITY DEFINER; tenant_atual/usuario_atual não)
$ ... objetos de posse de plat_app no banco inteiro: pg_class 0 · pg_proc 0 · pg_namespace 0
$ ... tabelas de plat com coluna tenant_id (relrowsecurity, nº políticas):
log_acesso|t|1   sessao|t|1   token_servico|t|1   usuario|t|1      (+ tenant|t|1 por id)
$ ... políticas: p_tenant/p_usuario/p_sessao/p_token_servico = ALL TO plat_app USING (tenant_id = plat.tenant_atual()) WITH CHECK (idem);
    p_log_acesso = SELECT só
$ psql "$DSN" -Atc "select current_user; select count(*) from plat.tenant; ... usuario; sessao; token_servico; log_acesso"   (SEM contexto)
plat_app
0 0 0 0 0            (como postgres: tenant 2, usuario 2)
$ psql "$DSN" ... BEGIN; set_config('plat.tenant_id','1',true); SELECT slug FROM plat.tenant; SELECT tenant_id||':'||login FROM plat.usuario; ...
tenant_atual|1  tenant|demo  usuario|1:admin  sessao|0  token_servico|0  log_acesso|0
$ ... set_config('plat.tenant_id','2',true)
tenant|demo2  usuario|2|admin
$ psql "$DSN" -v ON_ERROR_STOP=1 ... set_config('plat.tenant_id','1'); INSERT INTO plat.usuario(tenant_id,...) VALUES (2,'intruso_teste',...,'admin')
psql:<stdin>:3: ERROR:  new row violates row-level security policy for table "usuario"
rc_insert_cruzado=3
$ ... contexto 1: INSERT tenant_id=1 -> insert_proprio_ok|10 ; UPDATE ... WHERE tenant_id=2 RETURNING -> 0 linhas ;
    DELETE ... WHERE tenant_id=2 RETURNING -> 0 linhas ; UPDATE plat.usuario SET tenant_id=2 WHERE login='proprio_teste'
psql:<stdin>:6: ERROR:  new row violates row-level security policy for table "usuario"     (tudo em ROLLBACK)
$ sudo -u postgres psql -Atc "select tenant_id, login, nome, ativo from plat.usuario order by 1"
1|admin|Administrador demo|t
2|admin|Administrador demo2|t
$ psql "$DSN" -Atc "insert into plat.versao_migracao(nome, sha256) values ('x','y')"   -> ERROR:  permission denied for table versao_migracao
$ psql "$DSN" -Atc "insert into plat.log_acesso(tenant_id) values (1)"                -> ERROR:  permission denied for table log_acesso
$ psql "$DSN" -Atc "set role postgres"                                                 -> ERROR:  permission denied to set role "postgres"
$ psql "$DSN" -Atc "select count(*) from information_schema.table_privileges where grantee='plat_app' and table_schema<>'plat'"   -> 0
```

### 7. Medições

```
$ systemctl status plat-api --no-pager | sed -n 1,8p
     Active: active (running) since Sat 2026-09-05 12:47:11 UTC
      Tasks: 8   Memory: 89.7M (high: 768.0M max: 1.0G peak: 90.3M)
$ systemctl show plat-api -p MemoryCurrent -p MemoryPeak -p NRestarts     (final, após o caminho nunca-viu)
MemoryCurrent=94416896  MemoryPeak=94937088  NRestarts=0
$ ps -o pid,rss,cmd nos 4 processos do cgroup: mestre 25.680 kB · resource_tracker 12.980 · worker 56.128 · worker 56.232 ; soma 151.020 kB
$ 20 × curl -s -o /dev/null -w '%{time_total} %{http_code}' https://plat.iagrointel.com/saude   (conexão nova a cada chamada)
n=20 codigos={'200'} mediana_ms=19.9 p95_ms=22.4 min=19.3 max=23.9
$ curl -s -w '%{time_total}\n' (20 URLs numa invocação, TLS reaproveitado)
n=20 mediana_ms=1.7 p95_ms=2.7 min=1.6 max=20.5
$ idem em http://127.0.0.1:8150/saude (sem nginx/TLS)
n=20 mediana_ms=1.4 p95_ms=1.9
$ grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E 'TODO|FIXME|XXX|lorem ipsum|em breve|coming soon|placeholder|mock[A-Z_(]|not implemented|NotImplemented' app db web install.sh Makefile | grep -v laco/ | wc -l
0                       (repositório inteiro com a mesma expressão: 0; laco/placeholders.txt: 0 linhas)
$ journalctl -u plat-api --no-pager -o cat | grep -ciE '"nivel": "(ERROR|WARNING)"|Traceback|error'
0
$ ls -la tests/e2e/capturas/   -> L0-01-repo_inicio.png 43.130 bytes (lido a olho: "plat · análise / beta privado", versão 0.1.0,
  git b22761e1c785, ambiente producao, painel "saúde ok" com o JSON de /saude; nenhum botão)
```

### 8. Documentos do portão e P7

```
$ wc -l README.md ARQUITETURA.md MANUAL.md CHANGELOG.md docs/adr/0001-fundacao.md
  15 README.md · 3 ARQUITETURA.md · 3 MANUAL.md · 2 CHANGELOG.md · 726 docs/adr/0001-fundacao.md
$ cat ARQUITETURA.md
# Arquitetura
(escrita pelo laço a partir do item L0-01)
$ cat MANUAL.md
# Manual do usuário
(uma seção por tela, com captura real, escrita pelo cronista a cada item entregue)
$ cat CHANGELOG.md
# Changelog
$ cat docs/PARIDADE.md      -> só o cabeçalho da tabela, 0 linhas
$ grep -rnE "fgr|cbre" app db web install.sh Makefile deploy
app/settings.py:92:    """.env da raiz, com o ambiente do processo por cima (o ambiente vence, como no fgr/sig)."""
app/db.py:2:fgr/sig/app/main.py: só a PREPARAÇÃO repete (até 9 vezes); a consulta do chamador roda uma única vez.
db/migracoes/002_identidade.sql:2:-- SECURITY DEFINER (ADR 0001 seção 6; corpos seguem fgr/sig/db/schema_v3.sql, adaptados a token_hash e a
$ grep -ciE "fgr|cbre" docs/adr/0001-fundacao.md   -> 34
$ grep -rniE "fgr|cbre|novaterra|certel|edp" web/   -> nada (UI limpa) ; plat.tenant = demo / demo2 apenas
```

## Julgamento cláusula a cláusula

| cláusula do portão | evidência | veredito |
|---|---|---|
| git com README/ARQUITETURA/MANUAL/CHANGELOG | os 4 arquivos existem e estão versionados; README 15 linhas com conteúdo; ARQUITETURA (3 linhas), MANUAL (3), CHANGELOG (2) são esboços sem conteúdo ("escrita pelo laço a partir do item L0-01") | **NÃO PASSA no momento do teste** — depende do cronista (60), que roda depois de mim; o gerente só pode dar PASSA depois de conferir os três arquivos preenchidos |
| `install.sh` cria schema+role+pg_hba (com linha em pg_hba.conf) | seções 2 e 5: com schema, role, `.env`, credenciais e linha do pg_hba apagados, o script imprimiu `.env criado`, `linha acrescentada em pg_hba.conf`, `tests/credenciais.txt criado`; role recriada, senha rotacionada, senha antiga rejeitada | PASSA |
| ... e sobe `plat-api` (:8150) sem erro em máquina que nunca viu o repo | rc=0 em 3 execuções; `/saude local respondeu 200 em 2 s`; `ss -ltnp` mostra 127.0.0.1:8150 com 3 PIDs; NRestarts=0; journal sem erro. Ressalva: "máquina que nunca viu" foi simulada nesta máquina (venv e certificado TLS já existiam; o `certbot` do passo i2 não foi exercitado) | PASSA (com a ressalva de venv e certificado pré-existentes) |
| `make check` roda pytest verde | 3 rodadas rc=0: ruff ok, 0 marcador, 57 passed + 1 e2e passed, 2,7 s cada | PASSA |
| URL interna HTTPS com noindex responde 200 em /saude com JSON de versão | seção 3: HEAD e GET 200, JSON com `versao`, `git_sha` = HEAD, `banco ok`, migrações 2/0; `X-Robots-Tag: noindex, nofollow` em 11/11 rotas testadas (server, /static/, /, 404) | PASSA |
| `docs/adr/0001-fundacao.md` escrito | 726 linhas, 41.937 bytes, estado "aceito" | PASSA |
| refutação literal (apagar schema e role, reinstalar, /saude e pytest completo, noindex) | seções 2-5: feita por mim três vezes, inclusive com `.env`/pg_hba/credenciais apagados | PASSA (o adversário 50 ainda deve repetir em contexto próprio) |

Portões congelados que pude conferir neste item:

| portão | evidência | veredito |
|---|---|---|
| P1 funciona no navegador | e2e playwright na URL real: 0 erro de console/página, 0 resposta ≥ 400, captura lida a olho | PASSA |
| P2 sem placeholder | 0 linhas com a expressão do driver em app/db/web/install.sh/Makefile e no repositório inteiro | PASSA |
| P3 suíte inteira verde | `make check` rc=0 × 3 | PASSA |
| P4 paridade declarada e testada | `docs/PARIDADE.md` só tem cabeçalho; papel `esri` não rodou no T1 (o plano não o previu: item de fundação, sem capacidade Esri correspondente) | NÃO APLICÁVEL a este item; o gerente registra a decisão |
| P5 reprodutível | install do zero e caminho nunca-viu rc=0; migrações idempotentes (2ª rodada = 0 novas); nada manual fora do script | PASSA |
| P6 multi-inquilino e segurança | RLS ativa nas 4 tabelas com `tenant_id` (+ tenant), 0 linhas sem contexto, cruzado A→B bloqueado em INSERT e em UPDATE de `tenant_id`, `rolbypassrls=f`, 0 objetos de posse de `plat_app`, `versao_migracao` e `log_acesso` sem escrita direta; "em toda rota" só vale para `/`, `/saude`, `/api/versao` (não há rota autenticada ainda: L0-02); token com escopo e log de acesso em tabela ainda não existem | PASSA no banco; rotas e token ficam para L0-02 |
| P7 dado aberto, sem nome de cliente, sem PII | UI e dado semeado limpos (demo/demo2). **Nome de cliente em código e docs entregues**: `app/settings.py:92`, `app/db.py:2`, `db/migracoes/002_identidade.sql:2` ("fgr/sig"), `docs/adr/0001-fundacao.md` 34 linhas com `fgr`/`cbre` | **NÃO PASSA** — reprodução: `grep -rnE "fgr\|cbre" app db docs` no repositório |
| P8 adversário independente | ainda não rodou | pendente (50) |
| P9 documentado | OpenAPI comitado e igual ao servido (2 caminhos); MANUAL/ARQUITETURA/CHANGELOG vazios | NÃO PASSA no momento do teste (cronista 60) |

## Riscos

1. **`make check` suja o repositório.** A fixture `medida()` (`tests/conftest.py:73-90`) reescreve
   `tests/medidas/L0-01-repo.json`, que é versionado, a cada rodada (4 chaves + `gerado_em` +
   `git_sha`). Reprodução: `git status --short` depois de `make check` → ` M tests/medidas/L0-01-repo.json`.
   O driver roda `check-rapido` a cada 30 min e vai deixar a árvore suja permanentemente; e as
   chaves do testador ficam ao lado de chaves que o teste sobrescreve. Cabe ao gerente decidir:
   medidas de teste em arquivo separado (`*.auto.json` ignorado) ou fixture que só grava com
   `PLAT_GRAVAR_MEDIDAS=1`.
2. **Contexto de inquilino é um GUC que a própria role define.** `plat.tenant_atual()` lê
   `current_setting('plat.tenant_id')`; `plat_app` pode executar `set_config` livremente (é o
   desenho: a aplicação define o contexto). Uma injeção de SQL em rota futura trocaria de inquilino
   sem passar pela RLS. Não é defeito deste item; é regra para o L0-02: todo SQL parametrizado, e o
   contexto definido só em `app/db.py`.
3. **"Máquina que nunca viu" foi simulada**: a venv já existia (o `pip install -r` rodou sobre ela) e
   o certificado Let's Encrypt também (o passo `i2. certbot` nunca foi exercitado por mim nem, pelo
   handoff 30, pelo backend numa instalação limpa). Uma instalação em outro host pode falhar nesse
   passo sem que nenhum teste de hoje acuse.
4. As latências foram medidas do próprio servidor (216.238.123.14 → nginx local); a mediana de 19,9 ms
   com conexão nova é quase toda aperto de mão TLS. Não representa um usuário remoto.
5. O tempo de DDL da 002 oscilou 1,4 s → 3,5 s entre rodadas (instância compartilhada); o tempo total
   de instalação (6,2 s / 4,7 s / 9,1 s) carrega essa variação e não é métrica estável.
6. `MemoryCurrent` (90 MB) e a soma de RSS dos processos (147 MB) divergem por páginas compartilhadas;
   qualquer documento deve citar o valor do cgroup e dizer que é o cgroup.

## Pendências

- P7 (gerente/backend): apagar ou neutralizar as referências a `fgr/sig` e `cbre` em `app/settings.py:92`,
  `app/db.py:2`, `db/migracoes/002_identidade.sql:2` e no ADR (34 linhas); "padrão da casa" ou
  "serviço já em produção nesta máquina" dizem a mesma coisa sem nomear cliente.
- Risco 1 (gerente): decidir onde a fixture grava, antes de o driver sujar a árvore.
- Cronista (60): ARQUITETURA/MANUAL/CHANGELOG são a única cláusula do portão próprio que falta.
- Adversário (50): repetir a refutação literal em contexto próprio; sugiro também apagar `.env`,
  `tests/credenciais.txt` e a linha do pg_hba, como fiz, e conferir os três "criado".
- Risco 1 do backend observado ao vivo: depois do meu commit das medidas (sem `install.sh`), `/saude`
  devolve `git_sha b22761e1c785` enquanto `git rev-parse HEAD` = `832b638aeba2`. Quem comitar sem
  reiniciar `plat-api` (`sudo systemctl restart plat-api` ou `install.sh`) deixa a URL um commit atrás.
- Cópias de segurança feitas por mim no scratchpad da sessão (`pg_hba.conf.bak`, `env.bak`,
  `credenciais.bak`) não são mais necessárias: o estado novo é válido e a senha antiga está morta.

## Para o próximo papel (gerente)

1. O item passa em todas as cláusulas técnicas do portão próprio (install do zero, pg_hba, :8150,
   `make check`, /saude HTTPS noindex, ADR) e na refutação literal, com números em
   `tests/medidas/L0-01-repo.json` (commit só desse arquivo).
2. Duas cláusulas ficam NÃO PASSA no momento do teste: os três documentos vazios (cláusula 1 do
   portão próprio; cronista ainda não rodou) e P7 (nome de cliente em 3 arquivos de código e no ADR).
   Só a segunda exige mexer em código; nenhuma exige mudar o limiar.
3. Depois do cronista e da correção de P7, o `make check` tem de ser rodado de novo e o adversário
   lançado; até lá o estado honesto do item é `parcial` com as duas cláusulas nomeadas.

---

# Rodada 2 do testador (sobre HEAD `8ffe950`, após `32_backend_correcao.md`)

## Objetivo

Reconferir, sem reinstalação destrutiva (o adversário estava fazendo a dele), o que o backend afirma ter
corrigido e as duas cláusulas que marquei NÃO PASSA na rodada 1 (documentos vazios; P7).

## O que fiz

`make check` inteiro; `git status` depois; `make medidas`; latência de `/saude` (20 chamadas, dois modos);
RSS; contagem de testes; grep de P7; leitura de `ARQUITETURA.md`, `MANUAL.md`, `CHANGELOG.md`, `README.md`
contra o HEAD; noindex + HSTS nas 11 rotas; Swagger local; `make vendor`; journal. JSON de medidas reassinado.

## Evidência (comando + saída literal)

```
$ git log --oneline | head -3
8ffe950 L0-01 correção (T1): dependências fixadas sem ~/.local, senha por stdin, HSTS, Swagger local, make medidas, PLAT_GIT_SHA
7092755 Documentação do turno 1: ARQUITETURA, MANUAL, CHANGELOG e README descrevem o que existe em 0.1.0
3b53c24 P7: remove nomes de cliente/parceiro do codigo e do ADR; fixture de medidas so grava com PLAT_GRAVAR_MEDIDAS=1
$ /usr/bin/time -f "tempo_make_check_s=%e" make check
All checks passed!
81 passed, 1 deselected, 1 warning in 1.45s
1 passed, 81 deselected in 0.60s
tempo_make_check_s=2.86
rc=0
$ git status --short | wc -l
0                                  <- a suíte não suja mais a árvore (fixture só grava com PLAT_GRAVAR_MEDIDAS=1)
$ /usr/bin/time -f "tempo_make_medidas_s=%e" make medidas
82 passed, 1 warning in 1.96s
tempo_make_medidas_s=2.39   rc=0
$ git status --short
 M tests/medidas/L0-01-repo.json    <- só sob make medidas; as 4 chaves da fixture + gerado_em/git_sha; minhas chaves sobreviveram
$ venv/bin/pytest --collect-only -q | grep ^tests/
api: banco 5 · cabecalhos 26 · docs 2 · migracoes 5 · rls 7 · saude 5 · e2e: saude_pagina 1
unit: dependencias 4 · instalador 5 · log 2 · senha 2 · settings 10 · vendor 2 · versao 6      -> total=82 (81 + 1 e2e)
$ grep -rniE 'fgr|cbre|novaterra|certel|certaja|edp[^a-z]|robson|jamel|sigcorp|cbresig|fgrsig' --exclude-dir=venv --exclude-dir=.git --exclude-dir=vendor ... . | wc -l
0
$ grep -rnI ... -E '<expressão do driver>' app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md | wc -l
0
$ 20 × curl -s -o /dev/null -w '%{time_total} %{http_code}' https://plat.iagrointel.com/saude   (conexão nova)
n=20 codigos={'200'} mediana_ms=19.8 p95_ms=21.0 min=19.0 max=21.0
$ curl -s -w '%{time_total}\n' (20 URLs numa invocação, TLS reaproveitado)
n=20 mediana_ms=1.9 p95_ms=2.8 min=1.5 max=20.8
$ systemctl show plat-api -p MainPID -p MemoryCurrent -p MemoryPeak -p NRestarts -p TasksCurrent -p ActiveEnterTimestamp
MainPID=2508968  MemoryCurrent=92827648  MemoryPeak=93818880  NRestarts=0  TasksCurrent=8  ActiveEnterTimestamp=Sat 2026-09-05 13:11:09 UTC
$ ps -o rss nos 4 processos do cgroup: 25.468 + 12.836 + 55.560 + 55.316 kB = 149.180 kB
$ curl -sI https://plat.iagrointel.com/saude | grep -iE '^(HTTP|strict|x-robots|x-req)'
HTTP/1.1 200 OK
x-req-id: b1604d173a080139
Strict-Transport-Security: max-age=31536000
X-Robots-Tag: noindex, nofollow
$ curl -sS https://plat.iagrointel.com/saude | jq -r '.git_sha,.banco,.migracoes_pendentes'; git rev-parse --short=12 HEAD
8ffe950516f5 ok 0
8ffe950516f5
$ for u in (11 rotas); do curl -sI ...; done                     código | X-Robots-Tag | HSTS
/ 200 · /saude 200 · /api/versao 200 · /static/app.js 200 · /static/vendor/maplibre-gl-4.7.1.js 200 · /static/style.css 200 ·
/static/js/core.js 200 · /api/docs 405 (HEAD; GET = 200) · /api/openapi.json 200 · /naoexiste 404 · /static/naoexiste.js 404
-> 11/11 com "noindex, nofollow" e 11/11 com "max-age=31536000"
$ curl -sI http://plat.iagrointel.com/saude | grep -iE '^(HTTP|strict)'   -> HTTP/1.1 301 Moved Permanently (sem HSTS, correto)
$ /docs 404 · /redoc 404 · URLs externas no HTML de /api/docs: 0
$ make vendor
maplibre-gl-4.7.1.js: OK · maplibre-gl-4.7.1.css: OK · swagger-ui-bundle-5.32.15.js: OK · swagger-ui-5.32.15.css: OK
$ journalctl -u plat-api -o cat | grep '"nivel": "ERROR"'   (3 linhas; última linha útil do traceback)
2026-09-05T12:53:47 | LINE 1: SELECT nome FROM plat.versao_migracao ORDER BY nome
2026-09-05T12:56:08 | LINE 1: SELECT nome FROM plat.versao_migracao ORDER BY nome
2026-09-05T13:11:00 | LINE 1: SELECT nome FROM plat.versao_migracao ORDER BY nome
$ sudo journalctl --since 13:09 --until 13:12 _COMM=sudo | grep install.sh
2026-09-05T13:11:00 ... dev : COMMAND=/usr/bin/bash install.sh plat.iagro...    <- reinstalação de outro papel no mesmo segundo
$ wc -l README.md ARQUITETURA.md MANUAL.md CHANGELOG.md
47 · 475 · 157 · 82
$ grep -nE 'commit pendente|árvore de trabalho|sem commit|3b53c24|57 testes|58 testes|57 rápidos|maplibre-gl\.(js|css)[^-]|ca61ea1|\(este\)' README.md ARQUITETURA.md MANUAL.md CHANGELOG.md | wc -l
26
  README.md:18  "57 testes rápidos"
  MANUAL.md:38 git_sha 3b53c24e4c12 · :123 "57 testes rápidos" · :131 "58 testes coletados, 57 rápidos" · :144 "Limites conhecidos (commit 3b53c24)" ·
    :154 "correção na árvore de trabalho, ainda sem commit"
  CHANGELOG.md:27 "57 testes rápidos" · :35 medidas "em ca61ea1" · :63-65 "Correções pós-refutação em curso (árvore de trabalho ... commit pendente)" ·
    :82 "(este)" na tabela de commits
  ARQUITETURA.md:8 "commit ca61ea1" · :80 e :275 "maplibre-gl.js" (arquivo agora é maplibre-gl-4.7.1.js) · :286 "Ainda sem Strict-Transport-Security" ·
    :297 git_sha 3b53c24e4c12 · :377 "58 testes coletados" · :433-437 "seção 12. Correções em curso (árvore de trabalho, commit pendente)" · :466-468
```

## Julgamento atualizado (rodada 2)

| cláusula | evidência (rodada 2) | veredito |
|---|---|---|
| git com README/ARQUITETURA/MANUAL/CHANGELOG | os 4 existem e têm conteúdo real (47/475/157/82 linhas): componentes e portas, schema, `install.sh` passo a passo, contrato de `/saude`, manual de acesso com a captura do e2e, changelog com medições e commits; toda medida citada aponta para o JSON. **Mas descrevem `3b53c24`**: 26 linhas dizem "árvore de trabalho, commit pendente" para o que já está em `8ffe950`, citam 57/58 testes (são 81/82), `maplibre-gl.js` (é `maplibre-gl-4.7.1.js`), "ainda sem HSTS" (há), `git_sha 3b53c24e4c12` nos exemplos | PASSA na existência e na substância; **NÃO PASSA em P9 ("atualizados no mesmo turno")** até o cronista reescrever sobre `8ffe950` — 26 linhas nomeadas acima, nenhuma exige mudar código |
| `install.sh` cria schema+role+pg_hba e sobe `plat-api` :8150 | não repetido nesta rodada (adversário reinstalando); serviço ativo desde 13:11:09 após o `install.sh` de outro papel, NRestarts=0, `git_sha` = HEAD | PASSA (rodada 1 + serviço vivo sobre o HEAD novo) |
| `make check` pytest verde | rc=0, 81 + 1, 2,86 s; árvore limpa depois | PASSA |
| HTTPS noindex 200 em /saude com JSON de versão | 200 HEAD e GET, `git_sha 8ffe950516f5`, noindex 11/11, HSTS 11/11 | PASSA |
| ADR 0001 escrito | alterado em T1 nas seções listadas pelo backend; 0 nome de cliente | PASSA |
| P2 sem placeholder | 0 no escopo ampliado (inclui `*.md`, `requirements.txt`, `pyproject.toml`) | PASSA |
| P3 suíte inteira verde | rc=0 | PASSA |
| P7 sem nome de cliente | grep = 0 no repositório | **PASSA** (era NÃO PASSA na rodada 1) |
| risco 1 da rodada 1 (`make check` suja a árvore) | `git status` = 0 depois de `make check`; `make medidas` grava sob `PLAT_GRAVAR_MEDIDAS=1` | fechado |
| P9 documentado | OpenAPI igual ao servido; docs defasados (acima) | NÃO PASSA até a passada do cronista |

## Riscos (rodada 2)

1. `ARQUITETURA.md` §12 e `CHANGELOG.md` "Correções em curso" afirmam que as correções ainda não estão comitadas.
   Quem ler o documento hoje conclui o contrário do que o `git log` mostra. É defasagem de texto, não de código.
2. Os 3 erros do journal são o `/saude` chamado enquanto outro papel apagava o schema com o serviço no ar; o
   contrato devolve 503 e o log de acesso não registra `/saude` em produção (só em DEBUG), por isso não há linha
   com 503. Se o gerente quiser zero ruído, a refutação destrutiva deve parar o serviço antes do DROP, como fiz.
3. `/api/docs` devolve 405 a HEAD (rota `@app.get`); só `/saude` e `/api/versao` prometem HEAD. Não é cláusula;
   fica registrado para que ninguém meça `curl -sI /api/docs` e conclua que caiu.
4. As medidas de instalação, RLS e pg_hba deste JSON continuam sendo as da rodada 1 (sobre `b22761e`), marcadas
   assim no campo `comando`; a rodada destrutiva sobre `8ffe950` é a do adversário.

## Pendências

- Cronista: reescrever as 26 linhas defasadas sobre `8ffe950` (lista com número de linha acima); depois disso
  a cláusula dos documentos e P9 passam sem nova medição de código.
- Gerente: com P7 fechado e a suíte limpa, o único NÃO PASSA do item é documental.

## Para o próximo papel (gerente)

Estado honesto do item após a rodada 2: todas as cláusulas técnicas PASSAM sobre `8ffe950` (instalação e RLS
provadas na rodada 1 e no roteiro do adversário; suíte 81 + 1 verde e limpa; noindex + HSTS em toda rota; P7 = 0);
resta a documentação, que existe e é substantiva, mas descreve o commit anterior. Commit do JSON: ver `git log -1`.
