# ADR 0009 — Ambiente de homologação (item L7-31)

## Contexto

O laço precisava de um lugar para testar uma migração ou um release antes de aplicá-lo em produção,
sem tocar no schema `plat` que já serve tráfego real (`plat-api` :8150, `plat-worker`, ambos vivos e
com uso real medido durante este item). A hipótese registrada em `laco/estado.json` (L7-31) descrevia
um banco Postgres SEPARADO (`CREATE DATABASE plat_homolog`). O pedido que abriu este turno mudou a
decisão explicitamente: **schema `plat_homolog` no MESMO Postgres, nunca um banco novo** — `/` está a
98% de disco e `/mnt/pgdata` a 99% (medido no início deste item), e mesmo o overhead pequeno de um
banco novo (catálogo do Postgres, WAL próprio) não vale o risco numa máquina nesse estado.

## Decisão

1. **Um schema por ambiente, no banco `iagro_sat` de sempre.** Produção continua em `plat`/
   `plat_trabalho`; homologação vive em `plat_homolog`/`plat_trabalho_homolog`. Papéis, canal de
   notificação e schema seguem a MESMA convenção de nome (`app/settings.py`: o papel do worker é
   sempre `{PLAT_SCHEMA}_worker`), então não existe uma lista de exceções para manter sincronizada.

2. **As migrações são as MESMAS, reescritas em voo.** `db/migracoes/*.sql` continuam sendo a única
   fonte de verdade (o mesmo arquivo que roda em produção). `db/reescrever_homolog.py` troca token a
   token — `plat`→`plat_homolog`, `plat_trabalho`→`plat_trabalho_homolog`, papel `plat_app`→
   `plat_homolog_app`, papel/canal `plat_worker`→`plat_homolog_worker`, canal `plat_job`→
   `plat_homolog_job` — sem nunca escrever um arquivo novo em disco (lê, transforma em memória,
   manda para o psql por stdin). `db/migrar_homolog.sh` é uma cópia deliberada de `db/migrar.sh` com
   esse passo a mais e o controle de versão próprio (`plat_homolog.versao_migracao`, nunca
   `plat.versao_migracao`) — nenhuma migração é "pulada"; nenhuma conta como aplicada nos dois lados
   por engano, porque os textos comparados (sha256) já saem diferentes da transformação.

3. **O app troca de schema por variável de ambiente, não por código duplicado.** O hardcode `plat.`
   está espalhado em dezenas de rotas (`auth/`, `acervo/`, `catalogo/`, `jobs/`) e cresce a cada item;
   reescrever cada rota para ler um schema de `settings` teria sido um refactor grande e arriscado
   bem no meio de outras trilhas mexendo nos mesmos arquivos. Em vez disso, `app/schema_ambiente.py`
   troca o TEXTO da consulta antes de mandar para o driver: um `CursorSchemaAmbiente` (subclasse de
   `psycopg2.extras.RealDictCursor`) que reescreve `plat.`/`plat_trabalho.` para
   `settings.PLAT_SCHEMA`/`PLAT_SCHEMA_TRABALHO` quando esses diferem do padrão. Plugado nos dois
   únicos pontos onde uma conexão nasce (`app/db.py`, `app/jobs/worker.py`); toda consulta da API,
   dos jobs (mesmo o processo filho, que herda por fork) e do relógio de agendas passa por um dos
   dois. Em produção (`PLAT_SCHEMA == "plat"`) a função devolve a mesma string sem rodar a regex —
   custo zero, testado com `settings.producao` continuando a valer para o cookie `Secure` etc.

4. **GUC customizado não é schema e fica de fora.** `current_setting('plat.tenant_id', ...)` e as
   ~9 chaves do mesmo padrão (`usuario_id`, `via_worker`, `lixeira`, `link_itens`, `transferencia`,
   `superadmin`, `versao_comentario`, `versao_rotulo`, `login`) são configuração de SESSÃO do
   Postgres, não um objeto dentro de um schema — o app usa o literal fixo nesses pontos em qualquer
   ambiente. A regex de `reescrever_schema` exclui por contexto (`current_setting('`/`set_config('`
   imediatamente antes de `plat`), não por uma lista de nomes — conferido 1 a 1 contra as 17
   ocorrências reais da árvore (16 `current_setting`, 12 `set_config`, um menos porque uma linha
   soma os dois).

5. **NOTIFY/LISTEN e advisory lock são globais ao banco, não ao schema — tratados à parte.**
   `pg_notify('plat_job', ...)`/`LISTEN plat_job` e o equivalente para `plat_worker` são um canal por
   BANCO (não por schema); sem renomear, um job de homologação acordaria o SSE e o worker de
   PRODUÇÃO (medido no primeiro turno, antes da correção: o filtro por `tenant_id` no SSE não evita a
   notificação chegar, só evita render errado). `PLAT_CANAL_JOB`/`PLAT_CANAL_WORKER` resolvem isso do
   lado do app; o mesmo token nas migrações resolve do lado do trigger. **Não resolvido**: o advisory
   lock do job pesado (`LOCK_PESADO = "plat.job.pesado"`, `app/jobs/worker.py`) é uma string fixa,
   também global ao banco — homologação e produção disputam a MESMA trava se um job pesado rodar dos
   dois lados ao mesmo tempo. `pg_try_advisory_lock` é não bloqueante (falha rápido, não trava
   ninguém), e a suíte de homologação não dispara `prova.pesado` por padrão — risco aceito e
   registrado aqui, não corrigido neste item (mexer na trava exigiria repetir a mesma convenção de
   nome nela, item pequeno mas fora do escopo combinado para este turno).

6. **nginx próprio na frente, senão a tela nunca fica pronta.** A API nunca serviu `/static/`
   sozinha — isso é `location /static/` do nginx de produção, direto do disco. A primeira tentativa
   deste item subiu só o uvicorn (`:8154`) e qualquer teste de tela travou em
   `wait_for_selector("body[data-pronto='1']")` porque `login.js`/`style.css` voltavam 404 (achado
   real, não hipotético — está nos logs deste turno). `deploy/nginx_homolog.conf` é um site próprio
   (nunca edita `sites-available/plat.iagrointel.com`): nginx escuta em `127.0.0.1:8154` (loopback,
   sem certificado — nunca é exposto por DNS), serve `/static/` do disco e proxia o resto para o
   uvicorn interno em `127.0.0.1:8158`. `db/homolog_bootstrap.sh` escreve o site e só recarrega o
   nginx quando o conteúdo muda (idempotente; reload nunca derruba conexão existente, diferente de
   restart).

7. **Papel e senha próprios, gerados uma vez, guardados fora do repositório.**
   `plat_homolog_app`/`plat_homolog_worker` (criados pelas próprias migrações reescritas) recebem
   senha aleatória na primeira vez que `db/homolog_bootstrap.sh` roda; a senha e o `PLAT_SECRET` de
   homologação ficam em `var/homolog/segredos.env` (0600, fora do `.gitignore` por estar sob `var/`,
   que já é ignorado inteiro). `pg_hba.conf` ganha uma linha por papel (idempotente) — sem ela o
   Postgres aceita a migração mas recusa toda conexão do app (armadilha já registrada no
   `CLAUDE.md`).

## Alternativas descartadas

- **Banco novo (`CREATE DATABASE`)**: era a hipótese original do backlog; descartada pelo pedido
  explícito que abriu este item (disco a 98-99%).
- **Reescrever as rotas para ler o schema de `settings` uma a uma**: mais "correto" no papel, mas um
  refactor de dezenas de arquivos, em paralelo com outras trilhas mexendo nos MESMOS arquivos no
  mesmo turno — risco de colisão e de regressão maior do que o ganho.
- **Rodar só a suíte rápida (sem e2e/playwright) contra o schema de homologação**: não provaria o
  requisito do item ("roda a suíte de e2e... isoladamente"); a suíte completa foi rodada de verdade
  (ver `docs/HOMOLOGACAO.md` §5 e `tests/medidas/L7-31-homologacao.json`).

## Consequências

- Toda migração nova continua sendo escrita uma vez só, em `db/migracoes/`; `make homolog` é o passo
  que qualquer trilha roda antes de aplicar algo arriscado em produção.
- O app ganhou 4 chaves de configuração novas (`PLAT_SCHEMA`, `PLAT_SCHEMA_TRABALHO`,
  `PLAT_CANAL_JOB`, `PLAT_CANAL_WORKER`) que produção nunca declara (o padrão reproduz o
  comportamento de sempre, bit a bit).
- Risco aceito e nomeado: o advisory lock do job pesado é compartilhado entre os dois ambientes
  (item 5 acima); se algum dia isso incomodar de verdade, a correção é a mesma convenção de nome
  aplicada a `LOCK_PESADO`.
