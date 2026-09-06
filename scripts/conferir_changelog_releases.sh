#!/usr/bin/env bash
# Confere que toda etiqueta git vX.Y.Z tem uma seção "## [X.Y.Z]" em CHANGELOG.md e vice-versa (item
# L7-15-processo-release; refutação do portão: "adversário procura no CHANGELOG uma versão sem etiqueta git
# ou etiqueta sem changelog"). Chamado por scripts/preparar_release.sh depois de criar a etiqueta nova;
# também roda sozinho a qualquer momento. Saída != 0 se algo divergir, com a lista de divergências em stderr.
#
# Uso: bash scripts/conferir_changelog_releases.sh [caminho/do/CHANGELOG.md]
set -euo pipefail
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
CHANGELOG=${1:-"$APP_DIR/CHANGELOG.md"}
[ -f "$CHANGELOG" ] || { echo "changelog não existe: $CHANGELOG" >&2; exit 1; }
cd "$APP_DIR"

TAGS=$(git tag -l 'v*' | sed 's/^v//' | sort -V || true)
SECOES=$(grep -oE '^## \[[0-9]+\.[0-9]+\.[0-9]+\]' "$CHANGELOG" | sed -E 's/^## \[(.*)\]/\1/' | sort -V || true)

FALHOU=0
for t in $TAGS; do
  if ! printf '%s\n' "$SECOES" | grep -qx "$t"; then
    echo "etiqueta v$t sem seção correspondente no CHANGELOG" >&2
    FALHOU=1
  fi
done
for s in $SECOES; do
  if ! printf '%s\n' "$TAGS" | grep -qx "$s"; then
    echo "seção [$s] no CHANGELOG sem etiqueta git v$s" >&2
    FALHOU=1
  fi
done
if [ "$FALHOU" = 0 ]; then
  N=$(printf '%s\n' "$TAGS" | grep -c . || true)
  echo "changelog e etiquetas em dia ($N etiqueta(s))"
fi
exit $FALHOU
