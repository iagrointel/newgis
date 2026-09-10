#!/usr/bin/env bash
# Prepara o ambiente de HOMOLOGAÇÃO (item L7-31; docs/HOMOLOGACAO.md) no MESMO Postgres/banco iagro_sat
# de produção (nunca um banco novo — disco a 98%): aplica as migrações no schema plat_homolog (via
# db/migrar_homolog.sh), garante os papéis plat_homolog_app/plat_homolog_worker com senha própria,
# garante a linha correspondente no pg_hba.conf (idempotente; recarrega o postgres só quando muda —
# reload nunca derruba conexão existente, diferente de restart), marca plat_homolog.ambiente como
# 'dev'/semear_demo=true (a mesma marca que install.sh grava para plat.ambiente em instalação de
# desenvolvimento) e escreve var/homolog/homolog.env com tudo que o Makefile precisa para subir a API
# e o worker temporários. NUNCA toca em plat_app/plat_worker/plat/pg_hba de produção, nunca reinicia
# plat-api/plat-worker. Idempotente: rodar de novo só reaplica o que mudou.
set -euo pipefail
DIR_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB=${PLAT_DB:-iagro_sat}
PG_HBA=${PG_HBA:-/etc/postgresql/16/main/pg_hba.conf}
VAR_HOMOLOG="$DIR_REPO/var/homolog"
SEGREDOS="$VAR_HOMOLOG/segredos.env"
ENV_HOMOLOG="$VAR_HOMOLOG/homolog.env"
PORTA_EXTERNA=${PLAT_HOMOLOG_PORTA:-8154}   # o que a suíte de e2e chama de "a API de homologação"
PORTA_INTERNA=${PLAT_HOMOLOG_PORTA_INTERNA:-8158}  # uvicorn de verdade; só o nginx acima fala com ela
[ "$(id -u)" -eq 0 ] && { echo "não rode como root: o dono dos arquivos de var/ é o usuário da app" >&2; exit 1; }
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)
mkdir -p "$VAR_HOMOLOG"

echo "== a. migrações (schema plat_homolog)"
bash "$DIR_REPO/db/migrar_homolog.sh"

echo "== b. papéis e senhas (plat_homolog_app, plat_homolog_worker) — gerada uma vez, reusada depois"
if [ ! -f "$SEGREDOS" ]; then
  {
    echo "SENHA_APP=$(openssl rand -hex 16)"
    echo "SENHA_WORKER=$(openssl rand -hex 16)"
    echo "PLAT_SECRET=$(openssl rand -hex 32)"
  } > "$SEGREDOS"
  chmod 600 "$SEGREDOS"
  echo "novos segredos gerados em $SEGREDOS"
else
  echo "reusando segredos existentes de $SEGREDOS"
fi
# shellcheck disable=SC1090
source "$SEGREDOS"
"${PSQL[@]}" -v senha_app="'$SENHA_APP'" -v senha_worker="'$SENHA_WORKER'" -f - <<'SQL'
ALTER ROLE plat_homolog_app PASSWORD :senha_app;
ALTER ROLE plat_homolog_worker PASSWORD :senha_worker;
SQL

echo "== c. pg_hba.conf (idempotente; só recarrega se mudou algo)"
MUDOU=0
for papel in plat_homolog_app plat_homolog_worker; do
  if ! sudo grep -qE "^\s*host\s+$DB\s+$papel\s" "$PG_HBA"; then
    printf 'host    %s       %s        127.0.0.1/32            scram-sha-256\n' "$DB" "$papel" | sudo tee -a "$PG_HBA" >/dev/null
    echo "linha adicionada: $papel"
    MUDOU=1
  else
    echo "linha já existia: $papel"
  fi
done
if [ "$MUDOU" = 1 ]; then
  sudo systemctl reload postgresql@16-main 2>/dev/null || sudo pg_ctlcluster 16 main reload
  echo "postgres recarregado (reload, não restart — conexões existentes intactas)"
fi

echo "== d. plat_homolog.ambiente = dev / semear_demo = true (só no schema homolog)"
"${PSQL[@]}" -c "UPDATE plat_homolog.ambiente SET nome = 'dev', semear_demo = true WHERE unico" >/dev/null

echo "== e. dado semeado de TESTE (nunca cópia de produção): admins de plataforma/demo/demo2"
# migração 002 já criou os inquilinos 'demo'/'demo2' (e a 004, 'plataforma'); falta o usuário admin de
# cada um, com senha PRÓPRIA do homolog — mesmo mecanismo do install.sh (seção g), reescrito aqui só
# trocando plat-> plat_homolog e o arquivo de saída (nunca tests/credenciais.txt, que é de produção).
CRED_HOMOLOG="$DIR_REPO/tests/credenciais_homolog.txt"
if [ ! -f "$CRED_HOMOLOG" ]; then
  printf 'plataforma admin %s\ndemo admin %s\ndemo2 admin %s\n' \
    "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" > "$CRED_HOMOLOG"
  echo "$CRED_HOMOLOG criado"
fi
chmod 600 "$CRED_HOMOLOG"
while read -r slug login senha; do
  [ -n "$slug" ] || continue
  HASH=$(printf '%s' "$senha" | "$DIR_REPO/venv/bin/python" -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))")
  "${PSQL[@]}" -f - <<SQL
INSERT INTO plat_homolog.usuario(tenant_id, login, nome, senha_hash, perfil, superadmin)
SELECT t.id, '$login', CASE WHEN '$slug' = 'plataforma' THEN 'Operador da plataforma (homolog)' ELSE 'Administrador $slug (homolog)' END,
       '$HASH', 'admin', ('$slug' = 'plataforma')
FROM plat_homolog.tenant t WHERE t.slug = '$slug'
ON CONFLICT (tenant_id, login) DO UPDATE SET senha_hash = EXCLUDED.senha_hash, ativo = true, superadmin = EXCLUDED.superadmin,
  trocar_senha = false, totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, codigos_recuperacao = NULL,
  bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL, desafio_2fa_hash = NULL, desafio_2fa_ate = NULL,
  perfil = 'admin', papel_id = NULL;
SQL
  echo "admin de $slug semeado (homolog)"
done < "$CRED_HOMOLOG"
# cota alta de jobs/dia para demo/demo2 (a suíte cria centenas por rodada; mesma linha do install.sh)
"${PSQL[@]}" -Atc "UPDATE plat_homolog.tenant SET config = config || '{\"cota_jobs_dia\": 100000}' WHERE slug IN ('demo', 'demo2') AND coalesce((config->>'cota_jobs_dia')::int, 0) < 100000" >/dev/null
# resíduo zt-* de rodada anterior abortada (mesma faxina do install.sh em modo dev)
"${PSQL[@]}" -f - <<'SQL'
SELECT plat_homolog.tenant_apagar_interno(id) FROM plat_homolog.tenant WHERE slug LIKE 'zt-%';
DELETE FROM plat_homolog.usuario WHERE login LIKE 'zt%';
SQL

echo "== f. var/homolog/homolog.env"
# o daemon do Garage (:3900) é infraestrutura compartilhada de propósito (não há disco para uma instância
# nova), mas a CREDENCIAL não é mais (item L7-31, achado 11 do adversário no turno 3): até 06/09/2026 este
# script copiava para cá o PLAT_GARAGE_ADMIN_TOKEN do .env de produção, e com ele homologação listava e lia
# plat-demo e plat-demo2. Agora homologação recebe uma CHAVE S3 própria, criada e mantida pelo passo de
# operador scripts/garage_homolog_provisionar.sh (seção f2 abaixo), que só é dona dos buckets que ela mesma
# cria. Nenhuma linha de segredo de produção é lida aqui.
cat > "$ENV_HOMOLOG" <<ENV
PLAT_DSN=postgresql://plat_homolog_app:${SENHA_APP}@127.0.0.1:5432/${DB}
PLAT_DSN_WORKER=postgresql://plat_homolog_worker:${SENHA_WORKER}@127.0.0.1:5432/${DB}
PLAT_SECRET=${PLAT_SECRET}
PLAT_AMBIENTE=dev
PLAT_SEMENTE_DEMO=sim
PLAT_URL_PUBLICA=https://homolog.invalido
PLAT_SCHEMA=plat_homolog
PLAT_SCHEMA_TRABALHO=plat_trabalho_homolog
PLAT_CANAL_JOB=plat_homolog_job
PLAT_CANAL_WORKER=plat_homolog_worker
PLAT_GARAGE_URL=http://127.0.0.1:3900
PLAT_GARAGE_REGIAO=garage
PLAT_GARAGE_BUCKET_PREFIXO=homolog-plat-
PLAT_LOG_NIVEL=INFO
PLAT_WORKER_URL=http://127.0.0.1:8156
PLAT_WORKER_NOME=homolog
PLAT_WORKER_PROCESSOS=1
PLAT_WORKER_MEMORIA_MB=512
PLAT_JOB_MAX_REINICIOS=5
PLAT_CREDENCIAIS_ARQUIVO=${CRED_HOMOLOG}
ENV
chmod 600 "$ENV_HOMOLOG"
echo "gerado $ENV_HOMOLOG (nunca commitado: var/ está no .gitignore)"

echo "== f2. credencial de armazenamento PRÓPRIA de homologação (item L7-31)"
# acrescenta PLAT_GARAGE_CHAVE_ID/PLAT_GARAGE_CHAVE_SEGREDO ao arquivo acima e garante que nenhum
# PLAT_GARAGE_ADMIN_TOKEN sobra nele. Sem PLAT_GARAGE_ADMIN_URL/TOKEN a app entra sozinha no modo de chave
# própria (app/objetos.py::_chave_propria): cria bucket pelo CreateBucket do S3, com alias local da chave.
bash "$DIR_REPO/scripts/garage_homolog_provisionar.sh" "$ENV_HOMOLOG"

echo "== g. nginx (porta externa $PORTA_EXTERNA -> API interna $PORTA_INTERNA; /static/ direto do disco)"
# a app nunca serve /static/ sozinha (isso é nginx em produção); sem este bloco todo teste de tela
# quebra por 404 de JS/CSS (achado real do primeiro turno deste item). site PRÓPRIO, nunca edita o
# de produção; só recarrega se o conteúdo mudou (idempotente, reload nunca derruba conexão existente).
SITE=/etc/nginx/sites-available/plat-homolog
CONTEUDO=$(sed -e "s#APP_DIR#$DIR_REPO#g" -e "s#PORTA_EXTERNA#$PORTA_EXTERNA#g" -e "s#PORTA_INTERNA#$PORTA_INTERNA#g" \
  "$DIR_REPO/deploy/nginx_homolog.conf")
if ! sudo test -f "$SITE" || [ "$(sudo cat "$SITE" 2>/dev/null)" != "$CONTEUDO" ]; then
  printf '%s\n' "$CONTEUDO" | sudo tee "$SITE" >/dev/null
  sudo ln -sf "$SITE" /etc/nginx/sites-enabled/plat-homolog
  sudo nginx -t
  sudo systemctl reload nginx
  echo "site plat-homolog escrito/atualizado e nginx recarregado"
else
  echo "site plat-homolog já estava atualizado"
fi
echo "bootstrap de homologação pronto"
