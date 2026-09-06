# ADR 0001 — Fundação do repositório `plat` (item L0-01-repo)

Estado: aceito (arquiteto, turno T1, setembro de 2026). Toda decisão abaixo traz o motivo em uma
das três formas admitidas pelo laço: MEDIDO nesta máquina (comando e saída em
`laco/handoffs/T1/20_arquitetura.md`), LIDO em código que já roda em produção nesta máquina
(`SIG de teste interno`, serviço `SIG de teste interno`, só leitura) ou DOCUMENTO OFICIAL. Nenhuma decisão vale
por moda. Quando uma decisão custa caro para mudar, o custo está escrito.

Contexto fixo (lido em `laco/estado.json` e em `DOC.md` seção 17.2): codinome `plat`; schema
`plat` e role `plat_app` no banco `iagro_sat` (PostgreSQL 16.13 + PostGIS 3.6.3, medido com
`SELECT version()`); portas 8150 (api), 8151 (martin), 8152 (titiler), 8153 (worker); unidades
systemd `plat-*`; URL interna `https://plat.iagrointel.com` com `noindex`. Máquina: 12 vCPU,
23 GB de RAM com 3 GB disponíveis, disco `/` a 98 % com 13 GB livres (`df -h`, 05/09/2026).

---

## 1. Layout do repositório

```
/home/dev/plataforma/enterprise/
  VERSAO                 uma linha, semver (0.1.0); lida por /api/versao e pelo Makefile
  README.md              o que EXISTE (nunca o que falta)
  ARQUITETURA.md         componentes, portas, esquema; aponta para docs/adr/
  MANUAL.md              uma seção por tela, captura real
  CHANGELOG.md           por turno
  install.sh             instalação idempotente (root); seção 4
  Makefile               alvos: check, check-rapido, migrar, lint, e2e, medidas, openapi, vendor (alterado em T1: `vendor` confere sha256 de web/vendor; `medidas` implementado)
  pyproject.toml         configuração de ruff e pytest (marcadores, testpaths)
  requirements.txt       toda dependência da aplicação e da suíte fixada com == (seção 2.1, alterada em T1)
  .env.exemplo           todas as chaves de configuração, sem segredo (seção 8)
  .env                   segredo real, modo 600, fora do git
  app/                   API FastAPI (pacote Python `app`)
    __init__.py
    main.py              cria a aplicação, middleware, monta rotas
    settings.py          lê e valida o .env; falha na partida se faltar chave obrigatória
    db.py                pool psycopg2 com reconexão (seção 3.2) e contexto por inquilino
    log.py               logging JSON por linha (seção 9)
    versao.py            VERSAO + git_sha (seção 7)
    saude.py             rotas /saude e /api/versao (seção 7)
  db/
    migrar.sh            aplicador de migrações (seção 5)
    migracoes/NNN_nome.sql   idempotentes; imutáveis depois de aplicadas
  web/                   front servido pelo nginx direto do disco (seção 4.3 e 6)
    index.html
    app.js               entrada, módulo ES
    js/*.js              módulos ES, importação relativa, sem versão na URL
    style.css
    vendor/              bibliotecas de terceiros, uma cópia por versão, com VERSOES.txt (nome, versão, sha256, licença)
  deploy/
    plat-api.service     modelo da unidade systemd; install.sh substitui APP_DIR/APP_USER/PORTA
    nginx.conf           modelo do server block; install.sh substitui DOMINIO/APP_DIR/PORTA
  tests/
    conftest.py          fixtures: cliente HTTP da API, conexão como plat_app, gravador de medidas
    unit/                sem rede e sem banco
    api/                 contra a API local (TestClient ou :8150) e contra o banco como plat_app
    e2e/                 playwright chromium contra https://plat.iagrointel.com; capturas em e2e/capturas/
    medidas/<item>.json  números medidos pelos testes; único lugar de onde documento cita número
  docs/
    adr/NNNN-*.md        decisões
    PARIDADE.md          tabela viva feito/parcial/fora contra o ArcGIS Enterprise
    openapi.json         gerado por `make openapi` a partir da aplicação; comitado
```

Motivo, por parte:

- `app/` e `web/` separados, `web/` servido pelo nginx direto do disco. LIDO em `SIG de teste interno`: o
  `SIG de teste interno` serve `web/` pelo `StaticFiles` do FastAPI por trás do nginx; funciona, mas cada
  arquivo estático passa por um worker Python. Aqui o nginx faz `alias` para `web/` (seção 4.3),
  e a API só responde `/api/`, `/saude` e, no futuro, `/svc/`. Custo de mudar depois: zero
  (os dois caminhos coexistem; a decisão está em uma `location` do nginx).
- `db/migracoes/NNN_*.sql` em vez de `schema.sql` + `schema_v2.sql` + `schema_v3.sql`. LIDO em
  `SIG de teste interno/db/`: três arquivos aplicados sempre na mesma ordem pelo `install.sh`, sem registro do
  que já foi aplicado nem do conteúdo aplicado. A tabela `plat.versao_migracao` (seção 5) resolve
  os dois buracos: sabe-se o que está aplicado e detecta-se arquivo editado depois de aplicado.
- `deploy/` com modelos em vez de heredoc dentro do `install.sh`. LIDO em `install.sh do SIG de teste interno`:
  a unidade e o nginx vivem dentro de um heredoc de 60 linhas com `\$` escapado; revisar e
  testar (`nginx -t`) é mais difícil. Modelo em arquivo é lido por qualquer um e pode ser
  comparado com `diff` contra o que está em `/etc`.
- `tests/{unit,api,e2e,medidas}`: exigência do laço (SKILL, papel testador) e do portão P1/P3.
- `docs/openapi.json` comitado: o adversário do item L0-02 precisa varrer "todas as rotas do
  OpenAPI" sem subir a aplicação; um arquivo gerado e comitado permite isso e mostra no `git diff`
  toda rota que nasce ou muda.

---

## 2. Pilha

| camada | escolha | motivo (forma admitida) |
|---|---|---|
| API | FastAPI 0.138.0 + uvicorn 0.27.1 (já na venv, `pip list`) | LIDO: `SIG de teste interno` e `segundo SIG de teste interno` rodam a mesma pilha em produção nesta máquina; MEDIDO: `SIG de teste interno` com 2 workers ocupa 167 MB (`MemoryCurrent`) e pico de 251 MB (`MemoryPeak`), 0 reinícios |
| banco | psycopg2 2.9.9 (venv e sistema, mesma versão) com `ThreadedConnectionPool` | LIDO: `main.py do SIG de teste interno` linhas 36-68, pool com reconexão que já sobreviveu a 3 OOM do Postgres (CLAUDE.md, seção o SIG de teste interno); psycopg2 é síncrono, e o FastAPI roda rota `def` em threadpool, então 2 workers × 8 conexões bastam para este item |
| esquema | `plat` em `iagro_sat`, role `plat_app` LOGIN sem BYPASSRLS e sem ser dona das tabelas | LIDO: `esquema do SIG de teste interno` final: "sem BYPASSRLS, nao e dono" é o que faz a RLS valer (doc PostgreSQL: dono da tabela e superusuário ignoram RLS salvo FORCE) |
| tiles vetoriais | Martin em :8151 (item L2-01) | DOC.md 17.2: em produção no observatório; aqui só reserva de porta e campo em /saude |
| tiles raster | TiTiler + pgstac em :8152 (item L1-01/L1-02) | DOC.md 17.2, medido 36-56 ms/tile em `plataforma/pipeline`; aqui só reserva de porta e campo em /saude |
| objetos | Garage, já ativo em :3900 (`plataforma-garage`, MEDIDO: `systemctl is-active` = active; `GET /` = HTTP 403, esperado sem assinatura S3) | DOC.md 17.2 |
| front | MapLibre GL JS 4.7.1 em `web/vendor/` (cópia do arquivo que roda em `SIG de teste interno`, 803.086 bytes) + módulos ES sem bundler | seção 6, decisão por medição |
| fila | Postgres como fila (item L0-05) em :8153 | DOC.md 17.2 (Procrastinate ou própria); fora deste item |

### 2.1 Versões e segurança de dependência

Versões fixas em `requirements.txt` gerado com `pip freeze` filtrado (só o que o `app/` importa).
A venv foi criada com `--system-site-packages`; isso é aceito para não duplicar GDAL, rasterio e
psycopg2 (já no sistema, disco a 98 %). Consequência escrita: `pip list` da venv mostra o que é do
sistema; `requirements.txt` fixa só o que instalamos por cima (pytest, pytest-playwright, ruff,
python-dotenv e o que vier). O item L7-03 põe o varredor de CVE no `make check`.

**Alterado em T1: motivo** — o adversário mostrou (`refutacao.json`, ataque 6b) que `fastapi`,
`starlette`, `pydantic` e `python-dotenv` vinham de `/home/dev/.local` (pip `--user` de quem
instalou), não do sistema nem do `requirements.txt`; com `PYTHONNOUSERSITE=1` a aplicação não
importava. A regra passa a ser:

1. "Do sistema" só significa **pacote dpkg**: `python3-uvicorn` (0.27.1) e `python3-psycopg2`
   (2.9.9), conferidos por nome no passo f do `install.sh` (`dpkg -s`), que aborta nomeando o pacote
   que falta. Tudo o mais que `app/` ou `tests/` importa está fixado com `==` em `requirements.txt`
   (fastapi 0.138.0, starlette 1.3.1, pydantic 2.13.4, python-dotenv 1.2.2, httpx 0.28.1 e as
   transitivas). O teste `tests/unit/test_dependencias.py` reprova linha sem `==`.
2. **`PYTHONNOUSERSITE=1` em todo Python da aplicação**: `Environment=` na unidade systemd,
   `export` no `Makefile` (a suíte prova o mesmo ambiente do serviço) e `env` explícito em cada
   `sudo -u` do `install.sh` (o `sudo` zera o ambiente). O site do usuário nunca entra no caminho.
3. Prova executável, além do teste: o passo f do `install.sh` faz `python -c "import app.main"`
   com `PYTHONNOUSERSITE=1` e exige que `fastapi.__file__` esteja dentro de `venv/`.

---

## 3. Banco: conexão, pool e contexto por inquilino

### 3.1 Role, pg_hba e permissões

```sql
-- 001_fundacao.sql (trecho normativo; idempotente)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plat_app') THEN
    CREATE ROLE plat_app LOGIN;             -- senha: install.sh, ALTER ROLE, nunca no SQL do repo
  END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS plat;           -- dono: postgres (quem aplica as migrações)
GRANT USAGE ON SCHEMA plat TO plat_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA plat TO plat_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA plat TO plat_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA plat TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT USAGE, SELECT ON SEQUENCES TO plat_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA plat GRANT EXECUTE ON FUNCTIONS TO plat_app;
```

Motivo do `ALTER DEFAULT PRIVILEGES`: LIDO em `SIG de teste interno`: cada `schema_vN.sql` repete o bloco de
`GRANT ... ON ALL TABLES` no fim porque tabela criada depois do GRANT nasce sem permissão. Com
privilégio padrão declarado uma vez, toda migração futura cria tabela já acessível à role. Doc
PostgreSQL: `ALTER DEFAULT PRIVILEGES` aplica-se a objetos criados depois, pelo papel indicado,
no schema indicado.

Linha obrigatória em `/etc/postgresql/16/main/pg_hba.conf`, inserida pelo `install.sh` e
seguida de `SELECT pg_reload_conf()`:

```
host    iagro_sat       plat_app        127.0.0.1/32            scram-sha-256
```

Motivo: regra da casa (CLAUDE.md e SKILL): role nova sem linha no pg_hba sobe e quebra na primeira
consulta. MEDIDO em 05/09/2026: `grep -n` no pg_hba mostra `SIG de teste interno_app` (linha 24), `segundo SIGsig_app`
(25) e `plataforma_com_app` (30) com exatamente esse formato; `plat_app` ainda não existe
(`SELECT rolname FROM pg_roles WHERE rolname LIKE 'plat%'` devolveu só `plataforma_com_app`).
O `install.sh` faz `grep -q "plat_app" pg_hba.conf || append`, e o teste `tests/api/test_banco.py`
abre conexão com o `PLAT_DSN` (TCP 127.0.0.1, não socket) para provar que a linha vale.

### 3.2 Pool com reconexão (armadilha da casa)

Contrato de `app/db.py`, copiado em substância de `main.py do SIG de teste interno` (linhas 36-68) e
generalizado:

```python
POOL = psycopg2.pool.ThreadedConnectionPool(1, 8, settings.PLAT_DSN)

@contextmanager
def db(ctx: Contexto | None = None):
    """ctx = (tenant_id, usuario_id, login) da sessão. Só a PREPARAÇÃO repete (até 9 vezes):
    pegar conexão, testar `con.closed`, SET search_path, set_config do inquilino.
    A consulta do chamador roda uma única vez. Conexão que falhou na preparação é
    devolvida ao pool com close=True (descartada), nunca reaproveitada."""
```

Regras que valem para todo código futuro:

1. Nunca `POOL.getconn()` fora de `db()`.
2. Nunca reexecutar a consulta do chamador em caso de `OperationalError`: quem repete é a
   preparação, porque a consulta pode ter efeito (INSERT) e a repetição cega duplica.
3. A preparação executa, na ordem: `SET search_path = plat, public`;
   `SELECT set_config('plat.tenant_id', %s, true), set_config('plat.usuario_id', %s, true),
   set_config('plat.login', %s, true)` quando há contexto. `true` = `SET LOCAL`, morre no fim da
   transação; conexão devolvida ao pool nunca carrega inquilino da requisição anterior.
4. `con.autocommit = False`; commit no fim do bloco, rollback em exceção.
5. Tamanho do pool: 8 por worker, 2 workers = 16 conexões. MEDIDO: `max_connections` = 100 e
   `pg_stat_activity` = 12 sessões em uso em 05/09/2026. Item L7-02 (carga) remede.

### 3.3 RLS: o contrato que o item L0-02 implementa em cima

```sql
CREATE OR REPLACE FUNCTION plat.tenant_atual()  RETURNS int LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('plat.tenant_id', true), '')::int $$;
CREATE OR REPLACE FUNCTION plat.usuario_atual() RETURNS int LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('plat.usuario_id', true), '')::int $$;
```

- Toda tabela com `tenant_id` tem `ENABLE ROW LEVEL SECURITY` e uma política `p_<tabela>`
  `FOR ALL TO plat_app USING (tenant_id = plat.tenant_atual()) WITH CHECK (tenant_id = plat.tenant_atual())`.
  `WITH CHECK` explícito: LIDO em `SIG de teste interno`: as políticas só têm `USING`; a doc PostgreSQL diz que
  sem `WITH CHECK` o `USING` vale para escrita também, mas explícito evita que alguém "corrija"
  para `FOR SELECT` e abra a escrita.
- Sem contexto (`plat.tenant_atual()` = NULL) a política devolve NULL = falso: nenhuma linha.
  Isso é o comportamento desejado e é testado (`tests/api/test_rls.py`; alterado em T1: o nome
  citado aqui era anterior ao arquivo, vale o nome que está no teste).
- Autenticação roda ANTES de existir inquilino na sessão, por funções `SECURITY DEFINER` com
  `SET search_path = plat, public` (padrão do `SIG de teste interno`, funções `auth_*`). São as únicas funções
  que enxergam além do inquilino, e cada uma devolve só o necessário.
- Migração roda como `postgres` (dona, ignora RLS): é assim que se semeia o primeiro inquilino.
  Nenhum teste de RLS pode conectar como `postgres`; o fixture `conexao_plat_app` do `conftest.py`
  usa o `PLAT_DSN`.

---

## 4. Serviço, nginx e URL interna

### 4.1 Unidade systemd `plat-api` (modelo em `deploy/plat-api.service`)

Copiada de `systemctl cat SIG de teste interno` (LIDO) com três acréscimos, cada um com motivo:

```ini
[Unit]
Description=plat — API da plataforma SIG (FastAPI :8150). Interno. Análise / beta privado.
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=/home/dev/plataforma/enterprise
ExecStart=/home/dev/plataforma/enterprise/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8150 --workers 2 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=3
MemoryHigh=768M
MemoryMax=1G
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- `--no-access-log`: o middleware da seção 9 escreve a linha de acesso em JSON; o log de acesso
  do uvicorn duplicaria em texto livre.
- `MemoryHigh=768M` / `MemoryMax=1G`: MEDIDO: `SIG de teste interno` (mesma pilha, 2 workers) pico 251 MB.
  1 GB é 4× o pico medido e protege uma máquina com 3 GB disponíveis; o OOM de 30/08 derrubou o
  Postgres por falta de limite em processos vizinhos (CLAUDE.md).
- `Wants=postgresql.service` além de `After`: sem `Wants`, `After` só ordena, não puxa o Postgres.
- `--workers 2`: igual ao `SIG de teste interno`; o item L7-02 mede e ajusta.

`plat-martin`, `plat-titiler`, `plat-worker` seguem o mesmo modelo quando os itens L2-01, L1-01 e
L0-05 os criarem; este item não os cria (plano do turno: "nenhum serviço além de /saude").

### 4.2 nginx (modelo em `deploy/nginx.conf`)

Estado MEDIDO em 05/09/2026: `/etc/nginx/sites-enabled/plat.iagrointel.com` já existe (bloco
inicial do gerente: `location / { return 503; }`), o certificado
`/etc/letsencrypt/live/plat.iagrointel.com/` existe, o DNS resolve para `216.238.123.14` e
`https://plat.iagrointel.com/saude` responde HTTP 503 (esperado: sem API ainda). O `install.sh`
reescreve o bloco inteiro a partir do modelo, preserva as linhas do certbot e roda `nginx -t`
antes de `systemctl reload nginx`; se o certificado não existir (máquina nova), chama
`certbot --nginx -d DOMINIO --non-interactive --agree-tos --redirect` como o `install.sh do SIG de teste interno`.

Modelo (copiado de `/etc/nginx/sites-enabled/SIG de teste internosig.iagrointel.com`, LIDO, com as diferenças
marcadas):

```nginx
server {
    server_name DOMINIO;
    client_max_body_size 200m;                       # SIG de teste interno usa 200m; upload de camada vem em L0-04
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # DIFERENÇA 1: estático direto do disco, não pelo uvicorn.
    # no-store nos módulos ES: o navegador nunca mistura versão velha e nova (regra da casa:
    # nunca ?v= em import de módulo; duas URLs do mesmo módulo = duas instâncias = app morre).
    location /static/ {
        alias APP_DIR/web/;
        add_header Cache-Control "no-store, no-cache, must-revalidate, max-age=0" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        add_header X-Content-Type-Options "nosniff" always;
    }
    location / {
        proxy_pass http://127.0.0.1:PORTA;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        # Cache-Control NÃO sai daqui (alterado em T2): quem declara é a aplicação
        add_header X-Robots-Tag "noindex, nofollow" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
    }
    # linhas do certbot (listen 443 ssl, ssl_certificate...) preservadas pelo install.sh
}
```

Armadilha documentada do nginx (doc oficial de `add_header`): um `add_header` dentro de
`location` cancela todos os `add_header` herdados do `server`. Por isso `X-Robots-Tag` é repetido
em cada `location`, como o `SIG de teste interno` faz. O teste `tests/api/test_cabecalhos.py` confere
`X-Robots-Tag: noindex, nofollow` em `/`, `/saude`, `/api/versao` e `/static/app.js`, e
`Cache-Control: no-store` em `/static/app.js`.

**Alterado em T2: `Cache-Control` tem uma origem só — a aplicação.** O testador do L0-05 mediu o cabeçalho
duplicado na resposta SSE pela URL pública (`no-store, no-store, must-revalidate`). A causa é a mesma armadilha do
`add_header`: ele **acrescenta**, nunca substitui, então toda rota em que a aplicação já declarava o cabeçalho
saía com dois (MEDIDO em `/saude` e `/tarefas`), e uma rota que precisa de cache — a miniatura do catálogo declara
`private, max-age=300` — sairia contradita por um `no-store` que o serviço não teria como remover. Decisão: nas
`location` proxiadas o `Cache-Control` sai do nginx; o piso `no-store, must-revalidate` passa a ser posto pelo
middleware de `app/auth/middleware.py` em toda resposta que não declare o seu (`setdefault`), e a rota que quiser
outro valor declara na própria rota. Em `/static/` o nginx continua sendo a origem, porque ali o corpo é dele.
Conferido por `tests/api/test_cabecalhos.py` (um único `Cache-Control` em 6 rotas da aplicação e 2 estáticas).

**Alterado em T1: HSTS.** O adversário apontou a ausência de `Strict-Transport-Security`. O modelo
`deploy/nginx.conf` traz `add_header Strict-Transport-Security "max-age=31536000" always;` no
`server` e em cada `location` (mesma armadilha do `add_header`). O cabeçalho só vale no bloco 443:
quando ainda não há certificado, o `install.sh` escreve o bloco em `:80` **removendo** essas linhas
(`grep -v`), chama o certbot e reescreve o bloco de novo com o certificado (passo i3). A conferência
pública do passo j exige `max-age=31536000` em `/saude`; `test_cabecalhos.py` confere o cabeçalho em
toda rota HTTPS e a ausência dele na resposta 301 do bloco `:80`. Sem `includeSubDomains` e sem
`preload`: o domínio é interno e outros subdomínios da casa não são deste produto. Também em T1: o
`install.sh` guarda o bloco anterior e o restaura se `nginx -t` reprovar (risco 2 da refutação).

### 4.3 Por que nginx `alias` e não `StaticFiles`

LIDO em `main.py do SIG de teste interno` linha 421: `app.mount('/static', StaticFiles(directory=web))`. Cada
pedido de módulo passa pelo worker Python. Com `alias`, o nginx serve do disco e os workers
ficam para a API. Custo de mudar: uma `location`. Consequência para os testes: os testes `api/`
que rodam com `TestClient` não enxergam `/static/`; quem testa estático é `test_cabecalhos.py`
(HTTP real contra :8150 via nginx) e o e2e.

---

## 5. Migrações e `plat.versao_migracao`

```sql
CREATE TABLE IF NOT EXISTS plat.versao_migracao (
  nome         text PRIMARY KEY,                 -- '001_fundacao'
  sha256       text NOT NULL,                    -- do arquivo, no momento em que foi aplicado
  aplicada_em  timestamptz NOT NULL DEFAULT now(),
  duracao_ms   int NOT NULL,
  aplicada_por text NOT NULL DEFAULT current_user
);
```

Aplicador `db/migrar.sh` (bash; roda como root via `sudo -u postgres psql`, nunca como `plat_app`):

1. Lista `db/migracoes/[0-9][0-9][0-9]_*.sql` em ordem lexicográfica.
2. Para cada arquivo calcula `sha256sum`.
   - Nome ausente na tabela: aplica com `psql -v ON_ERROR_STOP=1 -1 -f arquivo` (uma transação
     por arquivo) e, na MESMA transação, insere a linha em `versao_migracao`. Como fazer isso em
     um só `psql -1`: o aplicador concatena `arquivo.sql` + `INSERT INTO plat.versao_migracao ...`
     e manda por stdin (regra da casa: SQL por stdin, `ON_ERROR_STOP=1`).
   - Nome presente com o mesmo sha: pula (idempotência do aplicador).
   - Nome presente com sha diferente: **para com código 3** e imprime o nome. Arquivo aplicado é
     imutável; correção vem em arquivo novo. Exceção única: a linha `-- reaplicavel` na primeira
     linha do arquivo declara que ele pode ser reaplicado (só para arquivos que contêm apenas
     `CREATE OR REPLACE FUNCTION`/`VIEW`); o sha é atualizado na tabela.
3. Cada arquivo é idempotente por construção (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT
   EXISTS`, `DROP POLICY IF EXISTS` + `CREATE POLICY`, `CREATE OR REPLACE FUNCTION`), para que
   o adversário possa apagar o schema e rodar de novo (refutação literal do item).
4. A primeira migração não pode depender de `versao_migracao` já existir: `001_fundacao.sql`
   cria a tabela; o aplicador cria a tabela (mesmo DDL) antes de ler, se não existir.

`/saude` compara os arquivos em disco com a tabela (seção 7): pendência > 0 = banco
`desatualizado` = HTTP 503. O teste `tests/api/test_migracoes.py` aplica duas vezes seguidas e
exige saída idêntica e 0 linhas novas na segunda; e edita uma cópia em diretório temporário
para provar o código de saída 3.

Migrações deste item, na ordem:

```
001_fundacao.sql   schema, role, grants, default privileges, versao_migracao, tenant_atual(), usuario_atual()
002_identidade.sql tenant, usuario, sessao, token_servico, log_acesso, RLS, funções auth_* (seção 6)
```

---

## 6. Esquema base do `plat` (contrato para L0-02)

Origem: `esquema do SIG de teste interno` + `schema_v2.sql` (api_token) + `schema_v3.sql` (tenant.config,
usuario.totp/bloqueio/superadmin, sessao.ip/agente, login_audit), LIDOS e generalizados. O que
mudou em relação ao modelo e por quê está depois do DDL.

```sql
CREATE TABLE IF NOT EXISTS plat.tenant (
  id           serial PRIMARY KEY,
  slug         text UNIQUE NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'),
  nome         text NOT NULL,
  ativo        boolean NOT NULL DEFAULT true,
  config       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- centro [lon,lat], zoom, basemap, srid_padrao, cor, logo
  cota_bytes   bigint NOT NULL DEFAULT 21474836480,  -- 20 GiB; item L0-04 aplica
  criado_em    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plat.usuario (
  id                 serial PRIMARY KEY,
  tenant_id          int NOT NULL REFERENCES plat.tenant(id),
  login              text NOT NULL CHECK (login = lower(login)),
  nome               text NOT NULL,
  email              text,                          -- só corporativo; nunca exibido fora do inquilino
  senha_hash         text NOT NULL,                 -- 'pbkdf2_sha256$600000$<salt>$<hex>'
  perfil             text NOT NULL CHECK (perfil IN ('admin','editor','visualizador','campo')),
  superadmin         boolean NOT NULL DEFAULT false, -- opera a plataforma: cria inquilinos
  ativo              boolean NOT NULL DEFAULT true,
  totp_secret        text,                          -- base32; NULL = 2FA não configurado
  totp_ativo         boolean NOT NULL DEFAULT false,
  senha_alterada_em  timestamptz,
  falhas_login       int NOT NULL DEFAULT 0,
  bloqueado_ate      timestamptz,
  ultimo_login       timestamptz,
  criado_em          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, login)
);

CREATE TABLE IF NOT EXISTS plat.sessao (
  token_hash   text PRIMARY KEY,                    -- sha256 do token do cookie
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  expira_em    timestamptz NOT NULL,
  ultimo_uso   timestamptz,
  ip           text,
  agente       text                                  -- left(user-agent, 200)
);

CREATE TABLE IF NOT EXISTS plat.token_servico (
  id           serial PRIMARY KEY,
  tenant_id    int NOT NULL REFERENCES plat.tenant(id),
  usuario_id   int NOT NULL REFERENCES plat.usuario(id) ON DELETE CASCADE,  -- quem criou
  nome         text NOT NULL,
  token_hash   text NOT NULL UNIQUE,                -- sha256 do token; o token só aparece uma vez, na criação
  prefixo      text NOT NULL,                       -- 8 primeiros caracteres, para o usuário reconhecer na lista
  escopos      text[] NOT NULL DEFAULT '{}',        -- L0-02 define o vocabulário; vazio = nada
  restricao    jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"referer": [...], "ip": [...]}; L1-02 aplica
  expira_em    timestamptz,                         -- NULL = não expira
  revogado_em  timestamptz,                         -- NULL = válido
  criado_em    timestamptz NOT NULL DEFAULT now(),
  ultimo_uso   timestamptz,
  ultimo_ip    text
);

CREATE TABLE IF NOT EXISTS plat.log_acesso (
  id           bigserial PRIMARY KEY,
  em           timestamptz NOT NULL DEFAULT now(),
  tenant_id    int,                                 -- NULL antes de autenticar (login falho)
  usuario_id   int,
  token_id     int,
  ip           text,
  metodo       text NOT NULL,
  rota         text NOT NULL,                       -- caminho + query, left(..., 500)
  status       int NOT NULL,
  bytes        bigint NOT NULL DEFAULT 0,
  tempo_ms     int NOT NULL,
  agente       text,
  resultado    text                                 -- login: ok|senha|bloqueado|totp|inexistente; demais: NULL
);
CREATE INDEX IF NOT EXISTS ix_log_acesso_tenant_em ON plat.log_acesso (tenant_id, em DESC);
CREATE INDEX IF NOT EXISTS ix_log_acesso_token_em  ON plat.log_acesso (token_id, em DESC) WHERE token_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_sessao_usuario       ON plat.sessao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_token_tenant         ON plat.token_servico (tenant_id);
```

RLS (todas com `ENABLE ROW LEVEL SECURITY`, políticas `FOR ALL TO plat_app`):

| tabela | USING / WITH CHECK |
|---|---|
| tenant | `id = plat.tenant_atual()` |
| usuario | `tenant_id = plat.tenant_atual()` |
| sessao | `tenant_id = plat.tenant_atual()` |
| token_servico | `tenant_id = plat.tenant_atual()` |
| log_acesso | `tenant_id = plat.tenant_atual()` (leitura pelo admin do inquilino); escrita só pela função `plat.log_registrar(...)` SECURITY DEFINER |
| versao_migracao | sem RLS (não tem tenant_id); `plat_app` só lê |

Funções `SECURITY DEFINER` (`SET search_path = plat, public`), assinaturas que o L0-02 implementa
e a API chama; os corpos seguem os de `esquema do SIG de teste interno` linhas 204-245:

```
plat.auth_login(p_tenant text, p_login text)        -> usuario_id, tenant_id, senha_hash, perfil, nome, tenant_nome, totp_ativo, totp_secret, bloqueado_ate, falhas_login, superadmin
plat.auth_falha(p_usuario int, p_max int, p_min int) -> void   (incrementa falhas, bloqueia)
plat.auth_ok(p_usuario int)                          -> void   (zera falhas, ultimo_login = now())
plat.auth_sessao_criar(p_usuario int, p_horas int, p_ip text, p_agente text) -> text  (devolve o token em claro; grava só o hash)
plat.auth_sessao(p_hash text)                        -> usuario_id, tenant_id, login, perfil, nome, tenant_slug, tenant_nome, superadmin, config
plat.auth_sessao_encerrar(p_hash text)               -> void
plat.auth_token(p_hash text, p_ip text)              -> usuario_id, tenant_id, login, perfil, escopos, restricao, token_id   (só se revogado_em IS NULL e (expira_em IS NULL OR expira_em > now()))
plat.log_registrar(p_tenant int, p_usuario int, p_token int, p_ip text, p_metodo text, p_rota text, p_status int, p_bytes bigint, p_tempo_ms int, p_agente text, p_resultado text) -> void
plat.tenant_criar(p_slug text, p_nome text, p_config jsonb, p_admin_login text, p_admin_nome text, p_senha_hash text) -> tenant_id, usuario_id   (exige superadmin na sessão, como SIG de teste interno plat_criar_tenant)
```

O que mudou em relação ao `SIG de teste interno` e por quê:

1. `sessao.token` em claro virou `sessao.token_hash`. LIDO: o `SIG de teste interno` guarda o token da sessão em
   claro e o do API token em hash; um dump do banco entregaria sessões válidas. Custo: um
   `hashlib.sha256` por requisição, sem dependência.
2. `sessao` ganhou `tenant_id` denormalizado: a política de RLS vira uma comparação direta em
   vez da subconsulta `usuario_id IN (SELECT ...)` do `SIG de teste interno` (executada em toda leitura de sessão).
3. Perfis `admin, editor, visualizador, campo` no lugar de `admin, tecnico, consulta, cliente`.
   Os quatro nomes são os papéis que o produto expõe (plano do laço: edição, visualização e
   coleta em campo, item L2-07). `campo` só usa formulários e a PWA; `visualizador` não edita.
   A tabela de permissão fina por camada e por item do catálogo é do L0-03 (não nasce aqui).
4. `token_servico.escopos` e `restricao`: o `SIG de teste interno` tem token sem escopo; o portão P6 exige "token
   com escopo e log". O vocabulário de escopos é decisão do L0-02 e vai para o `docs/openapi.json`.
5. `log_acesso` unifica o `login_audit` do `SIG de teste interno` (só login) com o log de leitura por token que o
   portão do L0-02 pede ("token de serviço aparece no log com IP/rota/bytes"). Uma tabela, um
   índice por inquilino e um por token. Retenção e particionamento são do L7.
6. `senha_hash` continua `pbkdf2_sha256` da biblioteca padrão, com 600.000 iterações (OWASP
   Password Storage Cheat Sheet, versão vigente em 2026, recomenda 600.000 para PBKDF2-HMAC-SHA256).
   Motivo de não usar bcrypt: zero dependência nova e o `SIG de teste interno` já valida esse formato.
7. `email` nullable e `slug` com CHECK de formato: o slug vai para URL e para o nome do bucket
   Garage (L1-01); um CHECK evita corrigir depois.

Ordem de leitura para o L0-02: `002_identidade.sql` cria tudo acima; o L0-02 acrescenta as rotas
(`/api/login`, `/api/logout`, `/api/eu`, `/api/usuarios`, `/api/tokens`, 2FA) e a tela; se
precisar de coluna nova, é `003_*.sql`, nunca edição da 002.

---

## 7. Contrato de `/saude` e `/api/versao`

`GET /saude` (sem autenticação, sem log de acesso, sem cache):

```json
{
  "versao": "0.1.0",
  "git_sha": "a1d0c20",
  "ambiente": "producao",
  "banco": "ok",
  "migracoes_aplicadas": 2,
  "migracoes_pendentes": 0,
  "ultima_migracao": "002_identidade",
  "servicos": {"martin": "ausente", "titiler": "ausente", "garage": "ausente"},
  "tempo_ms": 3.8,
  "em": "2026-09-05T15:04:05Z"
}
```

- `banco`: `ok` (SELECT 1 e leitura de `versao_migracao` responderam), `desatualizado`
  (arquivo em `db/migracoes/` sem linha na tabela) ou `erro` (exceção; a mensagem vai para o log,
  não para a resposta).
- HTTP 200 só com `banco = ok`; `desatualizado` e `erro` devolvem **503** com o mesmo JSON.
  Motivo: o `driver.sh` faz `curl -fsS /saude` e trata falha como "SEM RESPOSTA"; 503 em banco
  desatualizado faz o driver acusar no log em vez de esconder.
- `servicos.<nome>`: `ausente` quando a chave `PLAT_<NOME>_URL` não está no `.env`; `ok` quando
  um GET com timeout de 1 s devolve status < 500; `erro` caso contrário. MEDIDO: o Garage em
  `:3900` devolve 403 na raiz sem assinatura, por isso o critério é "< 500", não "== 200".
  Neste item os três são informativos: não mudam o status HTTP. O item que criar o serviço muda
  o contrato (L2-01 torna `martin` obrigatório, e assim por diante) e registra aqui, em ADR novo.
- `tempo_ms`: medido dentro da rota (perf_counter), da entrada à montagem do JSON.
- `git_sha`: lido uma vez na partida, de `.git/HEAD` e do arquivo de ref apontado (sem
  subprocesso); se o repositório não tiver `.git` (instalação por tarball), lê `PLAT_GIT_SHA` do
  `.env`, que o `install.sh` grava. Nunca "desconhecido" em produção: o teste `test_versao` exige
  7 a 40 caracteres hexadecimais. **Alterado em T1:** o `install.sh` deixava `PLAT_GIT_SHA=` vazio;
  agora grava `git rev-parse HEAD` no `.env` a cada execução (passo d) e, sem `.git`, aborta se o
  `.env` não trouxer um sha válido. `app/versao.py` lê o ambiente do processo e, se vazio, o
  `PLAT_GIT_SHA` do `.env` via `settings` (importação tardia). Três testes de unidade cobrem os
  três caminhos (ambiente, `.env`, nenhum).

`GET /api/versao` (sem banco, sempre 200): `{"versao","git_sha","ambiente","em"}`. Serve para o
front mostrar a versão e para o e2e confirmar que a página e a API são a mesma implantação.

`GET /api/openapi.json` e `GET /api/docs`: expostos como no `SIG de teste interno` (`docs_url='/api/docs'`),
atrás do `noindex` do nginx. **Alterado em T1:** o `docs_url` padrão do FastAPI carrega o Swagger UI
de CDN e o favicon de `fastapi.tiangolo.com`, o que contradiz a seção 11.4. A rota `/api/docs` é
própria (`get_swagger_ui_html`) com `swagger-ui-bundle-5.32.15.js`, `swagger-ui-5.32.15.css` e
`favicon.svg` servidos de `web/` pelo nginx (sha256 em `web/vendor/VERSOES.txt`, licença
Apache-2.0, origem `npm pack swagger-ui-dist@5.32.15`), `validatorUrl` nulo (sem consulta a
`validator.swagger.io`) e `redoc_url=None` (o ReDoc padrão também vinha de CDN). O teste
`tests/api/test_docs.py` reprova qualquer `http://` ou `https://` no HTML.

---

## 8. Configuração (`.env`)

Arquivo `.env` na raiz do repositório, modo `600`, dono `dev`, criado pelo `install.sh` se não
existir (senha da role gerada com `openssl rand -hex 16`, como o `install.sh do SIG de teste interno`). Lido por
`app/settings.py` com `python-dotenv` (1.2.2, no sistema); toda chave obrigatória ausente aborta
a partida com mensagem que nomeia a chave. `.env.exemplo` é comitado com todas as chaves e
valores de exemplo; `.gitignore` já tem `.env*`, e o backend acrescenta `!.env.exemplo`.

| chave | obrigatória | exemplo | uso |
|---|---|---|---|
| PLAT_DSN | sim | `postgresql://plat_app:<senha>@127.0.0.1:5432/iagro_sat` | pool |
| PLAT_AMBIENTE | sim | `producao` ou `dev` | `/saude`, nível de log |
| PLAT_URL_PUBLICA | sim | `https://plat.iagrointel.com` | cookies `Secure`, links absolutos, e2e |
| PLAT_GIT_SHA | não | `a1d0c20` | só sem `.git` |
| PLAT_MARTIN_URL | não | `http://127.0.0.1:8151` | `/saude` |
| PLAT_TITILER_URL | não | `http://127.0.0.1:8152` | `/saude` |
| PLAT_GARAGE_URL | não | `http://127.0.0.1:3900` | `/saude` |
| PLAT_LOG_NIVEL | não | `INFO` | logging |

**Alterado no item L7-19-segredos-e-certificados:** `PLAT_SECRET` e `PLAT_DSN_WORKER` (a senha da role
`plat_worker`) saíram desta tabela e do `.env` — moram em `/etc/plat/segredos/`, dono `root`, modo
`600`, e chegam a `plat-api`/`plat-worker` por `LoadCredential=` do systemd (não por argumento nem por
`Environment=` da unidade, então a regra abaixo continua valendo). Detalhe completo, rotação e o
porquê em `docs/SEGURANCA.md`. As demais chaves da tabela continuam no `.env` como descrito aqui.

Regra: segredo nunca em argumento de linha de comando nem em `Environment=`/argv de unidade systemd
(aparece em `ps` e em `systemctl show`); hoje isso é o `.env` 600 (chaves acima) **ou** um arquivo fora
do repositório entregue por `LoadCredential=` (`PLAT_SECRET`, `PLAT_DSN_WORKER` — `docs/SEGURANCA.md`).
Porta e caminho não são segredo e ficam na unidade.
**Alterado em T1: motivo** — o passo g do `install.sh` quebrava esta regra: a senha de
demonstração ia em `argv` de `sudo -u ... python -c`, e o `sudo` grava `COMMAND=` inteiro no
journal (18 linhas em claro achadas pelo adversário). Agora a senha entra por `stdin`
(`printf '%s' "$senha" | python -c "... gerar_hash(sys.stdin.read())"`; `printf` é builtin e não
aparece em `ps`), o hash resultante vai ao `psql` por heredoc, e `tests/unit/test_instalador.py`
reprova qualquer `gerar_hash(sys.argv`. As senhas semeadas antes da correção foram trocadas
(`tests/credenciais.txt` regenerado) porque o journal antigo continua legível por root e pelos
grupos `systemd-journal`/`adm`.

---

## 9. Logging

- Formato: uma linha JSON por evento em stdout (journal do systemd). Campos fixos: `ts`
  (ISO 8601 UTC), `nivel`, `msg`, `logger`; campos de requisição quando houver: `req_id`
  (16 hex, gerado no middleware e devolvido no cabeçalho `X-Req-Id`), `metodo`, `rota`,
  `status`, `tempo_ms`, `ip`, `tenant_id`, `usuario_id`, `token_id`; exceção: `exc` com traceback
  em string.
- Leitura: `journalctl -u plat-api -o cat | jq`. Motivo do JSON: o `driver.sh` e o testador
  extraem número com `jq`, sem regex sobre texto livre.
- O middleware de acesso grava a mesma linha em `plat.log_acesso` (seção 6) para rotas `/api/`,
  `/svc/` e `/ogc/`; não grava `/saude`, `/static/` nem `/api/versao` (ruído do driver a cada
  30 min). Custo de um INSERT local por requisição: o testador mede em `tests/medidas/L0-01-repo.json`
  (`latencia_saude_ms` sem log e `latencia_versao_ms` sem log servem de base; a rota com log entra
  no L0-02).
  **Decisão explícita (alterado em T1):** neste item o middleware escreve **só** a linha JSON no
  journal; a gravação em `plat.log_acesso` fica para o item **L0-02**, porque hoje não existe rota
  autenticada e a linha só faz sentido com `tenant_id`/`usuario_id`/`token_id` resolvidos pela
  sessão ou pelo token, que o L0-02 cria. Não é omissão: `app/main.py` não chama
  `plat.log_registrar` de propósito, e o L0-02 tem de entregar a chamada junto com o teste
  "token de serviço aparece no log com IP/rota/bytes" do seu portão.
- Nível `DEBUG` nunca em `producao` (o `settings.py` rebaixa para `INFO` e avisa).

---

## 10. Testes e `make check`

- venv do repositório: `/home/dev/plataforma/enterprise/venv` (Python 3.12.3, pytest 9.1.1,
  pytest-playwright 0.9.0, playwright 1.59.0, ruff 0.16.6 instalado neste turno, MEDIDO: 23 MB
  no `venv/bin/ruff`, venv total 43 MB).
- `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["lento: e2e ou medição demorada; excluído do driver (pytest -m 'not lento')", "e2e: playwright contra a URL interna"]
addopts = "-q --strict-markers"

[tool.ruff]
line-length = 120
target-version = "py312"
[tool.ruff.lint]
select = ["E", "F", "W", "B", "I"]
```

- Convenção de arquivos: `tests/unit/test_*.py` (sem rede, sem banco), `tests/api/test_*.py`
  (TestClient do FastAPI para rotas; conexão `plat_app` para RLS e migrações; HTTP real em
  `http://127.0.0.1:8150` e `https://plat.iagrointel.com` para cabeçalhos), `tests/e2e/test_*.py`
  marcados `@pytest.mark.lento` e `@pytest.mark.e2e`, `--base-url https://plat.iagrointel.com`,
  navegador chromium do playwright (MEDIDO: `~/.cache/ms-playwright` tem chromium 1234 =
  Chromium 147.0.7727.15, abriu `https://plat.iagrointel.com/saude` a partir da venv; o
  google-chrome do sistema não serve, regra da casa).
- Capturas: `page.screenshot(path=f"tests/e2e/capturas/{item}_{tela}.png", full_page=True)`;
  nome fixo por tela para o MANUAL apontar; `.gitignore` já exclui os PNG.
- Medidas: fixture `medida(nome, valor, unidade)` em `conftest.py` escreve/atualiza
  `tests/medidas/<item>.json` como `{"item","gerado_em","git_sha","medidas":{nome:{valor,unidade,comando}}}`.
  Documento cita número só por esse caminho (guardrail do estado). **Alterado em T1:** a fixture só
  grava com `PLAT_GRAVAR_MEDIDAS=1` (a suíte não pode sujar a árvore); o alvo `make medidas` roda a
  suíte inteira com essa variável e é o único caminho que o testador usa para regravar o arquivo.
- `Makefile`:

```make
VENV=venv/bin
export PYTHONNOUSERSITE=1                   # alterado em T1: a suíte roda no mesmo ambiente do serviço
check: lint sem-marcador teste e2e          ## suíte inteira (portão P3)
check-rapido: lint sem-marcador teste       ## o que o driver roda
lint: ; $(VENV)/ruff check app tests
teste: ; $(VENV)/pytest -m "not lento"
e2e: ; $(VENV)/pytest -m lento --base-url $(shell grep ^PLAT_URL_PUBLICA .env | cut -d= -f2)
medidas: ; PLAT_GRAVAR_MEDIDAS=1 $(VENV)/pytest --base-url ...   # alterado em T1: implementado
vendor: ; cd web/vendor && ... | sha256sum -c                     # alterado em T1: confere VERSOES.txt
sem-marcador: ; ! grep -rnI --exclude-dir=vendor --exclude-dir=node_modules --exclude-dir=tests --exclude-dir=.git --exclude-dir=venv -E -f tests/marcadores.regex app web db docs deploy install.sh Makefile requirements.txt pyproject.toml *.md
migrar: ; sudo bash db/migrar.sh
openapi: ; $(VENV)/python -c "import json; from app.main import app; json.dump(app.openapi(), open('docs/openapi.json','w'), ensure_ascii=False, indent=1)"
```

  O alvo `sem-marcador` usa a mesma expressão do `laco/driver.sh` (LIDA), copiada para
  `tests/marcadores.regex` (uma linha). **Alterado em T1:** a varredura passou a incluir os `.md`
  da raiz (README, ARQUITETURA, MANUAL, CHANGELOG), `requirements.txt` e `pyproject.toml`; `docs/`
  já era varrido. Motivo: o adversário achou os quatro `.md` como cascas fora da varredura.
  Motivo de o padrão viver em `tests/`: o driver e o alvo
  excluem `tests/` da varredura, então o arquivo com as palavras proibidas não se autoacusa; se a
  expressão ficasse dentro do `Makefile` ou deste ADR, a varredura reprovaria o próprio
  repositório (conferido: o grep do driver rodado sobre a primeira versão deste ADR acusou a
  linha do Makefile e a palavra "todos" em maiúsculas). O `!` inverte o grep: qualquer linha
  encontrada reprova. Observação lida no driver: o passo 4 dele roda
  `python3 -m pytest` com o Python do sistema, que não tem pytest (MEDIDO: `No module named
  pytest`). O driver não é editável por este papel; fica na pendência para o gerente.

---

## 11. Front: módulos ES sem bundler (decisão por medição)

### 11.1 O que foi medido (05/09/2026, scratchpad, apagado depois)

Projeto Vite mínimo (`vite ^6.3.5` + `maplibre-gl ^5.6.0`, um `index.html`, um `main.js`):

| grandeza | Vite | vanilla (o que `SIG de teste interno` faz hoje) |
|---|---|---|
| `node_modules` | 78 MB, 1.660 arquivos | 0 |
| cache do npm gerado pelo install | 95 MB | 0 |
| `npm install` | 5,45 s (rede quente) | 0 |
| `vite build` | 2,73 s de relógio, **391.628 kB de RSS de pico** | 0 (publicar = recarregar) |
| saída | 1 arquivo de 1.056 kB (MapLibre dentro), 285 kB gzip | MapLibre 803 kB + css 65 kB em `vendor/`, módulos próprios 240 kB em 5 arquivos |
| cache no navegador | hash no nome do arquivo | `no-store` no nginx nos módulos |

Custos fixos desta máquina que pesam na conta: 3 GB de RAM disponíveis e 13 GB de disco em
98 %. Um build de 392 MB de RSS cabe, mas concorre com os agentes do laço (regra: `free -g`
≥ 4 GB antes de lançar agente) e 173 MB de árvore por cópia do repositório entram no limite de
3 GB do repositório.

### 11.2 Decisão

**Módulos ES nativos, sem bundler, MapLibre GL JS em `web/vendor/`**, com quatro regras que
mantêm a porta aberta para bundler e para construtores grandes:

1. Todo módulo é ESM padrão com importação relativa (`./js/x.js`), sem variável global além de
   `maplibregl` (carregado por `<script>` clássico antes do módulo de entrada, como `SIG de teste interno`).
   Consequência MEDIDA: esse layout é exatamente o que o Vite consome sem alteração
   (`index.html` como entrada); ligar o Vite depois custa um `package.json` e um alvo no
   `Makefile`, e nenhuma linha de código muda.
2. Nunca `?v=` em `import`. O cache é `no-store` no nginx (seção 4.2). Regra da casa, com o
   incidente de 01/09/2026 documentado no `publicar.sh do SIG de teste interno`.
3. Bibliotecas de terceiros entram como ESM ou UMD em `web/vendor/<nome>-<versão>.js`, com
   linha em `web/vendor/VERSOES.txt` (nome, versão, sha256, licença, URL de origem). Licenças
   admitidas: BSD, MIT, Apache 2.0, ISC. Primeira entrada: `maplibre-gl 4.7.1`, BSD-3, cópia do
   arquivo que roda em `SIG de teste interno` (803.086 bytes; versão lida no cabeçalho do arquivo).
   Atualizar para 5.x é troca de arquivo + e2e, no item L2-01, quando houver mapa para testar.
   **Alterado em T1:** os arquivos passaram a seguir a convenção (`maplibre-gl-4.7.1.js`,
   `maplibre-gl-4.7.1.css`) e entraram `swagger-ui-bundle-5.32.15.js` e `swagger-ui-5.32.15.css`
   (Apache-2.0, seção 7). `tests/unit/test_vendor.py` reprova nome fora de `<nome>-<versão>.js|css`,
   arquivo sem linha em `VERSOES.txt`, sha256 divergente e licença fora da lista; `make vendor` faz
   a mesma conferência por `sha256sum -c`.
4. Orçamento: módulo próprio ≤ 60 kB; primeira pintura da tela medida no e2e e gravada em
   `tests/medidas/`. Quando um módulo passar do orçamento, divide-se; quando a soma dos módulos
   de uma tela passar de 400 kB, o item que causou isso reavalia esta seção em ADR novo.

### 11.3 E os construtores arrasta-e-solta (L5)?

Um construtor de aplicação, de fluxo ou de painel é um documento JSON (árvore de layout, widgets
e ações) mais um renderizador. Arrastar e soltar é API nativa do navegador (Drag and Drop e
Pointer Events); reordenação em lista pode entrar como `SortableJS` (MIT, ESM, ~44 kB) pela
regra 3. Nada disso exige bundler. O que um construtor grande pode pedir e este ADR NÃO decide é
um framework de componentes (React, Vue, Lit). Essa decisão é do L5-01, com medição própria, e
fica escrito o custo: trocar de bundler custa zero (regra 1); trocar para framework é reescrever
`web/js/`, porque o estado e a renderização passam a viver no framework. Por isso o L5-01
começa em vanilla, e só muda se o e2e do próprio item reprovar por complexidade medida (tempo de
resposta da interação, número de defeitos), nunca por preferência.

### 11.4 O que se rejeitou e por quê

- Vite/npm agora: custo medido (seção 11.1) sem função visível para o usuário neste item; o
  único ganho real, cache por hash, já está resolvido por `no-store`.
- SDK JavaScript da Esri: licença proprietária; DOC.md 17.2 manda trocar por MapLibre.
- CDN para MapLibre: a URL interna é `noindex` e o produto tem de funcionar em rede fechada de
  cliente (item L7-01, "instalador limpo"); dependência externa em tempo de execução quebra isso.

---

## 12. Regras transversais que este ADR fixa

1. Número em documento, README, MANUAL ou PARIDADE sai de `tests/medidas/*.json`, com o comando
   que o gerou. Número digitado à mão é erro de revisão.
2. Português nos identificadores expostos (rotas, colunas, mensagens de erro, nomes de teste);
   inglês só onde a biblioteca exige (`tenant_id` fica por herança do `SIG de teste interno` e por ser o nome que
   o mercado usa em RLS; `token`, `slug`, `hash` idem).
3. Nenhum nome de cliente, parceiro ou piloto no código, dado de exemplo, teste ou captura
   (portão P7). O dado de demonstração é aberto e pequeno; o primeiro inquilino de teste chama-se
   `demo` e o segundo `demo2` (necessários para o teste cruzado A→B do P6).
4. Nada manual fora de script (portão P5): o que o `install.sh` não faz, não existe.
5. Um serviço novo = uma unidade `plat-<nome>` em `deploy/`, uma porta da faixa 8150-8159, um
   campo em `/saude`, uma linha em `ARQUITETURA.md`, no mesmo turno.

---

## 13. Consequências e o que custa mudar

| decisão | custo de reverter |
|---|---|
| psycopg2 síncrono | trocar para psycopg 3 assíncrono = reescrever `db.py` e as rotas `def` em `async def`; medir antes (L7-02); nada a fazer agora |
| nginx `alias` para `web/` | uma `location`; coexiste com `StaticFiles` |
| migração por sha imutável | nenhum: é só disciplina; arquivo errado = arquivo novo |
| perfis de 4 valores | `ALTER TABLE ... DROP CONSTRAINT` + novo CHECK em migração; nenhuma coluna muda |
| `sessao.token_hash` | nenhum |
| sem bundler | ligar Vite = 1 `package.json` + 1 alvo; zero linha de código (seção 11.2 regra 1) |
| sem framework | reescrever `web/js/` (seção 11.3); decisão adiada ao L5-01 com medição |
| `MemoryMax=1G` | editar `deploy/plat-api.service` e `daemon-reload`; medir com `MemoryPeak` antes |
