#!/usr/bin/env bash
# Derruba o diretório LDAP de teste (prova o portão "diretório fora do ar não derruba o login local").
set -euo pipefail
docker rm -f plat-ldap-teste >/dev/null 2>&1 || true
echo "glauth parado"
