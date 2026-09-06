#!/usr/bin/env bash
# Sobe o diretório LDAP de teste (glauth) em contêiner Docker efêmero, porta 3893 só em 127.0.0.1 (nunca
# exposta fora da máquina). SÓ PARA TESTE (item L0-08-d-ldap); nunca em produção. Idempotente: se o
# contêiner já existe (parado ou rodando), recria do zero para garantir o config.cfg atual.
set -euo pipefail
NOME=plat-ldap-teste
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker rm -f "$NOME" >/dev/null 2>&1 || true
docker run -d --name "$NOME" \
  -p 127.0.0.1:3893:3893 \
  -v "$DIR/glauth.cfg:/app/config/config.cfg:ro" \
  glauth/glauth:latest >/dev/null
# espera a porta abrir (glauth sobe em ~1 s; até 10 s de folga)
for _ in $(seq 1 50); do
  if (exec 3<>"/dev/tcp/127.0.0.1/3893") 2>/dev/null; then exec 3<&- 3>&-; echo "glauth no ar (127.0.0.1:3893)"; exit 0; fi
  sleep 0.2
done
echo "glauth não respondeu em 10s" >&2
docker logs "$NOME" >&2 || true
exit 1
