#!/usr/bin/env bash
# Sobe um Keycloak de teste (item L0-08-a-oidc) em contêiner Docker efêmero, modo dev (start-dev), porta 8236
# só em 127.0.0.1 (nunca exposta fora da máquina). SÓ PARA TESTE; nunca em produção. Idempotente: se o
# contêiner já existe (parado ou rodando), recria do zero para garantir o realm.json atual.
set -euo pipefail
NOME=plat-keycloak-teste
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker rm -f "$NOME" >/dev/null 2>&1 || true
docker run -d --name "$NOME" \
  -p 127.0.0.1:8236:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin-teste-oidc \
  -v "$DIR/realm.json:/opt/keycloak/data/import/realm.json:ro" \
  quay.io/keycloak/keycloak:26.0 start-dev --import-realm >/dev/null
# a interface de saúde (/health/ready) mora na porta de administração 9000, que não expomos; o sinal de
# pronto real é a descoberta OIDC do REALM DE TESTE respondendo (prova que o import terminou, não só que a
# porta HTTP abriu). Keycloak em modo dev leva alguns segundos: até 90 s de folga (JVM completa, não um
# binário Go pequeno como o glauth do LDAP).
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:8236/realms/plataforma-teste-oidc/.well-known/openid-configuration" >/dev/null 2>&1; then
    echo "keycloak no ar (127.0.0.1:8236, realm plataforma-teste-oidc)"
    exit 0
  fi
  sleep 1
done
echo "keycloak não respondeu em 90s" >&2
docker logs "$NOME" 2>&1 | tail -100 >&2
exit 1
