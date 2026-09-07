#!/bin/sh
# Entrypoint da API em contêiner (item L7-01-a-compose-perfis). MESMO mecanismo do entrypoint do worker
# (deploy/entrypoint-worker.sh): o contêiner parte como root só para ler os segredos montados root:root 0600
# (docker-compose.yml -> secrets: PLAT_SECRET, PLAT_DSN_WORKER opcional), exporta como variável de ambiente e
# solta o privilégio com setpriv antes de importar uma linha da aplicação. Ver os comentários de
# entrypoint-worker.sh para o raciocínio completo (CREDENTIALS_DIRECTORY nunca propagada, etc.).
set -eu
SECRETS_DIR=/run/secrets

if [ -r "$SECRETS_DIR/PLAT_SECRET" ]; then
  PLAT_SECRET=$(cat "$SECRETS_DIR/PLAT_SECRET")
  export PLAT_SECRET
fi
if [ -r "$SECRETS_DIR/PLAT_DSN_WORKER" ]; then
  PLAT_DSN_WORKER=$(cat "$SECRETS_DIR/PLAT_DSN_WORKER")
  export PLAT_DSN_WORKER
fi

PORTA=${PLAT_API_PORTA:-8150}
PROCESSOS=${PLAT_API_WORKERS:-2}

exec setpriv --reuid=plat --regid=plat --init-groups -- \
    venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORTA" --workers "$PROCESSOS" \
    --proxy-headers --forwarded-allow-ips='*' --no-access-log
