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
# segredos fora do .env (item L7-19): mesmo caminho que deploy/plat-api.service e plat-worker.service
# usam em LoadCredential=; não é parâmetro do script de propósito (o caminho tem de bater nos dois lados)
CRED_DIR=/etc/plat/segredos
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

echo "== d. .env"
if [ ! -f .env ]; then
  SENHA=$(openssl rand -hex 16)
  cat > .env <<ENV
PLAT_DSN=postgresql://plat_app:$SENHA@127.0.0.1:5432/$DB
PLAT_AMBIENTE=producao
PLAT_URL_PUBLICA=https://$DOM
PLAT_GIT_SHA=
PLAT_MARTIN_URL=
PLAT_TITILER_URL=
PLAT_GARAGE_URL=http://127.0.0.1:3900
PLAT_LOG_NIVEL=INFO
PLAT_WORKER_URL=http://127.0.0.1:8153
PLAT_WORKER_PROCESSOS=1
PLAT_WORKER_MEMORIA_MB=1536
ENV
  echo ".env criado"
else
  echo ".env já existe (mantido)"
fi
chmod 600 .env; chown "$APP_USER":"$APP_USER" .env
# fila de jobs (ADR 0003 seção 11): instalação existente ganha as chaves do worker sem perder as demais
for chave in PLAT_WORKER_URL=http://127.0.0.1:8153 PLAT_WORKER_PROCESSOS=1 PLAT_WORKER_MEMORIA_MB=1536; do
  grep -q "^${chave%%=*}=" .env || echo "$chave" >> .env
done
echo "== d2. segredos fora do .env (item L7-19, docs/SEGURANCA.md)"
# PLAT_SECRET e a senha da role plat_worker (PLAT_DSN_WORKER) moram em arquivo fora do repositório, dono
# root, modo 600; só o systemd (LoadCredential=, deploy/plat-api.service e plat-worker.service) entrega
# uma cópia a cada unidade (achado do adversário no T2, L0-05: PLAT_DSN_WORKER em .env é autoridade
# total sobre job de qualquer inquilino). MEDIDO nesta máquina: a cópia some do .env, do argv, do
# journal e de qualquer usuário do sistema que não seja root ou o dono da unidade — não isola de outro
# PROCESSO rodando como o mesmo dono (todo produto desta máquina roda como o mesmo usuário; isolamento
# completo pediria DynamicUser=, fora de escopo aqui); ver docs/SEGURANCA.md §1 para o detalhe medido.
# Retrocompatível nos dois sentidos: instalação do zero nunca escreve os dois no .env; instalação
# anterior ao L7-19 que ainda os tem lá é migrada aqui, uma vez, e a linha some do .env.
install -d -m 0700 -o root -g root "$CRED_DIR"
if [ ! -s "$CRED_DIR/PLAT_SECRET" ]; then
  install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_SECRET"
  if grep -q '^PLAT_SECRET=' .env; then
    sed -nE 's/^PLAT_SECRET=//p' .env | head -n1 > "$CRED_DIR/PLAT_SECRET"
    echo "PLAT_SECRET migrado do .env para $CRED_DIR (instalação anterior ao L7-19)"
  else
    openssl rand -hex 32 > "$CRED_DIR/PLAT_SECRET"
    echo "PLAT_SECRET novo gerado em $CRED_DIR"
  fi
else
  echo "$CRED_DIR/PLAT_SECRET já existe (mantido)"
fi
sed -i '/^PLAT_SECRET=/d' .env
if [ ! -s "$CRED_DIR/PLAT_DSN_WORKER" ]; then
  install -m 0600 -o root -g root /dev/null "$CRED_DIR/PLAT_DSN_WORKER"
  if grep -q '^PLAT_DSN_WORKER=' .env; then
    sed -nE 's/^PLAT_DSN_WORKER=//p' .env | head -n1 > "$CRED_DIR/PLAT_DSN_WORKER"
    echo "PLAT_DSN_WORKER migrado do .env para $CRED_DIR (instalação anterior ao L7-19)"
  else
    printf 'postgresql://plat_worker:%s@127.0.0.1:5432/%s' "$(openssl rand -hex 16)" "$DB" > "$CRED_DIR/PLAT_DSN_WORKER"
    echo "PLAT_DSN_WORKER novo gerado em $CRED_DIR"
  fi
else
  echo "$CRED_DIR/PLAT_DSN_WORKER já existe (mantido)"
fi
sed -i '/^PLAT_DSN_WORKER=/d' .env

echo "== d3. senha das roles alinhada aos credentials/.env"
SENHA_WORKER=$(sed -nE 's#^postgresql://plat_worker:([^@]+)@.*#\1#p' "$CRED_DIR/PLAT_DSN_WORKER")
[ -n "$SENHA_WORKER" ] || { echo "$CRED_DIR/PLAT_DSN_WORKER não tem a forma postgresql://plat_worker:<senha>@..." >&2; exit 1; }
printf "ALTER ROLE plat_worker PASSWORD '%s';\n" "$SENHA_WORKER" | "${PSQL[@]}" -f -
echo "senha de plat_worker alinhada ao credential"
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
if grep -qE "^host\s+$DB\s+plat_worker\s" "$PG_HBA"; then
  echo "linha de plat_worker já existe em $PG_HBA"
else
  printf 'host    %-15s plat_worker     127.0.0.1/32            scram-sha-256\n' "$DB" >> "$PG_HBA"
  echo "linha de plat_worker acrescentada em $PG_HBA"
fi
"${PSQL[@]}" -Atc "SELECT pg_reload_conf()" >/dev/null

echo "== f. venv"
# uvicorn e psycopg2 vêm do sistema por decisão (ADR 0001 seção 2.1): pacotes dpkg, conferidos aqui com nome
for pacote in python3-uvicorn python3-psycopg2 python3-venv python3-cryptography; do
  dpkg -s "$pacote" >/dev/null 2>&1 || { echo "falta o pacote do sistema $pacote (apt install $pacote)" >&2; exit 1; }
done
[ -x venv/bin/python ] || sudo -u "$APP_USER" python3 -m venv --system-site-packages venv
"${PIP[@]}" install -q --disable-pip-version-check -r requirements.txt
# prova da cláusula "máquina que nunca viu o repo": a aplicação importa sem o site do usuário. PLAT_SECRET
# agora mora em $CRED_DIR (0600, dono root; d2 acima) e o "$APP_USER" que roda este import não é root —
# de propósito, não lê o segredo de verdade aqui. Um valor sintético de 64 hex só serve para settings.py
# aceitar o formato e a importação prosseguir; nunca é usado por um serviço de verdade (o systemd entrega
# o de verdade via LoadCredential=) e não é segredo, então tanto faz aparecer em `ps`.
"${PY[@]}" -c "import os; os.environ.setdefault('PLAT_SECRET', 'a' * 64); import app.main, fastapi, dotenv; assert fastapi.__file__.startswith('$APP_DIR/venv/'), fastapi.__file__" \
  || { echo "app.main não importa com PYTHONNOUSERSITE=1: requirements.txt incompleto" >&2; exit 1; }
echo "venv: $(venv/bin/python --version) · fastapi $("${PY[@]}" -c 'import fastapi; print(fastapi.__version__)') da venv · pytest $(venv/bin/pytest --version 2>&1 | awk '{print $2}')"

echo "== g. administradores: plataforma (superadmin, 2FA obrigatório) e demonstração (demo, demo2)"
CRED=tests/credenciais.txt
if [ ! -f "$CRED" ]; then
  printf 'plataforma admin %s\ndemo admin %s\ndemo2 admin %s\n' "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" > "$CRED"
  echo "$CRED criado"
elif ! grep -q '^plataforma ' "$CRED"; then
  printf 'plataforma admin %s\n' "$(openssl rand -hex 8)" >> "$CRED"
  echo "$CRED: linha de plataforma acrescentada"
fi
chmod 600 "$CRED"; chown "$APP_USER":"$APP_USER" "$CRED"
# o 2FA do admin semeado é resetado a cada instalação (superadmin exige 2FA: a suíte liga de novo e guarda o segredo
# em tests/credenciais_totp.txt, fora do git); o arquivo antigo perde a validade aqui
rm -f tests/credenciais_totp.txt
while read -r slug login senha; do
  [ -n "$slug" ] || continue
  # a senha entra pelo stdin (printf é builtin: não aparece em ps nem no COMMAND= que o sudo grava no journal);
  # o hash resultante não é segredo e vai ao psql também por stdin (heredoc)
  HASH=$(printf '%s' "$senha" | "${PY[@]}" -c "import sys; from app.senha import gerar_hash; print(gerar_hash(sys.stdin.read()))")
  "${PSQL[@]}" -f - <<SQL
INSERT INTO plat.usuario(tenant_id, login, nome, senha_hash, perfil, superadmin)
SELECT t.id, '$login', CASE WHEN '$slug' = 'plataforma' THEN 'Operador da plataforma' ELSE 'Administrador $slug' END,
       '$HASH', 'admin', ('$slug' = 'plataforma')
FROM plat.tenant t WHERE t.slug = '$slug'
ON CONFLICT (tenant_id, login) DO UPDATE SET senha_hash = EXCLUDED.senha_hash, ativo = true, superadmin = EXCLUDED.superadmin,
  trocar_senha = false, totp_secret = NULL, totp_ativo = false, totp_ultimo_passo = NULL, codigos_recuperacao = NULL,
  bloqueado_ate = NULL, falhas_login = 0, falhas_desde = NULL, desafio_2fa_hash = NULL, desafio_2fa_ate = NULL,
  perfil = 'admin', papel_id = NULL;
SQL
  echo "admin de $slug semeado"
done < "$CRED"
# partições do mês corrente e dos 3 seguintes para log_acesso e evento (ADR 0002 seções 9.2 e 9.4; o L0-05-d agenda)
"${PSQL[@]}" -Atc "SELECT plat.log_particao_garantir((date_trunc('month', now()) + make_interval(months => m))::date), plat.evento_particao_garantir((date_trunc('month', now()) + make_interval(months => m))::date) FROM generate_series(0, 3) AS m" | tr '\n' ' '; echo
echo "partições de log_acesso e evento garantidas"
# o banco passa a saber em que ambiente está (plat.ambiente, migração 014). semear_demo liga plat.jobs_semear_demo
# (semeadura de jobs terminais nos inquilinos de demonstração, usada pelo e2e dos 1.000 jobs): true só quando o .env
# diz PLAT_AMBIENTE=dev ou PLAT_SEMENTE_DEMO=sim. Numa instalação de cliente as duas chaves faltam e fica false.
AMB=$(grep -E '^PLAT_AMBIENTE=' .env | head -n1 | cut -d= -f2)
SEM=$(grep -E '^PLAT_SEMENTE_DEMO=' .env | head -n1 | cut -d= -f2)
if [ "${AMB:-producao}" = dev ] || [ "${SEM:-}" = sim ]; then SEMEAR=true; else SEMEAR=false; fi
"${PSQL[@]}" -Atc "INSERT INTO plat.ambiente (unico, nome, semear_demo) VALUES (true, '${AMB:-producao}', $SEMEAR) ON CONFLICT (unico) DO UPDATE SET nome = EXCLUDED.nome, semear_demo = EXCLUDED.semear_demo, definido_em = now()" >/dev/null
echo "plat.ambiente = ${AMB:-producao} (semear_demo = $SEMEAR)"

# em dev (PLAT_AMBIENTE=dev no .env) a suíte pode ter deixado resíduo zt-* (rodada abortada): inquilinos zt-inq-*,
# usuários/grupos/papéis/tokens zt-* dos inquilinos de demonstração somem aqui; em producao nada é tocado
if grep -qE '^PLAT_AMBIENTE=dev$' .env; then
  "${PSQL[@]}" -f - <<'SQL'
SELECT plat.tenant_apagar_interno(id) FROM plat.tenant WHERE slug LIKE 'zt-%';
UPDATE plat.token_servico SET revogado_em = now() WHERE nome LIKE 'zt%' AND revogado_em IS NULL;
DELETE FROM plat.grupo WHERE nome LIKE 'zt%';
UPDATE plat.usuario SET papel_id = NULL WHERE login LIKE 'zt%' OR papel_id IN (SELECT id FROM plat.papel_personalizado WHERE nome LIKE 'zt%');
DELETE FROM plat.usuario WHERE login LIKE 'zt%';
DELETE FROM plat.papel_personalizado WHERE nome LIKE 'zt%';
SQL
  echo "resíduos zt-* de teste apagados (modo dev)"
fi

# inquilinos de demonstração: cota diária de jobs alta (a suíte cria centenas por rodada; padrão de produto = 1.000, ADR 0003)
"${PSQL[@]}" -Atc "UPDATE plat.tenant SET config = config || '{\"cota_jobs_dia\": 100000}' WHERE slug IN ('demo', 'demo2') AND coalesce((config->>'cota_jobs_dia')::int, 0) < 100000" >/dev/null
echo "cota_jobs_dia dos inquilinos de demonstração garantida (100000)"

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

echo "== h2. systemd plat-worker"
install -d -o "$APP_USER" -g "$APP_USER" var/jobs
sed -e "s#APP_DIR#$APP_DIR#g" -e "s#APP_USER#$APP_USER#g" deploy/plat-worker.service > /etc/systemd/system/plat-worker.service
systemctl daemon-reload
systemctl enable -q plat-worker
systemctl restart plat-worker
for i in $(seq 1 30); do
  if curl -fsS -m 2 "http://127.0.0.1:8153/saude" >/dev/null 2>&1; then echo "/saude do worker respondeu 200 em ${i} s"; break; fi
  if [ "$i" -eq 30 ]; then echo "plat-worker não respondeu em 30 s:" >&2; journalctl -u plat-worker -n 30 --no-pager >&2; exit 1; fi
  sleep 1
done
systemctl --no-pager --lines=0 status plat-worker | sed -n '1,4p'

echo "== i. nginx"
SITE=/etc/nginx/sites-enabled/$DOM
# zona limit_req própria: 10 tentativas/min por IP em /api/login e /api/login/2fa (ADR 0002 seção 6.2)
LIMITES=/etc/nginx/conf.d/plat_limites.conf
printf '# plat: limite por IP nos logins (ADR 0002 secao 6.2); escrito pelo install.sh\nlimit_req_zone $binary_remote_addr zone=plat_login:10m rate=10r/m;\n' > "$LIMITES.novo"
if [ -f "$LIMITES" ] && cmp -s "$LIMITES" "$LIMITES.novo"; then rm -f "$LIMITES.novo"; echo "$LIMITES já existe (igual)"; else mv "$LIMITES.novo" "$LIMITES"; echo "$LIMITES escrito"; fi
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
curl -fsS -m 5 "https://$DOM/saude" | grep -q '"workers_vivos": *[1-9]' || { echo "/saude sem worker vivo (fila.workers_vivos)" >&2; exit 4; }
echo "== instalado em $((SECONDS - INICIO)) s: https://$DOM (serviços $UNIDADE :$PORTA e plat-worker :8153)"
