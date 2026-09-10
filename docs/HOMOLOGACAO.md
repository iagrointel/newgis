# Ambiente de homologação (item L7-31)

Ponto de decisão que abriu este item: `laco/estado.json` (L7-31) tinha registrado a hipótese de um
BANCO Postgres novo (`CREATE DATABASE plat_homolog`). O pedido que disparou este turno mudou isso
explicitamente — schema `plat_homolog` no MESMO banco `iagro_sat`, nunca um banco novo, porque `/`
estava a 98% e `/mnt/pgdata` a 99% de disco quando o item começou. O raciocínio completo (por que um
schema dá para isolar tudo que importa, e o que NÃO isola) está em `docs/adr/0009-ambiente-homologacao.md`.

## O que é

Um segundo conjunto completo dos objetos do produto — schema `plat_homolog` (espelho de `plat`) e
`plat_trabalho_homolog` (espelho de `plat_trabalho`) —, papéis de banco próprios
(`plat_homolog_app`, `plat_homolog_worker`), canal de notificação próprio (`plat_homolog_job`,
`plat_homolog_worker`), API e worker próprios (processos temporários, nunca as unidades systemd
`plat-api`/`plat-worker`), tudo dentro do MESMO Postgres e do MESMO banco `iagro_sat` de produção.
Dado é semeado NA HORA (tenants `demo`/`demo2`/`plataforma` com admin próprio, senha gerada, nunca
copiada de produção) — nunca é um `pg_dump`/restore do que já existe.

## Quando usar

- **Antes de aplicar uma migração de risco em produção** (uma que muda estrutura de tabela grande,
  reescreve um trigger, ou mexe em privilégio): `make homolog` aplica a MESMA migração no schema de
  homologação e roda a suíte inteira contra ela primeiro.
- **Antes de um release** que mexeu em rota autenticada, RLS ou fila de jobs — qualquer coisa que só
  se prova com a API de pé e um navegador de verdade.
- **Nunca** para gerar tráfego de demonstração para terceiro — isso é o produto rodando em
  `plat.iagrointel.com`; homologação é interna, efêmera, sem certificado, sem DNS.

## O fluxo, em ordem

```
make homolog
  └─ scripts/homolog_e2e.sh
       ├─ 1. db/homolog_bootstrap.sh (idempotente)
       │     a. db/migrar_homolog.sh — as MESMAS db/migracoes/*.sql, cada uma passada por
       │        db/reescrever_homolog.py antes do psql (troca schema/papel/canal; nunca escreve
       │        um arquivo novo em disco); controle de versão próprio: plat_homolog.versao_migracao
       │     b. papéis plat_homolog_app/plat_homolog_worker — senha gerada uma vez, guardada em
       │        var/homolog/segredos.env (0600, fora do git: var/ está inteiro no .gitignore)
       │     c. pg_hba.conf — uma linha por papel nesta lista (idempotente); só recarrega o
       │        postgres se algo mudou (reload, nunca restart — não derruba conexão existente,
       │        logo não derruba plat-api/plat-worker de produção)
       │     d. plat_homolog.ambiente = 'dev' / semear_demo = true
       │     e. DADO SEMEADO DE TESTE: admin de plataforma/demo/demo2 com senha própria (nunca a de
       │        produção), gravada em tests/credenciais_homolog.txt; cota de jobs/dia alta para os
       │        inquilinos de demonstração; faxina de resíduo zt-* de rodada anterior
       │     f. var/homolog/homolog.env — todas as variáveis que a API/worker temporários precisam
       │     g. nginx: site próprio (deploy/nginx_homolog.conf → sites-available/plat-homolog),
       │        escuta em 127.0.0.1:8154, serve /static/ do disco, proxia o resto para o uvicorn
       │        interno em 127.0.0.1:8158 — sem isso NENHUMA tela carrega JS/CSS (a app nunca
       │        serviu estático sozinha; achado real do primeiro turno deste item, não hipótese)
       ├─ 2. sobe `uvicorn app.main:app --port 8158` com o ambiente de var/homolog/homolog.env
       ├─ 3. sobe `python -m app.jobs.worker` com o mesmo ambiente
       ├─ 4. espera http://127.0.0.1:8154/saude responder (até 20 s)
       ├─ 5. roda a suíte de e2e (pytest -m lento --base-url http://127.0.0.1:8154), sob
       │     flock /home/dev/plataforma/laco/.pytest.lock (serializa contra qualquer make check/
       │     pytest concorrente de outra trilha da casa — regra de T2)
       └─ 6. trap EXIT/INT/TERM: mata a API e o worker PELO PID EXATO que guardou (nunca por
             padrão de linha de comando — plat-worker de produção sobe com a MESMA linha "python -m
             app.jobs.worker", só o ambiente muda; um pkill -f aqui poderia matar o de verdade)
```

`db/homolog_bootstrap.sh` pode rodar sozinho, fora do `make homolog`, quando só se quer o schema em
dia (sem subir API/worker) — por exemplo para inspecionar `plat_homolog` por psql direto.

## Como o mesmo código fala com dois schemas

O hardcode `plat.`/`plat_trabalho.` está espalhado em dezenas de rotas (`auth/`, `acervo/`,
`catalogo/`, `jobs/`) — reescrever cada uma para ler o schema de `settings` seria um refactor grande
demais para este item, e arriscado em paralelo com outras trilhas mexendo nos mesmos arquivos.
Em vez disso:

- `app/settings.py` ganhou 4 chaves novas — `PLAT_SCHEMA`, `PLAT_SCHEMA_TRABALHO`, `PLAT_CANAL_JOB`,
  `PLAT_CANAL_WORKER` — com o padrão de sempre (`plat`, `plat_trabalho`, `plat_job`, `plat_worker`).
  Produção nunca declara essas chaves: o padrão reproduz bit a bit o comportamento de antes deste
  item.
- `app/schema_ambiente.py` define `CursorSchemaAmbiente` (subclasse de
  `psycopg2.extras.RealDictCursor`): reescreve o TEXTO da consulta trocando `plat.`/`plat_trabalho.`
  pelo schema do ambiente atual antes de mandar para o servidor — e devolve a mesma string, sem rodar
  regex nenhuma, quando o schema já é o padrão (produção não paga custo). Plugado nos dois únicos
  pontos onde uma conexão nasce: `app/db.py` (pool da API; usado também pelo processo filho de cada
  job, que herda por fork) e `app/jobs/worker.py` (a conexão própria do worker, de onde
  `app/jobs/agenda.py` também lê via `con.cursor()` sem cursor_factory explícito — herda o da
  conexão).
- **GUC customizado fica de fora.** `current_setting('plat.tenant_id', ...)`, `set_config('plat.
  usuario_id', ...)` e mais ~8 chaves do mesmo padrão (`via_worker`, `lixeira`, `link_itens`,
  `transferencia`, `superadmin`, `versao_comentario`, `versao_rotulo`, `login`) são configuração de
  SESSÃO do Postgres, não um objeto dentro de um schema — continuam com o nome fixo `plat.<algo>`
  em QUALQUER ambiente. A regra de exclusão é por contexto (não roda a troca logo depois de
  `current_setting('`/`set_config('`), não por uma lista de nomes.
- **NOTIFY/LISTEN é por BANCO, não por schema.** `pg_notify('plat_job', ...)` chega a QUALQUER
  sessão que faça `LISTEN plat_job` no mesmo banco — inclusive o SSE e o worker de PRODUÇÃO. Por
  isso o canal também virou configurável (`PLAT_CANAL_JOB`/`PLAT_CANAL_WORKER`), e a migração
  reescrita troca o literal dentro do trigger. Sem essa troca, um job criado em homologação
  acordaria o worker de produção (achado real, corrigido no mesmo turno — ver ADR 0009 item 5).

## Prova de isolamento (o teste pedido pelo item)

Aplicar uma migração de teste (fictícia — cria e apaga uma tabela de prova) no schema de
homologação e provar que o schema `plat` de produção nunca muda, contando tabelas antes/depois nos
dois:

```
$ sudo -u postgres psql -d iagro_sat -Atc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='plat'"
44
$ sudo -u postgres psql -d iagro_sat -Atc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='plat_homolog'"
44

# migração fictícia (nunca entra em db/migracoes/): CREATE TABLE plat.zzz_prova_homologacao(...)
# reescrita por db/reescrever_homolog.py -> CREATE TABLE plat_homolog.zzz_prova_homologacao(...)
$ venv/bin/python db/reescrever_homolog.py scratchpad/l7-31/999_prova_homologacao.sql | \
    sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -f -

$ ...count(*) plat...          -> 44   (INALTERADO)
$ ...count(*) plat_homolog...  -> 45   (+1, a tabela de prova)
$ ...plat.zzz_prova_homologacao existe em produção?   -> 0
$ ...plat_homolog.zzz_prova_homologacao existe?       -> 1

$ sudo -u postgres psql -d iagro_sat -c "DROP TABLE plat_homolog.zzz_prova_homologacao;"
$ ...count(*) plat...          -> 44   (INALTERADO)
$ ...count(*) plat_homolog...  -> 44   (de volta à linha de base)
```

Números exatos e o comando completo estão em `tests/medidas/L7-31-homologacao.json` e no handoff do
turno (`laco/handoffs/T3/L7-31-homologacao.md`).

## O que fica de fora (residual, nomeado, não escondido)

- **Advisory lock do job pesado** (`LOCK_PESADO = "plat.job.pesado"`, `app/jobs/worker.py`) é uma
  string fixa, também global ao banco — homologação e produção disputam a MESMA trava se um
  `prova.pesado` rodar dos dois lados ao mesmo tempo. `pg_try_advisory_lock` falha rápido e não
  bloqueia ninguém (não é um risco de travar produção), mas não é isolamento de verdade. A suíte de
  homologação não dispara esse tipo de job por padrão. Corrigir exigiria a mesma convenção de nome
  usada em `PLAT_SCHEMA`; fora do escopo combinado para este item.
- **Garage (armazenamento de objeto) é o MESMO servidor** — não há disco para uma instância nova.
  A CREDENCIAL, porém, deixou de ser a mesma em 06/09/2026 (achado 11 do adversário do turno 3: o
  token de administração era byte a byte igual nos dois ambientes e enxergava `plat-demo` e
  `plat-demo2`). Homologação usa hoje uma chave S3 própria, sem poder de administração, dona só dos
  buckets que ela mesma cria (alias local da chave). Ver **`docs/AMBIENTES.md`** e
  `tests/unit/test_isolamento_homologacao.py`. O prefixo de bucket (`homolog-plat-`) continua
  existindo, mas como defesa em profundidade: ele separa o nome, não o poder.
- **OSRM, Martin/TiTiler e o GPU box continuam compartilhados** — são serviços de leitura (rota,
  tile, hardware), não guardam dado de inquilino; reusar não fura o isolamento de PRODUTO.

## Armadilhas (o que já custou tempo neste item)

- **A API nunca serviu `/static/` sozinha.** Isso é o nginx de produção (`location /static/` em
  `sites-enabled/plat.iagrointel.com`, `alias` direto para `web/`). Subir só o uvicorn faz qualquer
  teste de tela travar em 20 s esperando `body[data-pronto='1']` (o JS nunca chega, 404). É por isso
  que existe `deploy/nginx_homolog.conf` — sem ele, "sobe a API" não basta.
- **`PLAT_DSN_WORKER` valida o papel pelo PREFIXO** (`postgresql://{PLAT_SCHEMA}_worker:...`) — a
  validação em `app/settings.py` deriva o papel esperado do schema (item L7-31), não mais um literal
  `plat_worker` fixo; se o padrão mudar um dia, essa validação muda junto.
- **`tests/credenciais.txt` é de PRODUÇÃO** (escrito pelo `install.sh`, admins de `plat`). A suíte
  de homologação usa `tests/credenciais_homolog.txt` via `PLAT_CREDENCIAIS_ARQUIVO` (env), lido por
  `tests/e2e/apoio.py::credenciais()` e `tests/api/conftest.py::CREDENCIAIS` — sobrescrever o
  arquivo de produção faria o próximo `make e2e` de verdade falhar por senha errada.
- **role nova sem linha em `pg_hba.conf` sobe e quebra na 1ª consulta** (regra antiga da casa,
  vale aqui igual): `db/homolog_bootstrap.sh` cuida disso; se alguém rodar as migrações à mão sem
  passar por ele, a API de homologação não conecta.
- **Nunca `pkill -f "python -m app.jobs.worker"`** — é a MESMA linha de comando do `plat-worker` de
  produção; `scripts/homolog_e2e.sh` mata só pelo PID exato que guardou.
- **Migração numerada na hora** (regra antiga): `db/migrar_homolog.sh` lê `db/migracoes/` no
  momento em que roda, então pega qualquer migração nova de outra trilha automaticamente — não há
  lista fixa para manter em dia.
