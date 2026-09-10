#!/usr/bin/env bash
# Derruba o Keycloak de teste (prova o portão "provedor desligado não impede o login local do admin").
set -euo pipefail
docker rm -f plat-keycloak-teste >/dev/null 2>&1 || true
echo "keycloak parado"
