#!/usr/bin/env bash
# Verifica a assinatura Ed25519 de um pacote de atualização do plat (item L7-16-assinatura-pacote, ADR
# 0007 seção 3) contra as chaves públicas fixadas em deploy/chaves_publicas_release.txt (versionadas no
# git). Recusa — saída ≠ 0 — se o arquivo foi alterado, se não há .sig, ou se a chave que assinou não é
# confiável nesta versão (rotação pendente). Funciona sem rede: é o caminho do appliance sem internet.
#
# Uso: bash scripts/verificar_pacote.sh <arquivo> [<assinatura.sig>]
#
# Variável opcional: PLAT_CHAVES_CONFIAVEIS (padrão: deploy/chaves_publicas_release.txt do repositório).
set -euo pipefail
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
ARQUIVO=${1:?uso: bash scripts/verificar_pacote.sh <arquivo> [<assinatura.sig>]}
ASSINATURA=${2:-"$ARQUIVO.sig"}
[ -f "$ARQUIVO" ] || { echo "arquivo não existe: $ARQUIVO" >&2; exit 1; }
CONFIAVEIS=${PLAT_CHAVES_CONFIAVEIS:-"$APP_DIR/deploy/chaves_publicas_release.txt"}

env PYTHONNOUSERSITE=1 "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/plat_assinatura.py" \
  verificar "$ARQUIVO" --assinatura "$ASSINATURA" --confiaveis "$CONFIAVEIS"
