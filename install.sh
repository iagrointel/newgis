#!/usr/bin/env bash
# Instalador do plat (ADR 0001 seção 4). Root, idempotente: pode rodar quantas vezes for preciso.
# Uso: sudo bash install.sh <dominio> [porta]     ex.: sudo bash install.sh plat.iagrointel.com 8150
# Faz: extensões, migrações (db/migrar.sh), .env 600 + senha da role realinhada, linha no pg_hba.conf,
# venv, unidade systemd plat-api, nginx (preservando as linhas do certbot), certbot só sem certificado,
# e confere https://<dominio>/saude com X-Robots-Tag. O que este script não faz, não existe (portão P5).
set -euo pipefail
INICIO=$SECONDS
DOM=${1:?uso: sudo bash install.sh <dominio> [porta]}
PORTA=${2:-8150}
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
APP_USER=${APP_USER:-$(stat -c %U "$APP_DIR")}
DB=${PLAT_DB:-iagro_sat}
PG_HBA=${PG_HBA:-/etc/postgresql/16/main/pg_hba.conf}
UNIDADE=plat-api
[ "$(id -u)" -eq 0 ] || { echo "rode como root: sudo bash install.sh $DOM $PORTA" >&2; exit 1; }
cd "$APP_DIR"
PSQL=(sudo -u postgres psql -d "$DB" -X -q -v ON_ERROR_STOP=1)

echo "== a. máquina"
df -h / | tail -1
free -g | head -2
echo "app_dir=$APP_DIR usuario=$APP_USER banco=$DB porta=$PORTA dominio=$DOM"

echo "== b. extensões"
"${PSQL[@]}" -f - <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SQL

echo "== c. migrações"
bash db/migrar.sh

echo "== d. .env e senha da role"
if [ ! -f .env ]; then
  SENHA=$(openssl rand -hex 16)
  SEGREDO=$(openssl rand -hex 32)
  cat > .env <<ENV
PLAT_DSN=postgresql://plat_app:$SENHA@127.0.0.1:5432/$DB
PLAT_SECRET=$SEGREDO
PLAT_AMBIENTE=producao
PLAT_URL_PUBLICA=https://$DOM
PLAT_GIT_SHA=
PLAT_MARTIN_URL=
PLAT_TITILER_URL=
PLAT_GARAGE_URL=http://127.0.0.1:3900
PLAT_LOG_NIVEL=INFO
ENV
  echo ".env criado"
else
  echo ".env já existe (mantido)"
fi
chmod 600 .env; chown "$APP_USER":"$APP_USER" .env
SENHA=$(sed -nE 's#^PLAT_DSN=postgresql://plat_app:([^@]+)@.*#\1#p' .env)
[ -n "$SENHA" ] || { echo "PLAT_DSN no .env não tem a forma postgresql://plat_app:<senha>@..." >&2; exit 1; }
# sempre: a senha do banco passa a ser a do .env (idempotência de verdade; ADR risco 6)
printf "ALTER ROLE plat_app PASSWORD '%s';\n" "$SENHA" | "${PSQL[@]}" -f -
echo "senha de plat_app alinhada ao .env"

echo "== e. pg_hba"
if grep -qE "^host\s+$DB\s+plat_app\s" "$PG_HBA"; then
  echo "linha já existe em $PG_HBA"
else
  printf 'host    %-15s plat_app        127.0.0.1/32            scram-sha-256\n' "$DB" >> "$PG_HBA"
  echo "linha acrescentada em $PG_HBA"
fi
"${PSQL[@]}" -Atc "SELECT pg_reload_conf()" >/dev/null

echo "== f. venv"
[ -x venv/bin/python ] || sudo -u "$APP_USER" python3 -m venv --system-site-packages venv
sudo -u "$APP_USER" venv/bin/pip install -q --disable-pip-version-check -r requirements.txt
echo "venv: $(venv/bin/python --version) · pytest $(venv/bin/pytest --version 2>&1 | awk '{print $2}')"

echo "== g. administradores de demonstração"
CRED=tests/credenciais.txt
if [ ! -f "$CRED" ]; then
  printf 'demo admin %s\ndemo2 admin %s\n' "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" > "$CRED"
  echo "$CRED criado"
fi
chmod 600 "$CRED"; chown "$APP_USER":"$APP_USER" "$CRED"
while read -r slug login senha; do
  [ -n "$slug" ] || continue
  HASH=$(sudo -u "$APP_USER" venv/bin/python -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.argv[1]))" "$senha")
  "${PSQL[@]}" -f - <<SQL
INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, superadmin)
SELECT t.id, '$login', 'Administrador $slug', '$HASH', 'admin', ('$slug' = 'demo')
FROM plat.tenant t WHERE t.slug = '$slug'
ON CONFLICT (tenant_id, login) DO UPDATE SET senha_hash = EXCLUDED.senha_hash, ativo = true;
SQL
  echo "admin de $slug semeado"
done < "$CRED"

echo "== h. systemd $UNIDADE"
sed -e "s#APP_DIR#$APP_DIR#g" -e "s#APP_USER#$APP_USER#g" -e "s#PORTA#$PORTA#g" deploy/plat-api.service > /etc/systemd/system/$UNIDADE.service
systemctl daemon-reload
systemctl enable -q $UNIDADE
systemctl restart $UNIDADE
for i in $(seq 1 30); do
  if curl -fsS -m 2 "http://127.0.0.1:$PORTA/saude" >/dev/null 2>&1; then echo "/saude local respondeu 200 em ${i} s"; break; fi
  if [ "$i" -eq 30 ]; then echo "plat-api não respondeu 200 em /saude em 30 s:" >&2; journalctl -u $UNIDADE -n 30 --no-pager >&2; curl -sS -m 2 "http://127.0.0.1:$PORTA/saude" >&2 || true; exit 1; fi
  sleep 1
done
systemctl --no-pager --lines=0 status $UNIDADE | sed -n '1,4p'

echo "== i. nginx"
SITE=/etc/nginx/sites-enabled/$DOM
BLOCO=$(sed -e "s#DOMINIO#$DOM#g" -e "s#APP_DIR#$APP_DIR#g" -e "s#PORTA#$PORTA#g" deploy/nginx.conf)
if [ -f "$SITE" ] && grep -q '# managed by Certbot' "$SITE"; then
  CERTBOT_443=$(awk '/^server[[:space:]]*\{/{n++} n==1 && /# managed by Certbot/' "$SITE")
  BLOCO_80=$(awk '/^server[[:space:]]*\{/{n++} n>=2' "$SITE")
  printf '%s\n\n%s\n}\n\n%s\n' "$BLOCO" "$CERTBOT_443" "$BLOCO_80" > "$SITE.novo"
  echo "bloco reescrito preservando $(printf '%s\n' "$CERTBOT_443" | grep -c .) linhas do certbot"
else
  printf '%s\n    listen 80;\n    listen [::]:80;\n}\n' "$BLOCO" > "$SITE.novo"
  echo "bloco novo (sem certificado ainda)"
fi
mv "$SITE.novo" "$SITE"
nginx -t
systemctl reload nginx
if [ ! -d "/etc/letsencrypt/live/$DOM" ]; then
  echo "== i2. certbot"
  certbot --nginx -d "$DOM" --non-interactive --agree-tos --register-unsafely-without-email --redirect
fi

echo "== j. conferência pública"
# o reload do nginx é assíncrono: os workers antigos ainda servem o bloco velho por alguns segundos
for i in $(seq 1 15); do
  CAB=$(curl -sI -m 10 "https://$DOM/saude" || true)
  CODIGO=$(printf '%s\n' "$CAB" | head -1 | awk '{print $2}')
  [ "$CODIGO" = "200" ] && break
  sleep 1
done
ROBOTS=$(printf '%s\n' "$CAB" | grep -i '^x-robots-tag' | tr -d '\r')
echo "https://$DOM/saude -> HTTP $CODIGO · $ROBOTS"
[ "$CODIGO" = "200" ] || { echo "esperado 200 em https://$DOM/saude" >&2; exit 4; }
printf '%s' "$ROBOTS" | grep -qi noindex || { echo "X-Robots-Tag sem noindex" >&2; exit 4; }
echo "== instalado em $((SECONDS - INICIO)) s: https://$DOM (serviço $UNIDADE, porta $PORTA)"
