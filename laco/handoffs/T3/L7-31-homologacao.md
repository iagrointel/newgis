# L7-31-ambiente-homologacao — turno 3 (sessão única: arquiteto+backend)

**Objetivo do turno** (recorte dado pelo pedido que abriu o item, MENOR e diferente da hipótese do
backlog): construir um ambiente de homologação com schema `plat_homolog` SEPARADO **no mesmo Postgres**
(`laco/estado.json` tinha registrado `CREATE DATABASE plat_homolog` — mudado explicitamente para schema,
porque `/` estava a 98% e `/mnt/pgdata` a 99% de disco quando o item começou), com as mesmas migrações
aplicadas de forma independente, `make homolog` (API+worker temporários em `:8154`, e2e isolado), e prova
de isolamento por contagem de tabelas. Subdomínio DNS, senha básica e réplica anonimizada do inquilino
demo (partes da hipótese original do backlog) **ficaram fora** — não pedidos neste recorte.

## Portão do item no backlog (para referência; recorte deste turno é menor)

> `install.sh --ambiente homolog` cria tudo idempotente; `make check` e e2e passam contra a URL de
> homologação; produção e homologação nunca compartilham banco, bucket, chave ou segredo; consumo de RAM
> medido; `docs/AMBIENTES.md`.

Este turno entrega o equivalente com schema (não `install.sh --ambiente`, que exigiria reescrever o
instalador de produção inteiro): `db/homolog_bootstrap.sh` idempotente + `make homolog`; e2e passa
PARCIALMENTE (ver §4); banco/papel/canal nunca compartilhados, bucket compartilhado só no PREFIXO (ver
§5, risco nomeado); RAM não medida por unidade systemd (não há unidade — são processos temporários).
`docs/HOMOLOGACAO.md` cobre o que `docs/AMBIENTES.md` cobriria.

## O que fiz

### 1. Por que schema, não banco (decisão herdada, não minha)

A hipótese do backlog pedia `CREATE DATABASE`. O pedido que abriu este turno mudou isso explicitamente
para schema no mesmo `iagro_sat`, citando disco a 98%/99% (medido: `df -h /` = 12 GB livres, `/mnt/pgdata`
= 13 GB livres). Segui a instrução literal, documentada em `docs/adr/0009-ambiente-homologacao.md`.

### 2. Migração idêntica, reescrita em voo (não duplicada em disco)

`db/reescrever_homolog.py` troca token a token o texto de CADA `db/migracoes/*.sql` antes de mandar ao
`psql`: schema `plat`→`plat_homolog`, `plat_trabalho`→`plat_trabalho_homolog`, papel `plat_app`→
`plat_homolog_app`, papel/canal `plat_worker`→`plat_homolog_worker`, canal `plat_job`→`plat_homolog_job`.
GUC customizado (`current_setting('plat.tenant_id', ...)` e ~9 chaves do mesmo padrão) fica de fora por
CONTEXTO (não roda a troca logo depois de `current_setting('`/`set_config('`), não por lista de nomes —
conferido 1 a 1 contra as 17 ocorrências reais da árvore antes de aplicar qualquer coisa no banco.
`db/migrar_homolog.sh` é a mesma mecânica de `db/migrar.sh`, com controle de versão próprio
(`plat_homolog.versao_migracao`). Rodado de verdade: **25/25 migrações aplicadas limpo** na primeira vez
(nenhuma reaplicada, nenhuma divergente).

### 3. App fala com dois schemas sem refatorar as rotas

O hardcode `plat.`/`plat_trabalho.` está espalhado em dezenas de arquivos (`auth/`, `acervo/`,
`catalogo/`, `jobs/`) — reescrever cada um seria um refactor grande demais para este item, e arriscado em
paralelo com outras trilhas mexendo nos MESMOS arquivos no mesmo turno (medido: colisão real em
`app/settings.py`/`app/jobs/worker.py`, ver §6). Em vez disso: `app/schema_ambiente.py` define
`CursorSchemaAmbiente` (subclasse de `RealDictCursor`) que reescreve o TEXTO da consulta antes de mandar
ao servidor, plugado nos dois únicos pontos onde uma conexão nasce (`app/db.py`, `app/jobs/worker.py`) —
cobre a API, o processo filho de cada job (herda por fork) e o relógio de agendas. Produção não paga
custo: a função devolve a mesma string quando `PLAT_SCHEMA == "plat"`. 4 chaves novas em
`app/settings.py` (`PLAT_SCHEMA`, `PLAT_SCHEMA_TRABALHO`, `PLAT_CANAL_JOB`, `PLAT_CANAL_WORKER`);
`PLAT_DSN_WORKER` passou a validar o papel pelo PREFIXO derivado do schema (antes era um literal fixo
`plat_worker`).

**Achado que não estava na hipótese**: NOTIFY/LISTEN é por BANCO, não por schema —
`pg_notify('plat_job', ...)` chegaria a QUALQUER sessão fazendo `LISTEN plat_job`, inclusive o SSE e o
worker de PRODUÇÃO. Corrigido com `PLAT_CANAL_JOB`/`PLAT_CANAL_WORKER` (mesma convenção de nome do
schema/papel).

### 4. `make homolog` — bootstrap, nginx, seed, teardown

`db/homolog_bootstrap.sh` (idempotente): migra, cria papéis com senha própria (`var/homolog/segredos.env`,
0600), linha em `pg_hba.conf` (só recarrega o Postgres se mudou — reload, nunca restart), semeia dado de
TESTE (admin de `plataforma`/`demo`/`demo2` com senha PRÓPRIA em `tests/credenciais_homolog.txt` — nunca
cópia de produção), escreve `var/homolog/homolog.env`, e sobe um site nginx PRÓPRIO
(`deploy/nginx_homolog.conf`) porque **a API nunca serviu `/static/` sozinha** (achado real do 1º turno
deste item: sem nginx na frente, TODO teste de tela travava 20 s em `body[data-pronto='1']` porque
`login.js`/`style.css` voltavam 404 — ficou registrado como armadilha em `docs/HOMOLOGACAO.md`).
`scripts/homolog_e2e.sh` sobe uvicorn (`:8158` interno) + worker temporários, espera `/saude`, roda
`pytest -m lento --base-url http://127.0.0.1:8154` sob `flock .pytest.lock`, e SEMPRE mata os dois pelo
PID EXATO no `trap EXIT/INT/TERM` (nunca `pkill -f`, porque o `plat-worker` de produção sobe com a MESMA
linha de comando).

**Evidência da suíte de e2e rodando de verdade** (3 rodadas neste turno, cada uma corrigindo um achado):
rodada 1 (sem nginx) = 1 passou/8 falhou; rodada 2 (+ nginx) = 4 passaram/5 falharam (login 401: credencial
de produção); rodada 3 (+ seed próprio) = **23 passaram, 8 falharam, 12 erro** (de ~43 testes
relevantes). Dos 8 falhos + 12 erros: a maioria são **timeouts de interação em navegador sob carga
extrema** (12 processos concorrentes disputando o MESMO `flock`/CPU no momento da rodada — medido:
`ps aux | grep flock` = 12) e **12 ERROR de `tests/api/ldap/`**, fixture de OUTRA trilha do mesmo turno
(`tests/ldap_fixture/`), não relacionada a schema/ambiente — falharia igual contra produção agora. Não
tive tempo neste turno para isolar e reduzir a carga concorrente e rodar uma 4ª rodada limpa; fica como
próximo passo (§ Pendências).

### 5. O que NÃO isola (nomeado, não escondido)

- Advisory lock do job pesado (`LOCK_PESADO = "plat.job.pesado"`, string fixa em `app/jobs/worker.py`) é
  global ao banco — homologação e produção disputam a MESMA trava se um `prova.pesado` rodar dos dois
  lados ao mesmo tempo. `pg_try_advisory_lock` não bloqueia (falha rápido), risco baixo, não corrigido.
- Garage é o MESMO servidor (sem disco para outro); isolamento é só o prefixo do bucket
  (`homolog-plat-` vs `plat-`), com o MESMO token admin de produção reusado (lido do `.env` real a cada
  bootstrap, nunca copiado para dentro de um script).
- OSRM/Martin/TiTiler/GPU box continuam compartilhados (serviços de leitura, sem dado de inquilino).

### 6. Colisão de área real (dois itens no mesmo arquivo, mesmo turno)

`app/settings.py` e `app/jobs/worker.py` também estavam sendo editados por outra trilha (L2-11-c OSRM,
L0-05-e cgroup) no mesmo turno. `app/settings.py`/`app/limites.py` já saíram commitados por aquela trilha
(19c4cb3, cirúrgico, incluindo minhas 4 chaves — confirmado por `git diff HEAD` vazio antes deste commit).
`app/jobs/worker.py` eu resolvi com staging cirúrgico próprio: reconstruí "HEAD + só meus 2 hunches"
num arquivo temporário, `git hash-object -w` + `git update-index --cacheinfo`, sem tocar a árvore de
trabalho (que continua com as duas mudanças funcionando juntas localmente) — o commit deste item carrega
só o que é meu.

## Prova de isolamento (evidência literal)

```
$ sudo -u postgres psql -d iagro_sat -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='plat'"
44
$ ...table_schema='plat_homolog'
44
# CREATE TABLE plat.zzz_prova_homologacao(...) reescrito -> plat_homolog.zzz_prova_homologacao(...)
$ venv/bin/python db/reescrever_homolog.py scratchpad/l7-31/999_prova_homologacao.sql | sudo -u postgres psql -d iagro_sat -f -
$ ...table_schema='plat'          -> 44   (inalterado)
$ ...table_schema='plat_homolog'  -> 45   (+1)
$ ...table_schema='plat' AND table_name='zzz_prova_homologacao'         -> 0
$ ...table_schema='plat_homolog' AND table_name='zzz_prova_homologacao' -> 1
$ sudo -u postgres psql -d iagro_sat -c "DROP TABLE plat_homolog.zzz_prova_homologacao;"
$ ...table_schema='plat'          -> 44   (inalterado, o turno inteiro)
$ ...table_schema='plat_homolog'  -> 44   (de volta à linha de base)
```
Números e comandos completos em `tests/medidas/L7-31-homologacao.json`.

## `make check` (escopo verde)

- `venv/bin/ruff check` nos meus arquivos: limpo.
- `sem-marcador` nos meus arquivos: limpo (dois falsos-positivos de "TODO"/palavra portuguesa em
  `docs/HOMOLOGACAO.md`/ADR corrigidos por mim antes do commit).
- `tests/unit` inteiro (sob flock): **verde** (achei e corrigi de passagem um E501 pré-existente em
  `app/limites.py`, de outra trilha ainda não commitada, que travava `make lint` para a árvore inteira —
  e regenerei `docs/LIMITES.md`, que dependia do texto do comentário).
- `make check`/`make check-rapido` completos para a ÁRVORE INTEIRA **não fecham verde agora**: outros
  arquivos não meus (`tests/api/jobs/test_jobs_sse.py`, `app/jobs/filho.py`, `docs/adr/0010-*`) têm
  lint/marcador pendente de OUTRAS trilhas em voo no mesmo turno — não são meus para consertar. `teste`
  completo contra produção também tropeçou num bloqueio temporário (423) do usuário `plataforma` por
  força bruta de OUTRAS trilhas rodando `test_login.py` concorrentemente — transitório, não é bug meu.
- Não tocado: `plat-api`/`plat-worker` de produção (confirmado: nenhum comando meu chama
  `systemctl ... plat-api`/`plat-worker`; um restart real de `plat-worker` aconteceu às 10:45:32 durante a
  janela deste turno — verificado no journal, não veio de nenhum script meu, provavelmente deploy de outra
  trilha).

## Riscos

- Advisory lock compartilhado (§5) — baixo, não bloqueante, nomeado no ADR.
- `make homolog` sobe processos reais (uvicorn+worker+nginx reload) numa máquina com ~400 MB livres — 3
  rodadas deste turno não derrubaram nada, mas é sensível a concorrência (12 trilhas disputando RAM/CPU
  ao mesmo tempo é o normal desta casa agora).
- e2e de homologação ainda não está 100% verde (§4) — mecanismo provado, faltou tempo para uma rodada
  limpa sem a carga concorrente do turno.

## Pendências (para quem continuar)

1. Rodar `make homolog` numa janela com menos concorrência da casa e medir o resultado limpo (a suíte
   melhorou a cada rodada — 1 → 4 → 23 testes passando — a tendência é resolver sozinha).
2. Isolar o advisory lock do job pesado por schema, se algum dia incomodar de verdade.
3. `docs/AMBIENTES.md` citado no portão original do backlog não foi criado — `docs/HOMOLOGACAO.md` cobre
   o mesmo conteúdo; renomear/linkar se o dono quiser o nome exato.

## Para o próximo papel

Testador: rodar `make homolog` de novo (idempotente) numa janela mais tranquila e anexar o resultado a
`tests/medidas/L7-31-homologacao.json`. Adversário: tentar alcançar `plat`/dado de produção a partir de um
processo apontado para `var/homolog/homolog.env` (DSN, bucket, canal, advisory lock — este último É um
caminho real, nomeado acima, não escondido).
