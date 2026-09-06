#!/bin/bash
# Cria (idempotente) uma base de teste PRÓPRIA para uma trilha/worktree, para que várias trilhas
# rodem pytest AO MESMO TEMPO sem o flock global e sem tocar no schema `plat` de produção.
# Reusa a máquina do ambiente de homologação do produto (item L7-31), só que parametrizada.
# Uso: bash trilha_ambiente.sh <nome-da-trilha>        (ex.: amc, stac, garage, valida)
set -euo pipefail
T=${1:?uso: trilha_ambiente.sh <nome>}
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
APP="${SCHEMA}_app"; WORKER="${SCHEMA}_worker"; CANAL="${SCHEMA}_job"
VAR="$LACO/var/trilha"; mkdir -p "$VAR"; chmod 700 "$VAR"
ENVF="$VAR/$T.env"; SEG="$VAR/$T.segredos"
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)

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
  sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1 -1 -f - < "$tmp" >/dev/null
  dur=$(( $(date +%s%3N) - ini ))
  "${PSQL[@]}" -c "INSERT INTO $SCHEMA.versao_migracao(nome,sha256,duracao_ms) VALUES('$nome','$sha',$dur)" >/dev/null
  echo "  + $nome (${dur} ms)"; rm -f "$tmp"
done

echo "== b. papéis $APP / $WORKER (senha gerada uma vez)"
if [ -f "$SEG" ]; then . "$SEG"; else
  SENHA_APP=$(openssl rand -hex 24); SENHA_WORKER=$(openssl rand -hex 24)
  printf 'SENHA_APP=%s\nSENHA_WORKER=%s\n' "$SENHA_APP" "$SENHA_WORKER" > "$SEG"; chmod 600 "$SEG"
fi
"${PSQL[@]}" -c "ALTER ROLE $APP PASSWORD '$SENHA_APP'" >/dev/null
"${PSQL[@]}" -c "ALTER ROLE $WORKER PASSWORD '$SENHA_WORKER'" >/dev/null

echo "== c. pg_hba.conf (idempotente; reload só se mudou — nunca restart)"
MUDOU=0
for papel in "$APP" "$WORKER"; do
  linha="host    $DB    $papel    127.0.0.1/32    scram-sha-256"
  sudo grep -qF "$papel" "$PG_HBA" || { echo "$linha" | sudo tee -a "$PG_HBA" >/dev/null; MUDOU=1; }
done
[ $MUDOU = 1 ] && sudo systemctl reload postgresql && echo "  pg_hba atualizado (reload)" || echo "  pg_hba já tinha as linhas"

echo "== c2. privilégio nos schemas de dado d_<slug> (achado 06/09)"
# O produto grava camada em `d_<slug>` derivado do APELIDO do inquilino, sem prefixo de ambiente:
# produção, homologação e todas as trilhas partilham `d_demo`. Enquanto o produto não separar isso
# (item de recurso partilhado, em conserto), a trilha precisa de privilégio nos schemas que já
# existem, senão QUALQUER teste que crie camada morre com `permission denied for schema d_demo`.
for d in $("${PSQL[@]}" -Atc "select nspname from pg_namespace where nspname like 'd\_%'"); do
  "${PSQL[@]}" -c "GRANT USAGE, CREATE ON SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1
  "${PSQL[@]}" -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA \"$d\" TO $APP, $WORKER" >/dev/null 2>&1
done
echo "  privilégio dado nos schemas de dado existentes"

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
DELETE FROM $SCHEMA.usuario WHERE login LIKE 'zt%';
SQL
echo "  admins de plataforma/demo/demo2 semeados"

echo "== e. $ENVF"
TOKEN_GARAGE=$(grep -m1 '^PLAT_GARAGE_ADMIN_TOKEN=' "$REPO/.env" | cut -d= -f2-)
SEGREDO=$(sudo cat /etc/plat/segredos/PLAT_SECRET)
cat > "$ENVF" <<ENV
PLAT_DSN=postgresql://$APP:${SENHA_APP}@127.0.0.1:5432/${DB}
PLAT_DSN_WORKER=postgresql://$WORKER:${SENHA_WORKER}@127.0.0.1:5432/${DB}
PLAT_SECRET=${SEGREDO}
PLAT_AMBIENTE=dev
PLAT_SEMENTE_DEMO=sim
PLAT_URL_PUBLICA=https://trilha-$T.invalido
PLAT_SCHEMA=$SCHEMA
PLAT_SCHEMA_TRABALHO=$SCHEMA_TRAB
PLAT_CANAL_JOB=$CANAL
PLAT_CANAL_WORKER=$WORKER
PLAT_GARAGE_URL=http://127.0.0.1:3900
PLAT_GARAGE_ADMIN_URL=http://127.0.0.1:3903
PLAT_GARAGE_ADMIN_TOKEN=${TOKEN_GARAGE}
PLAT_GARAGE_REGIAO=garage
PLAT_GARAGE_BUCKET_PREFIXO=t$T-plat-
PLAT_LOG_NIVEL=INFO
PLAT_WORKER_NOME=trilha-$T
PLAT_WORKER_PROCESSOS=1
PLAT_WORKER_MEMORIA_MB=1024
PLAT_POOL_MIN=1
PLAT_POOL_MAX=2
PLAT_CREDENCIAIS_ARQUIVO=$VAR/$T.credenciais.txt
PLAT_CREDENCIAIS_TOTP_ARQUIVO=$VAR/$T.credenciais_totp.txt
ENV
chmod 600 "$ENVF"
echo
echo "pronto. Nesta trilha, rode a suíte SEM flock:"
echo "  set -a; source $ENVF; set +a; venv/bin/pytest tests/unit tests/api -q"
echo "refazer do zero:  sudo -u postgres psql -d $DB -c 'DROP SCHEMA $SCHEMA CASCADE; DROP SCHEMA $SCHEMA_TRAB CASCADE' && rm -f $ENVF"
