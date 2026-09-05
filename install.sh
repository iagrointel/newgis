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
# todo Python da aplicação roda sem ~/.local (mesma regra da unidade systemd e do Makefile); sudo -u zera o ambiente,
# por isso a variável vai explícita em cada chamada
PY=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/python)
PIP=(sudo -u "$APP_USER" env PYTHONNOUSERSITE=1 venv/bin/pip)

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
# PLAT_GIT_SHA: /saude usa quando não há .git (instalação por tarball); gravado a cada execução (ADR 0001 seção 7)
if SHA=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse HEAD 2>/dev/null); then
  grep -q '^PLAT_GIT_SHA=' .env && sed -i "s/^PLAT_GIT_SHA=.*/PLAT_GIT_SHA=$SHA/" .env || printf 'PLAT_GIT_SHA=%s\n' "$SHA" >> .env
  echo "PLAT_GIT_SHA=$SHA gravado no .env"
else
  grep -qE '^PLAT_GIT_SHA=[0-9a-f]{7,40}$' .env || { echo "sem .git e sem PLAT_GIT_SHA válido no .env: informe o sha da versão instalada" >&2; exit 1; }
  echo "sem .git: PLAT_GIT_SHA do .env mantido ($(grep ^PLAT_GIT_SHA= .env | cut -d= -f2))"
fi

echo "== e. pg_hba"
if grep -qE "^host\s+$DB\s+plat_app\s" "$PG_HBA"; then
  echo "linha já existe em $PG_HBA"
else
  printf 'host    %-15s plat_app        127.0.0.1/32            scram-sha-256\n' "$DB" >> "$PG_HBA"
  echo "linha acrescentada em $PG_HBA"
fi
"${PSQL[@]}" -Atc "SELECT pg_reload_conf()" >/dev/null

echo "== f. venv"
# uvicorn e psycopg2 vêm do sistema por decisão (ADR 0001 seção 2.1): pacotes dpkg, conferidos aqui com nome
for pacote in python3-uvicorn python3-psycopg2 python3-venv; do
  dpkg -s "$pacote" >/dev/null 2>&1 || { echo "falta o pacote do sistema $pacote (apt install $pacote)" >&2; exit 1; }
done
[ -x venv/bin/python ] || sudo -u "$APP_USER" python3 -m venv --system-site-packages venv
"${PIP[@]}" install -q --disable-pip-version-check -r requirements.txt
# prova da cláusula "máquina que nunca viu o repo": a aplicação importa sem o site do usuário
"${PY[@]}" -c "import app.main, fastapi, dotenv; assert fastapi.__file__.startswith('$APP_DIR/venv/'), fastapi.__file__" \
  || { echo "app.main não importa com PYTHONNOUSERSITE=1: requirements.txt incompleto" >&2; exit 1; }
echo "venv: $(venv/bin/python --version) · fastapi $("${PY[@]}" -c 'import fastapi; print(fastapi.__version__)') da venv · pytest $(venv/bin/pytest --version 2>&1 | awk '{print $2}')"

echo "== g. administradores de demonstração"
CRED=tests/credenciais.txt
if [ ! -f "$CRED" ]; then
  printf 'demo admin %s\ndemo2 admin %s\n' "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" > "$CRED"
  echo "$CRED criado"
fi
chmod 600 "$CRED"; chown "$APP_USER":"$APP_USER" "$CRED"
while read -r slug login senha; do
  [ -n "$slug" ] || continue
  # a senha entra pelo stdin (printf é builtin: não aparece em ps nem no COMMAND= que o sudo grava no journal);
  # o hash resultante não é segredo e vai ao psql também por stdin (heredoc)
  HASH=$(printf '%s' "$senha" | "${PY[@]}" -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))")
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
escrever_nginx() {
  local bloco certbot_443 bloco_80
  bloco=$(sed -e "s#DOMINIO#$DOM#g" -e "s#APP_DIR#$APP_DIR#g" -e "s#PORTA#$PORTA#g" deploy/nginx.conf)
  if [ -f "$SITE" ] && grep -q '# managed by Certbot' "$SITE"; then
    # bloco 443: HSTS fica (modelo); as linhas do certbot são preservadas; o bloco 80 do certbot (301) fica como está
    certbot_443=$(awk '/^server[[:space:]]*\{/{n++} n==1 && /# managed by Certbot/' "$SITE")
    bloco_80=$(awk '/^server[[:space:]]*\{/{n++} n>=2' "$SITE")
    printf '%s\n\n%s\n}\n\n%s\n' "$bloco" "$certbot_443" "$bloco_80" > "$SITE.novo"
    echo "bloco 443 reescrito com HSTS, preservando $(printf '%s\n' "$certbot_443" | grep -c .) linhas do certbot"
  else
    # sem certificado o bloco escuta em 80: HSTS não pode existir aqui (o navegador ignora em http e é errado prometer)
    printf '%s\n    listen 80;\n    listen [::]:80;\n}\n' "$bloco" | grep -v 'Strict-Transport-Security' > "$SITE.novo"
    echo "bloco novo em :80, sem HSTS (sem certificado ainda)"
  fi
  # troca com volta: se nginx -t reprovar, o bloco anterior volta e o script para. A cópia fica FORA de
  # sites-enabled (o nginx inclui sites-enabled/* inteiro; uma cópia ali seria um segundo server block)
  local anterior=""
  if [ -f "$SITE" ]; then anterior=/etc/nginx/plat-anterior.$(date +%s).$$; cp -p "$SITE" "$anterior"; fi
  mv "$SITE.novo" "$SITE"
  if ! nginx -t; then
    [ -n "$anterior" ] && mv "$anterior" "$SITE" && echo "nginx -t reprovou: bloco anterior restaurado" >&2
    exit 5
  fi
  [ -n "$anterior" ] && rm -f "$anterior"
  systemctl reload nginx
}
escrever_nginx
if [ ! -d "/etc/letsencrypt/live/$DOM" ]; then
  echo "== i2. certbot"
  certbot --nginx -d "$DOM" --non-interactive --agree-tos --register-unsafely-without-email --redirect
  echo "== i3. nginx de novo, agora com o certificado (bloco 443 com HSTS)"
  escrever_nginx
fi

echo "== j. conferência pública"
# o reload do nginx é assíncrono: os workers antigos ainda servem o bloco velho (200, mas sem HSTS) por alguns
# segundos; espera-se 200 COM o cabeçalho novo. grep sem resultado não pode derrubar o set -e (|| true).
for i in $(seq 1 15); do
  CAB=$(curl -sI -m 10 "https://$DOM/saude" | tr -d '\r' || true)
  CODIGO=$(printf '%s\n' "$CAB" | head -1 | awk '{print $2}')
  HSTS=$(printf '%s\n' "$CAB" | grep -i '^strict-transport-security' || true)
  [ "$CODIGO" = "200" ] && [ -n "$HSTS" ] && break
  sleep 1
done
ROBOTS=$(printf '%s\n' "$CAB" | grep -i '^x-robots-tag' || true)
echo "https://$DOM/saude -> HTTP $CODIGO · $ROBOTS · $HSTS"
[ "$CODIGO" = "200" ] || { echo "esperado 200 em https://$DOM/saude" >&2; exit 4; }
printf '%s' "$ROBOTS" | grep -qi noindex || { echo "X-Robots-Tag sem noindex" >&2; exit 4; }
printf '%s' "$HSTS" | grep -q 'max-age=31536000' || { echo "sem Strict-Transport-Security no bloco 443" >&2; exit 4; }
echo "== instalado em $((SECONDS - INICIO)) s: https://$DOM (serviço $UNIDADE, porta $PORTA)"
