#!/bin/sh
# Entrypoint do worker em contêiner (item L0-05-e-worker-em-container). O contêiner PARTE como root só até
# aqui: os segredos (PLAT_SECRET, PLAT_DSN_WORKER) chegam pelo mesmo arquivo root:root modo 600 que a
# unidade systemd lê via LoadCredential= (/etc/plat/segredos/*, docs/SEGURANCA.md); o docker-compose.worker.yml
# monta esse mesmo arquivo como secret e o Compose (fora de swarm, MEDIDO neste item) preserva o dono e a
# permissão de origem no bind — um processo não-root dentro do contêiner não conseguiria ler o arquivo. Por
# isso o processo lê os segredos como root, exporta como variável de ambiente e só então solta o privilégio.
#
# setpriv (não `su`): troca uid/gid e faz exec() direto, sem PAM e sem filtrar o ambiente do processo — as
# variáveis exportadas aqui chegam intactas ao worker.
#
# NUNCA propagar CREDENTIALS_DIRECTORY para o processo final (nem defini-la aqui): app/settings.py também
# sabe ler segredos de CREDENTIALS_DIRECTORY (mesmo mecanismo do LoadCredential= do systemd) e tentaria reler
# os MESMOS arquivos já como `plat` — que continuam dono root:600 dentro do contêiner (o bind do Compose
# preserva a permissão de origem; o systemd, ao contrário, ajusta o dono/ACL do diretório de credenciais para
# o usuário da unidade, então esse caminho nunca vê este problema lá). Sem CREDENTIALS_DIRECTORY no ambiente,
# app/settings.py nem tenta — as duas variáveis já chegam prontas via os.environ, que settings.py sempre lê
# por último e com prioridade (mesma regra que a suíte de teste usa para injetar PLAT_SECRET, ver Makefile).
set -eu
SECRETS_DIR=/run/secrets   # caminho fixo que o docker-compose.worker.yml monta (Compose fora de swarm)

if [ -r "$SECRETS_DIR/PLAT_SECRET" ]; then
  PLAT_SECRET=$(cat "$SECRETS_DIR/PLAT_SECRET")
  export PLAT_SECRET
fi
if [ -r "$SECRETS_DIR/PLAT_DSN_WORKER" ]; then
  PLAT_DSN_WORKER=$(cat "$SECRETS_DIR/PLAT_DSN_WORKER")
  export PLAT_DSN_WORKER
fi
# PLAT_DSN (item L7-19): settings.py exige a chave sempre, mesmo no worker (que só USA PLAT_DSN_WORKER para
# mudar estado de job) — sem isto o import de app.settings falha na partida com "chave obrigatória ausente".
if [ -r "$SECRETS_DIR/PLAT_DSN" ]; then
  PLAT_DSN=$(cat "$SECRETS_DIR/PLAT_DSN")
  export PLAT_DSN
fi

exec setpriv --reuid=plat --regid=plat --init-groups -- venv/bin/python -m app.jobs.worker
