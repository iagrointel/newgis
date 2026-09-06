#!/usr/bin/env bash
# Verifica a assinatura Ed25519 de um pacote de atualização do plat (item L7-16-assinatura-pacote, ADR
# 0007 seção 3) contra as chaves públicas fixadas em deploy/chaves_publicas_release.txt — dado de
# INSTALAÇÃO, versionado no git e conferido por tests/unit/test_release_seguranca.py. Recusa (saída != 0)
# se o arquivo foi alterado, se não há .sig, se o .sig não descreve ESTE arquivo (nome, tamanho, sha256)
# ou se a chave que assinou não é confiável nesta instalação. Funciona sem rede: é o caminho do appliance
# sem internet.
#
# Uso: bash scripts/verificar_pacote.sh <arquivo> [<assinatura.sig>]
#
# Saídas: 0 aceito · 2 .sig ausente/malformado/formato antigo · 3 chave não confiável · 4 assinatura
# inválida ou arquivo diferente do que a declaração assinada descreve.
#
# ⛔ ENDURECIDO em 06/09/2026 (ataque adversarial ao grupo G6): a lista de confiança não vem mais de
# variável de ambiente nem de APP_DIR. `PLAT_CHAVES_CONFIAVEIS` só ACRESCENTA chaves quando o ambiente é
# declaradamente de desenvolvimento (PLAT_AMBIENTE em dev/teste/homolog) e, mesmo aí, o aviso vai para
# stderr; em produção é ignorada, também com aviso. Quem decide isso é
# `chaves_confiaveis_efetivas()` em scripts/plat_assinatura.py, um lugar só.
set -euo pipefail
APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ARQUIVO=${1:?"uso: bash scripts/verificar_pacote.sh <arquivo> [<assinatura.sig>]"}
ASSINATURA=${2:-"$ARQUIVO.sig"}
[ -f "$ARQUIVO" ] || { echo "arquivo não existe: $ARQUIVO" >&2; exit 1; }

env PYTHONNOUSERSITE=1 "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/plat_assinatura.py" \
  verificar "$ARQUIVO" --assinatura "$ASSINATURA" \
  --confiaveis "$APP_DIR/deploy/chaves_publicas_release.txt"
