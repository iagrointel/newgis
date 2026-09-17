#!/bin/bash
# Cria (idempotente) uma base de teste PRÓPRIA para uma trilha/worktree, para que várias trilhas
# rodem pytest AO MESMO TEMPO sem o flock global e sem tocar no schema `plat` de produção.
# Reusa a máquina do ambiente de homologação do produto (item L7-31), só que parametrizada.
# Uso: bash trilha_ambiente.sh <nome-da-trilha>        (ex.: amc, stac, garage, valida)
set -euo pipefail
# 08/09 01:05: construções de trilha em paralelo (12 agentes + fila) disputam o ACL dos schemas de dado partilhados
# (`GRANT USAGE ON SCHEMA d_demo` dentro das migrações reescritas) e o Postgres responde "tuple concurrently
# updated", derrubando a base inteira — a fila abortou 2 lotes seguidos assim. Uma construção por vez na máquina
# (trinco de arquivo; cada uma leva 1-2 min). Quem espera mais de 30 min recebe erro e o motivo.
# 08/09 02:40: o trinco passou a valer só por MIGRAÇÃO (abaixo), não pelo script inteiro — 12 construções esperavam
# 30 min. Cada psql de migração roda sob o trinco (nunca duas migrações ao mesmo tempo em builds diferentes) e
# repete até 3× se colidir com um GRANT de outro build ("tuple concurrently updated").
T=${1:?uso: trilha_ambiente.sh <nome>}
# 08/09 06:30: duas invocações para a MESMA trilha ao mesmo tempo (laço de repetição de um líder + outra chamada)
# aplicavam a mesma migração duas vezes -> "duplicate key ... versao_migracao_pkey" em laço infinito. Uma
# construção por trilha de cada vez (trinco por nome); trilhas diferentes seguem em paralelo.
if [ "${TRILHA_MESMA:-0}" != "1" ]; then
  mkdir -p /home/dev/plataforma/laco/var/trilha
  exec flock -w 1800 "/home/dev/plataforma/laco/var/trilha/$T.lock" env TRILHA_MESMA=1 bash "$(readlink -f "$0")" "$@"
fi
REPO=/home/dev/plataforma/enterprise
# 06/09: as migrações vêm do WORKTREE da trilha quando ele existe (2º argumento, ou /home/dev/plataforma/wt/<nome>).
# Antes, vinham só da árvore principal; sem as próprias migrações na base isolada, os agentes recorriam
# ao db/migrar.sh de produção — foi a causa raiz das 6 migrações de ramo aplicadas em produção hoje.
FONTE=${2:-}
[ -z "$FONTE" ] && [ -d "/home/dev/plataforma/wt/$T" ] && FONTE="/home/dev/plataforma/wt/$T"
[ -z "$FONTE" ] && FONTE="$REPO"
[ -d "$FONTE/db/migracoes" ] || { echo "sem db/migracoes em $FONTE" >&2; exit 2; }
LACO=/home/dev/plataforma/laco
DB=${PLAT_DB:-iagro_sat}
PG_HBA=${PG_HBA:-/etc/postgresql/16/main/pg_hba.conf}
SCHEMA="plat_t$T"; SCHEMA_TRAB="plat_trabalho_t$T"
APP="${SCHEMA}_app"; WORKER="${SCHEMA}_worker"; CANAL="${SCHEMA}_job"; LEITOR="${SCHEMA}_leitor"
VAR="$LACO/var/trilha"; mkdir -p "$VAR"; chmod 700 "$VAR"
ENVF="$VAR/$T.env"; SEG="$VAR/$T.segredos"
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)

# == 0. extensões (lista única db/extensoes.txt, item L7-01-d) ==
# Terceiro leitor da mesma lista que o install.sh e o ensaio de restauração (app/backup/drill.py) usam.
# A base de trilha é um SCHEMA dentro do banco compartilhado, então na prática as extensões já existem;
# o que este trecho garante é que a trilha PARE nomeando a extensão que falta, em vez de a migração 045
# ou uma restauração falharem depois com "tabela ausente". Enquanto o ramo do L7-01-d não estiver em
# master, worktree antigo não tem os dois arquivos: nesse caso avisa e segue (o comportamento de antes).
EXT_SH=""; EXT_TXT=""
for raiz in "$FONTE" "$REPO"; do
  if [ -r "$raiz/db/extensoes.sh" ] && [ -r "$raiz/db/extensoes.txt" ]; then
    EXT_SH="$raiz/db/extensoes.sh"; EXT_TXT="$raiz/db/extensoes.txt"; break
  fi
done
if [ -n "$EXT_SH" ]; then
  echo "== 0. extensões ($EXT_TXT)"
  . "$EXT_SH"
  plat_extensoes_garantir "$EXT_TXT" "${PSQL[@]}"
else
  echo "== 0. extensões: db/extensoes.txt ausente em $FONTE e em $REPO (ramo do L7-01-d ainda não em master); seguindo sem conferir"
fi

echo "== a. migrações no schema $SCHEMA"
"${PSQL[@]}" -f - <<SQL
CREATE SCHEMA IF NOT EXISTS $SCHEMA AUTHORIZATION postgres;
CREATE TABLE IF NOT EXISTS $SCHEMA.versao_migracao (
  nome text PRIMARY KEY, sha256 text NOT NULL,
  aplicada_em timestamptz NOT NULL DEFAULT now(),
  duracao_ms int NOT NULL, aplicada_por text NOT NULL DEFAULT current_user);
SQL
# Ordem de aplicação com as DUAS famílias de nome (ADR 0014 do repositório): legado `NNN_slug.sql`
# (001 a 048, fechado) primeiro, depois carimbo de tempo `YYYYMMDDTHHMM_slug.sql` (+3 hex opcionais).
# Chave: prefixo "0" para o legado e "1" para o carimbo, depois o nome.
listar_migracoes() {
  local d=$1 f
  { for f in "$d"/[0-9][0-9][0-9]_*.sql; do [ -e "$f" ] && printf '0\t%s\n' "$f"; done
    for f in "$d"/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9]*_*.sql; do [ -e "$f" ] && printf '1\t%s\n' "$f"; done
  } | LC_ALL=C sort -t "$(printf '\t')" -k1,1 -k2,2 | cut -f2
}

shopt -s nullglob
mapfile -t ARQS_MIG < <(listar_migracoes "$FONTE/db/migracoes")
for arq in "${ARQS_MIG[@]}"; do
  nome=$(basename "$arq" .sql); tmp=$(mktemp)
  TRILHA=$T "$LACO/trilha_reescrever.py" "$arq" > "$tmp"
  sha=$(sha256sum "$tmp" | cut -d' ' -f1)
  atual=$("${PSQL[@]}" -Atc "SELECT sha256 FROM $SCHEMA.versao_migracao WHERE nome='$nome'")
  if [ "$atual" = "$sha" ]; then rm -f "$tmp"; continue; fi
  if [ -n "$atual" ]; then echo "  ! $nome mudou desde a última aplicação — recrie a trilha (ver secão 'refazer')"; rm -f "$tmp"; continue; fi
  ini=$(date +%s%3N)
  for tent in 1 2 3 4 5 6; do
    # TRILHA_TRAVADA=1 = processo antigo que já entrou sob o trinco do script inteiro: um 2º flock no mesmo arquivo travaria
    if [ "${TRILHA_TRAVADA:-0}" = "1" ]; then TRINCO=(); else TRINCO=(flock -w 1800 "$LACO/.trilha_build.lock"); fi
    if err=$("${TRINCO[@]}" sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1 -1 -f - < "$tmp" 2>&1 >/dev/null); then break; fi
    if echo "$err" | grep -q "tuple concurrently updated" && [ "$tent" -lt 6 ]; then sleep $((tent*3)); continue; fi
    echo "$err" >&2; echo "migração $nome falhou (tentativa $tent)" >&2; exit 1
  done
  dur=$(( $(date +%s%3N) - ini ))
  "${PSQL[@]}" -c "INSERT INTO $SCHEMA.versao_migracao(nome,sha256,duracao_ms) VALUES('$nome','$sha',$dur) ON CONFLICT (nome) DO NOTHING" >/dev/null
  echo "  + $nome (${dur} ms)"; rm -f "$tmp"
done

echo "== b. papéis $APP / $WORKER (senha gerada uma vez)"
if [ -f "$SEG" ]; then . "$SEG"; else
  SENHA_APP=$(openssl rand -hex 24); SENHA_WORKER=$(openssl rand -hex 24)
  printf 'SENHA_APP=%s\nSENHA_WORKER=%s\n' "$SENHA_APP" "$SENHA_WORKER" > "$SEG"; chmod 600 "$SEG"
fi
# 07/09 21:30: papel só-leitura da trilha (Martin/tiles, PLAT_DSN_LEITOR) — faltava e 5 testes de tile reprovavam
if [ -z "${SENHA_LEITOR:-}" ]; then SENHA_LEITOR=$(openssl rand -hex 24); printf 'SENHA_LEITOR=%s\n' "$SENHA_LEITOR" >> "$SEG"; fi
"${PSQL[@]}" -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$LEITOR') THEN CREATE ROLE $LEITOR LOGIN; END IF; END \$\$" >/dev/null
"${PSQL[@]}" -c "ALTER ROLE $LEITOR PASSWORD '$SENHA_LEITOR'" >/dev/null
"${PSQL[@]}" -c "ALTER ROLE $APP PASSWORD '$SENHA_APP'" >/dev/null
"${PSQL[@]}" -c "ALTER ROLE $WORKER PASSWORD '$SENHA_WORKER'" >/dev/null

echo "== c. pg_hba.conf (idempotente; reload só se mudou — nunca restart)"
MUDOU=0
for papel in "$APP" "$WORKER" "$LEITOR"; do
  linha="host    $DB    $papel    127.0.0.1/32    scram-sha-256"
  sudo grep -qF "$papel" "$PG_HBA" || { echo "$linha" | sudo tee -a "$PG_HBA" >/dev/null; MUDOU=1; }
done
[ $MUDOU = 1 ] && sudo systemctl reload postgresql && echo "  pg_hba atualizado (reload)" || echo "  pg_hba já tinha as linhas"

echo "== c2. privilégio nos schemas de dado d_<slug> (achado 06/09; isolado desde 07/09)"
# O produto gravava camada em `d_<slug>`, derivado só do APELIDO do inquilino: produção, homologação e
# todas as trilhas partilhavam `d_demo` (achado F8 do adversário, 07/09 — 79 tabelas em d_demo, 65 de
# sete trilhas). O conserto (migração *_isolamento_schema_de_dado.sql + plat.camada_schema_prefixo)
# põe a instalação no prefixo: a trilha grava em `d_plat_t<T>_<slug>`, criado pela própria migração,
# com dono `plat_t<T>_app`. Quando o worktree TEM o conserto, a trilha NÃO recebe mais privilégio nos
# schemas de dado de produção — é isso que a torna incapaz de ler ou apagar camada de produção.
# Enquanto houver worktree sem o conserto (código de master antigo), ele continua ganhando o
# privilégio antigo, senão qualquer teste que crie camada morre com `permission denied`.
if grep -rqs "camada_schema_prefixo" "$FONTE/db/migracoes"; then
  echo "  worktree com o isolamento de schema de dado: nenhum privilégio em d_ de produção"
  # 07/09 18:40: os papéis plat_t<T>_app/_worker SOBREVIVEM ao DROP SCHEMA da trilha; um GRANT dado por uma
  # rodada antiga (worktree sem o isolamento) ficava colado no papel e o teste de isolamento reprovava
  # ("plat_tintegra_app tem USAGE em d_demo"). Revoga em todo d_* de produção antes de conceder no prefixo.
  # só os schemas de dado REAIS (inquilinos semeados); os 1.200+ `d_zt-inq-*` são resto de inquilino de teste
  for d in $("${PSQL[@]}" -Atc "select nspname from pg_namespace where nspname like 'd\_%' and nspname not like 'd\_plat\_t%' and nspname not like 'd\_zt%'"); do
    "${PSQL[@]}" -c "REVOKE ALL ON SCHEMA \"$d\" FROM $APP, $WORKER" >/dev/null 2>&1 || true
    "${PSQL[@]}" -c "REVOKE ALL ON ALL TABLES IN SCHEMA \"$d\" FROM $APP, $WORKER" >/dev/null 2>&1 || true
  done
  for d in $("${PSQL[@]}" -Atc "select nspname from pg_namespace where nspname like 'd\_plat\_t${T}\_%'"); do
    "${PSQL[@]}" -c "GRANT USAGE, CREATE ON SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1 || true
    "${PSQL[@]}" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1 || true
    # 07/09 (achado do L2-06-a): tabela criada no d_<slug> DEPOIS de a trilha subir nascia sem privilégio;
    # privilégio padrão vale para o que o dono do schema criar daqui em diante (mesma classe das partições)
    for dono in postgres plat_app "$APP"; do
      "${PSQL[@]}" -c "ALTER DEFAULT PRIVILEGES FOR ROLE $dono IN SCHEMA \"$d\" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP, $WORKER" >/dev/null 2>&1 || true
    done
  done
else
  # 08/09 02:00: os 1.000+ `d_zt*` (inquilinos de teste que a suíte cria e não apaga) faziam este laço levar minutos
  # por construção (2 psql por schema) e engarrafavam o trinco de construção; só os schemas reais entram.
  for d in $("${PSQL[@]}" -Atc "select nspname from pg_namespace where nspname like 'd\_%' and nspname not like 'd\_zt%'"); do
    # `|| true` + 2 tentativas: GRANT em schema compartilhado dá `tuple concurrently updated` quando outra
    # trilha faz DDL no mesmo instante (set -e derrubava a criação da trilha inteira por isso)
    # 08/09 12:00: 2 tentativas de 1 s não bastavam — a trilha da FILA ficou sem USAGE em d_demo e 41 testes
    # caíram com "permission denied for schema d_demo" (lote inteiro vermelho, culpado falso). Agora 8 tentativas
    # com espera crescente e, para d_demo, conferência explícita no fim (abaixo).
    for tent in 1 2 3 4 5 6 7 8; do "${PSQL[@]}" -c "GRANT USAGE, CREATE ON SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1 && break; sleep $((tent*2)); done || true
    for tent in 1 2 3 4 5 6 7 8; do "${PSQL[@]}" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1 && break; sleep $((tent*2)); done || true
  done
  for tent in 1 2 3 4 5 6 7 8 9 10; do
    if [ "$("${PSQL[@]}" -Atc "select has_schema_privilege('$APP','d_demo','CREATE') and has_schema_privilege('$WORKER','d_demo','CREATE')")" = "t" ]; then break; fi
    "${PSQL[@]}" -c "GRANT USAGE, CREATE ON SCHEMA d_demo TO $APP, $WORKER" >/dev/null 2>&1 || true; sleep $((tent*3))
  done
  [ "$("${PSQL[@]}" -Atc "select has_schema_privilege('$APP','d_demo','CREATE')")" = "t" ] || { echo "ERRO: $APP sem CREATE em d_demo depois de 10 tentativas (contenção no ACL); base inválida" >&2; exit 1; }
  echo "  d_demo: USAGE+CREATE conferidos para $APP e $WORKER"
  echo "  privilégio dado nos schemas de dado existentes (worktree sem o isolamento)"
fi

echo "== c2b. privilégio nas tabelas que NASCEM depois (partições mensais) — achado 07/09"
# As migrações concedem privilégio nas tabelas que EXISTEM quando rodam. As partições mensais de
# `evento` e `log_acesso` (e mais duas tabelas) são criadas em tempo de execução, depois disso, e
# ficavam SEM privilégio nenhum. Efeito: qualquer rota que grave evento de auditoria devolvia 403
# "operação fora do inquilino da sessão" -- que é a tradução de um erro de PRIVILÉGIO do Postgres,
# não de uma checagem de inquilino. Isso deixou a suíte de master vermelha e a fila de junção
# reprovava TODO lote a noite inteira, com quinze itens prontos parados. Duas partes:
#   (1) alcance retroativo: concede no que já existe agora;
#   (2) privilégio padrão: vale para o que o dono do schema criar daqui em diante.
for tent in 1 2 3; do
  "${PSQL[@]}" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"$SCHEMA\" TO $APP, $WORKER" >/dev/null 2>&1 && break
  sleep 1
done || true
"${PSQL[@]}" -c "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA \"$SCHEMA\" TO $APP, $WORKER" >/dev/null 2>&1 || true
for dono in postgres "$APP"; do
  "${PSQL[@]}" -c "ALTER DEFAULT PRIVILEGES FOR ROLE $dono IN SCHEMA \"$SCHEMA\" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP, $WORKER" >/dev/null 2>&1 || true
  "${PSQL[@]}" -c "ALTER DEFAULT PRIVILEGES FOR ROLE $dono IN SCHEMA \"$SCHEMA\" GRANT USAGE, SELECT ON SEQUENCES TO $APP, $WORKER" >/dev/null 2>&1 || true
done
faltam=$("${PSQL[@]}" -Atc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relkind='r' and not exists (select 1 from information_schema.role_table_grants g where g.table_schema='$SCHEMA' and g.table_name=c.relname and g.grantee='$APP')" 2>/dev/null || echo '?')
echo "  privilégio conferido: $faltam tabela(s) ainda sem GRANT para $APP (esperado: 0)"

echo "== c2c. matriz de privilégio das tabelas = a de PRODUÇÃO (achado 07/09, refeito 07/09 noite)"
# O GRANT em massa do passo c2b concede em TODA tabela do schema e DESFAZ os REVOKE deliberados das
# migrações (item_versao da 011, privilegio/evento/log_acesso da 003, job da 006, worker da 004, ambiente
# da 014...). A 1ª correção reaplicava só as linhas REVOKE lidas das migrações — e deixava buraco no
# sentido oposto (plat.ambiente ficava SEM o GRANT SELECT que a 014 dá depois do REVOKE: "permission
# denied for table ambiente" nos testes de semente demo) e não fechava o do worker em plat.job.
# Agora a matriz não é adivinhada nem lida de texto: é COPIADA do schema `plat` de produção, tabela a
# tabela, com plat_app -> $APP e plat_worker -> $WORKER. Tabela que só existe neste worktree (migração
# nova do item) fica com o GRANT amplo do c2b — é o que o item vai ajustar na própria migração.
"${PSQL[@]}" -c "REVOKE ALL ON ALL TABLES IN SCHEMA \"$SCHEMA\" FROM $APP, $WORKER" >/dev/null 2>&1 || true
n_gr=0; n_novas=0
while IFS='|' read -r rel grantee privs; do
  [ -n "$rel" ] || continue
  case "$grantee" in plat_app) alvo=$APP;; plat_worker) alvo=$WORKER;; *) continue;; esac
  existe=$("${PSQL[@]}" -Atc "select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relname='$rel' and c.relkind in ('r','p','v','m')" 2>/dev/null)
  [ "$existe" = 1 ] || continue
  "${PSQL[@]}" -c "GRANT $privs ON \"$SCHEMA\".\"$rel\" TO $alvo" >/dev/null 2>&1 && n_gr=$((n_gr+1))
done < <("${PSQL[@]}" -Atc "select table_name, grantee, string_agg(privilege_type, ',') from information_schema.role_table_grants where table_schema='plat' and grantee in ('plat_app','plat_worker') group by 1,2 order by 1,2" 2>/dev/null)
# tabelas que não existem em produção (nascidas neste worktree): GRANT amplo, como antes
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  "${PSQL[@]}" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON \"$SCHEMA\".\"$rel\" TO $APP, $WORKER" >/dev/null 2>&1 && n_novas=$((n_novas+1))
done < <("${PSQL[@]}" -Atc "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relkind in ('r','p') and not exists (select 1 from pg_class c2 join pg_namespace n2 on n2.oid=c2.relnamespace where n2.nspname='plat' and c2.relname=c.relname)" 2>/dev/null)
echo "  matriz copiada de produção: $n_gr GRANT em tabelas existentes; $n_novas tabela(s) só deste worktree com GRANT amplo"

echo "== c2e. leitura para $LEITOR (schema da trilha + schemas de dado próprios)"
"${PSQL[@]}" -c "GRANT USAGE ON SCHEMA \"$SCHEMA\" TO $LEITOR; GRANT SELECT ON ALL TABLES IN SCHEMA \"$SCHEMA\" TO $LEITOR; GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA \"$SCHEMA\" TO $LEITOR" >/dev/null 2>&1 || true
for dono in postgres "$APP"; do "${PSQL[@]}" -c "ALTER DEFAULT PRIVILEGES FOR ROLE $dono IN SCHEMA \"$SCHEMA\" GRANT SELECT ON TABLES TO $LEITOR" >/dev/null 2>&1 || true; done
for d in $("${PSQL[@]}" -Atc "select nspname from pg_namespace where nspname like 'd\_plat\_t${T}\_%'"); do
  "${PSQL[@]}" -c "GRANT USAGE ON SCHEMA \"$d\" TO $LEITOR; GRANT SELECT ON ALL TABLES IN SCHEMA \"$d\" TO $LEITOR" >/dev/null 2>&1 || true
  for dono in postgres plat_app "$APP"; do "${PSQL[@]}" -c "ALTER DEFAULT PRIVILEGES FOR ROLE $dono IN SCHEMA \"$d\" GRANT SELECT ON TABLES TO $LEITOR" >/dev/null 2>&1 || true; done
done
# 08/09: o GRANT amplo acima é conveniência da trilha (o Martin lê qualquer tabela de camada), mas ele
# concede ao papel de leitura DUAS coisas que o modelo de segurança do produto nega de propósito: a tabela
# `segredo_leitor` (quem lê o segredo forja a prova de inquilino) e a função `prova_leitor` (devolve a prova
# de QUALQUER inquilino). Com o GRANT amplo, os testes adversários do item L2-04-a passam a falhar por causa
# do ambiente, não do código. O instalador do produto (db/leitor_instalar.sh) nunca concede as duas; a trilha
# volta atrás aqui para ficar igual a ele.
"${PSQL[@]}" -c "REVOKE ALL ON TABLE \"$SCHEMA\".segredo_leitor FROM $LEITOR" >/dev/null 2>&1 || true
# 08/09 (achado do L2-09-b): a migração do leitor recria/altera o papel como NOLOGIN depois de o script
# tê-lo criado com LOGIN; o Martin da trilha não conectava. LOGIN volta aqui, depois de todas as migrações.
"${PSQL[@]}" -c "ALTER ROLE $LEITOR LOGIN" >/dev/null 2>&1 || true
"${PSQL[@]}" -c "DO \$\$ DECLARE f text; BEGIN FOR f IN SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = '$SCHEMA' AND p.proname = 'prova_leitor' LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM $LEITOR', f); END LOOP; END \$\$" >/dev/null 2>&1 || true
echo "== c2c. PLAT_GIT_SHA da trilha (achado 07/09, 3 agentes tropeçaram)"
# num worktree o `.git` é um ARQUIVO apontador, não pasta; `app/versao.py::git_sha_curto()` lê `.git/HEAD`
# e quebra — os testes de /api/versao e o /saude da trilha caíam. Grava o sha resolvido no .env.
if [ -n "${FONTE:-}" ] && [ -d "$FONTE" ]; then
  SHA_WT=$(git -C "$FONTE" rev-parse HEAD 2>/dev/null || true)
  [ -n "$SHA_WT" ] && { grep -q "^PLAT_GIT_SHA=" "$ENVF" 2>/dev/null && sed -i "s/^PLAT_GIT_SHA=.*/PLAT_GIT_SHA=$SHA_WT/" "$ENVF" || echo "PLAT_GIT_SHA=$SHA_WT" >> "$ENVF"; echo "  PLAT_GIT_SHA=${SHA_WT:0:12}"; }
fi

echo "== c2d. dependências Node versionadas por package-lock (node_modules não vai no git; achado 07/09)"
if [ -n "${FONTE:-}" ] && [ -d "$FONTE" ]; then
  for pk in $(cd "$FONTE" && ls */*/package-lock.json */package-lock.json 2>/dev/null); do
    d=$(dirname "$pk"); [ -d "$FONTE/$d/node_modules" ] && continue
    (cd "$FONTE/$d" && npm ci --no-audit --no-fund --silent --prefer-offline >/dev/null 2>&1 || npm install --no-audit --no-fund --silent --prefer-offline >/dev/null 2>&1) \
      && echo "  npm: $d instalado" || echo "  npm: $d FALHOU (validador de estilo pode devolver 503)"
  done
fi

echo "== c3. privilégio de leitura no schema certaja (ativo da casa, só leitura, item L4-01-b)"
# tests/dados/carga_bdgd.py carrega a rede REAL da cooperativa de teste (certaja.ssdmt/ssdbt/ramlig/
# trafo/ponnot) para medir a topologia derivada em escala; sem USAGE+SELECT o teste morre com
# `permission denied for schema certaja` (achado 06/09 ao medir o item L4-01-b-topologia-derivada).
if "${PSQL[@]}" -Atc "select 1 from pg_namespace where nspname='certaja'" | grep -q 1; then
  "${PSQL[@]}" -c "GRANT USAGE ON SCHEMA certaja TO $APP" >/dev/null 2>&1 || true
  "${PSQL[@]}" -c "GRANT SELECT ON ALL TABLES IN SCHEMA certaja TO $APP" >/dev/null 2>&1 || true
  echo "  privilégio de leitura dado em certaja.*"
fi
# 07/09 noite: o acervo (registro único, schema `acervo` do servidor principal) é lido pela tela do acervo e pelos
# sincronizadores (scripts/acervo_*_sync.py) — na base por trilha o papel não tinha USAGE e a suíte de master
# reprovava test_acervo_camada/test_acervo_licenca com 0 linhas. Só leitura, como em produção.
if "${PSQL[@]}" -Atc "select 1 from pg_namespace where nspname='acervo'" | grep -q 1; then
  "${PSQL[@]}" -c "GRANT USAGE ON SCHEMA acervo TO $APP, $WORKER" >/dev/null 2>&1 || true
  "${PSQL[@]}" -c "GRANT SELECT ON ALL TABLES IN SCHEMA acervo TO $APP, $WORKER" >/dev/null 2>&1 || true
  echo "  privilégio de leitura dado em acervo.*"
fi

# 08/09: o pgstac (schema global `pgstac`, item L1-01-a) era instalado só à mão. Sem ele, a trilha não tem
# linha `pgstac-migrate-*` em versao_migracao e os testes de catálogo de imagens reprovam por causa da base,
# não do código. O próprio db/pgstac_instalar.sh é idempotente e sai em 0 quando já está registrado.
if [ -r "$FONTE/db/pgstac_instalar.sh" ] && [ -x "$REPO/venv/bin/pypgstac" ]; then
  echo "== c2f. pgstac (schema global; registro da versão em $SCHEMA.versao_migracao)"
  if PLAT_DB="$DB" PLAT_SCHEMA="$SCHEMA" bash "$FONTE/db/pgstac_instalar.sh" 2>&1 | sed 's/^/  /'; then :; else
    echo "  aviso: pgstac_instalar.sh falhou; testes de catálogo de imagens vão acusar a falta" >&2
  fi
fi

echo "== d. ambiente de teste + admins semeados (nunca cópia de produção)"
"${PSQL[@]}" -c "UPDATE $SCHEMA.ambiente SET nome='dev', semear_demo=true WHERE unico" >/dev/null 2>&1 || true
CRED="$VAR/$T.credenciais.txt"
if [ ! -f "$CRED" ]; then
  printf 'plataforma admin %s\ndemo admin %s\ndemo2 admin %s\n' \
    "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" > "$CRED"
fi
chmod 600 "$CRED"
while read -r slug login senha; do
  [ -n "$slug" ] || continue
  HASH=$(cd "$REPO" && printf '%s' "$senha" | "$REPO/venv/bin/python" -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))")
  "${PSQL[@]}" -f - <<SQL >/dev/null
INSERT INTO $SCHEMA.usuario(tenant_id, login, nome, senha_hash, perfil, superadmin)
SELECT t.id, '$login', 'Administrador $slug (trilha $T)', '$HASH', 'admin', ('$slug' = 'plataforma')
FROM $SCHEMA.tenant t WHERE t.slug = '$slug'
ON CONFLICT (tenant_id, login) DO UPDATE SET senha_hash = EXCLUDED.senha_hash, ativo = true, superadmin = EXCLUDED.superadmin,
  trocar_senha = false, totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, codigos_recuperacao = NULL,
  bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL, desafio_2fa_hash = NULL, desafio_2fa_ate = NULL,
  perfil = 'admin', papel_id = NULL;
SQL
done < "$CRED"
"${PSQL[@]}" -Atc "UPDATE $SCHEMA.tenant SET config = config || '{\"cota_jobs_dia\": 100000}' WHERE slug IN ('demo','demo2') AND coalesce((config->>'cota_jobs_dia')::int,0) < 100000" >/dev/null
"${PSQL[@]}" -f - <<SQL >/dev/null
SELECT $SCHEMA.tenant_apagar_interno(id) FROM $SCHEMA.tenant WHERE slug LIKE 'zt-%';
-- 17/09/2026 (ensaio da união): a união levou de 16 para 59 as chaves estrangeiras que apontam para
-- `usuario` sem cascata, e o DELETE direto passou a parar em job/exportação de usuário de teste que vive
-- num inquilino não-zt. A função resolve as dependências antes (migração 20260917T2210).
SELECT $SCHEMA.usuario_apagar_por_login('zt%');
SQL
echo "  admins de plataforma/demo/demo2 semeados"

echo "== e. $ENVF"
# 16/09 (D26, item F2/garage2): a trilha NUNCA MAIS lê o cofre de produção (/etc/plat/segredos) nem o
# .env de produção para o token do Garage. Existe agora uma instância de Garage SEPARADA, só para
# teste/homologação (unidade plataforma-garage-trilhas.service, S3 :3910, admin :3913, dados em
# /mnt/pgdata/garage-trilhas/), com token de administração PRÓPRIO — quem tiver esse token administra
# só os buckets de trilha, nunca os de produção. O segredo fica em laco/var/garage-trilhas.segredos
# (umask 077, fora do repo), gerado uma vez com `openssl rand -hex 32` por esta mesma tarefa.
GARAGE_TRILHAS_SEG="$LACO/var/garage-trilhas.segredos"
TOKEN_GARAGE=$(grep -m1 '^PLAT_GARAGE_ADMIN_TOKEN=' "$GARAGE_TRILHAS_SEG" 2>/dev/null | cut -d= -f2- || true)
[ -z "$TOKEN_GARAGE" ] && echo "  ! $GARAGE_TRILHAS_SEG sem PLAT_GARAGE_ADMIN_TOKEN — trilha ficará SEM Garage (nunca usar o token de produção para compensar)" >&2
# 07/09 noite (adversário do L7-19, achado registrado como L7-31-a): a trilha NÃO precisa do PLAT_SECRET de
# produção — ele assinava sessão e token só dentro da própria trilha e acabava em texto plano em ~100 .env e no
# /proc de dezenas de processos do usuário dev. Cada trilha ganha um segredo aleatório próprio, guardado no
# mesmo cofre local dos papéis ($SEG, modo 600) para sobreviver a rebuild da base sem invalidar sessão.
if grep -q '^SEGREDO_TRILHA=' "$SEG" 2>/dev/null; then
  SEGREDO=$(grep -m1 '^SEGREDO_TRILHA=' "$SEG" | cut -d= -f2-)
else
  SEGREDO=$(openssl rand -hex 32); printf 'SEGREDO_TRILHA=%s\n' "$SEGREDO" >> "$SEG"; chmod 600 "$SEG"
fi
# O endereço público entra no CORPO do TileJSON e do WMTS: com `*.invalido` o QGIS e o ArcGIS Pro leem
# a capacidade e não recebem ladrilho nenhum. Quando a trilha JÁ tem um endereço de verdade, reconstruir
# não pode devolvê-la ao placeholder — aconteceu duas vezes (10/09 na trilha `lancamento`, 11/09 na
# `uniao`) e nas duas o serviço voltou a anunciar host inválido sem ninguém notar.
# ⚠ Um drop-in de systemd com `Environment=` NÃO resolve: o `EnvironmentFile=` desta trilha vence
# (medido em 11/09). O valor tem de ficar certo AQUI.
URL_ANTERIOR=""
if [ -f "$ENVF" ]; then
  URL_ANTERIOR=$(sed -n 's/^PLAT_URL_PUBLICA=//p' "$ENVF" | head -1)
  case "$URL_ANTERIOR" in *.invalido) URL_ANTERIOR="";; esac
fi
URL_PUBLICA="${URL_ANTERIOR:-https://trilha-$T.invalido}"
[ -n "$URL_ANTERIOR" ] && echo "  mantendo PLAT_URL_PUBLICA=$URL_ANTERIOR (já publicada)"
cat > "$ENVF" <<ENV
PLAT_DSN=postgresql://$APP:${SENHA_APP}@127.0.0.1:5432/${DB}
PLAT_DSN_WORKER=postgresql://$WORKER:${SENHA_WORKER}@127.0.0.1:5432/${DB}
PLAT_DSN_LEITOR=postgresql://$LEITOR:${SENHA_LEITOR}@127.0.0.1:5432/${DB}
PLAT_SECRET=${SEGREDO}
PLAT_AMBIENTE=dev
PLAT_SEMENTE_DEMO=sim
PLAT_URL_PUBLICA=$URL_PUBLICA
PLAT_SCHEMA=$SCHEMA
PLAT_SCHEMA_TRABALHO=$SCHEMA_TRAB
PLAT_CANAL_JOB=$CANAL
PLAT_CANAL_WORKER=$WORKER
PLAT_GARAGE_URL=http://127.0.0.1:3910
PLAT_GARAGE_ADMIN_URL=http://127.0.0.1:3913
PLAT_GARAGE_ADMIN_TOKEN=${TOKEN_GARAGE}
PLAT_GARAGE_REGIAO=garage
PLAT_GARAGE_BUCKET_PREFIXO=t$T-plat-
PLAT_LOG_NIVEL=INFO
PLAT_WORKER_NOME=trilha-$T
PLAT_WORKER_PROCESSOS=1
PLAT_WORKER_MEMORIA_MB=1024
PLAT_POOL_MIN=1
PLAT_POOL_MAX=4
PLAT_CREDENCIAIS_ARQUIVO=$VAR/$T.credenciais.txt
PLAT_CREDENCIAIS_TOTP_ARQUIVO=$VAR/$T.credenciais_totp.txt
ENV
chmod 600 "$ENVF"
# 07/09 noite (achado do agente do L6-02-o): o passo c2c gravava PLAT_GIT_SHA e este `cat >` recriava o arquivo
# sem a linha — o worker morria no arranque em qualquer worktree (.git é arquivo, não diretório). Regrava aqui.
[ -n "${SHA_WT:-}" ] && echo "PLAT_GIT_SHA=$SHA_WT" >> "$ENVF" && echo "  PLAT_GIT_SHA regravado no env final"
# 16/09 (achado GET /saude): trilha_systemd.sh só injeta PLAT_MARTIN_URL/PLAT_WORKER_URL via Environment=
# das unidades (api/worker/martin) — nunca chega neste .env, que é o que a suíte de teste sourcia
# (roda_teste.sh; TestClient em processo, sem systemd). Medido: /saude no processo de teste devolvia
# servicos.worker=servicos.martin="ausente" com as duas unidades vivas e respondendo "ok" pela API real
# (:8192). Igual PLAT_URL_PUBLICA acima: o valor tem de ficar certo AQUI, não só no Environment= da
# unidade. Lido de $T.portas.env, que trilha_systemd.sh já grava (idempotente; ausente até a trilha
# ganhar unidades systemd — nesse caso nem martin nem worker respondem HTTP mesmo, "ausente" segue
# honesto). Titiler de propósito NÃO entra: não é uma unidade por trilha (compartilhado/externo).
if [ -f "$VAR/$T.portas.env" ]; then
  (
    . "$VAR/$T.portas.env"
    [ -n "${PLAT_TRILHA_PORTA_MARTIN:-}" ] && echo "PLAT_MARTIN_URL=http://127.0.0.1:${PLAT_TRILHA_PORTA_MARTIN}"
    [ -n "${PLAT_TRILHA_PORTA_WORKER:-}" ] && echo "PLAT_WORKER_URL=http://127.0.0.1:${PLAT_TRILHA_PORTA_WORKER}"
  ) >> "$ENVF"
  echo "  PLAT_MARTIN_URL/PLAT_WORKER_URL alinhados com $T.portas.env"
fi
echo
echo "pronto. Nesta trilha, rode a suíte SEM flock:"
echo "  set -a; source $ENVF; set +a; venv/bin/pytest tests/unit tests/api -q"
echo "refazer do zero:  sudo -u postgres psql -d $DB -c 'DROP SCHEMA $SCHEMA CASCADE; DROP SCHEMA $SCHEMA_TRAB CASCADE' && rm -f $ENVF"
