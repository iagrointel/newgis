#!/usr/bin/env bash
# Alias: o portão do item L7-15-processo-release em laco/estado.json nomeia o script "release.sh"; a
# automação real ficou em preparar_release.sh (nome usado no recorte que abriu este turno). Os dois nomes
# fazem a mesma coisa — nunca duas implementações a manter.
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/preparar_release.sh" "$@"
