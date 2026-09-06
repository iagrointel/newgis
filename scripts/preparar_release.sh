#!/usr/bin/env bash
# Processo de release (item L7-15-processo-release; docs/RELEASE.md). Automatiza o que dá sem decisão
# humana e PARA no primeiro erro: (1) valida X.Y.Z como semver 2.0.0; (2) gera o rascunho de changelog
# (keep-a-changelog) do `git log` desde a última etiqueta — scripts/gerar_changelog_release.py, NUNCA edita
# CHANGELOG.md sozinho; (3) `make check` (escopo verde, reaproveita o Makefile); (4) `make homolog` (reaproveita
# L7-31 — migra plat_homolog, sobe API+worker temporários, roda o e2e isolado); (5) empacota a árvore de
# produção num tar determinístico COM um RELEASE_MANIFEST.json dentro (versão, commit, make_check/make_homolog
# = "passou") — o manifesto viaja onde a assinatura cobre, então forjar "passou por homologação" sem a chave
# privada (item L7-16) é impossível; (6) assina com scripts/assinar_pacote.sh; (7) cria a etiqueta anotada
# vX.Y.Z e confere que CHANGELOG.md tem a seção correspondente (scripts/conferir_changelog_releases.sh); e
# PARA — falta só a decisão humana de publicar, com scripts/publicar_release.sh (que recusa qualquer pacote
# sem manifesto/assinatura válidos, inclusive um que nunca passou por aqui).
#
# Uso: bash scripts/preparar_release.sh X.Y.Z [--hotfix]
#   --hotfix   exige rodar no ramo hotfix/X.Y.Z (recusa em qualquer outro ramo)
#
# Variáveis (só para teste — nunca use em produção real, ver tests/unit/test_preparar_release.py):
#   PLAT_RELEASE_CHECK_CMD     comando no lugar de "make check"   (padrão: "make check")
#   PLAT_RELEASE_HOMOLOG_CMD   comando no lugar de "make homolog" (padrão: "make homolog")
#   PLAT_ASSINAR_SCRIPT        script de assinatura (padrão: $APP_DIR/scripts/assinar_pacote.sh)
#   PLAT_PACOTE_ITENS          lista de itens a empacotar, separados por espaço (padrão: ver PACOTE_ITENS)
set -euo pipefail
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=${APP_DIR:-$(cd "$AQUI/.." && pwd)}
VERSAO=${1:?"uso: bash scripts/preparar_release.sh X.Y.Z [--hotfix]"}
HOTFIX=0
for arg in "$@"; do [ "$arg" = "--hotfix" ] && HOTFIX=1; done

SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+$'
if ! [[ "$VERSAO" =~ $SEMVER_RE ]]; then
  echo "recusado: versão precisa ser semver 2.0.0 (MAJOR.MINOR.PATCH): '$VERSAO'" >&2
  exit 1
fi

cd "$APP_DIR"

if [ "$HOTFIX" = 1 ]; then
  RAMO=$(git rev-parse --abbrev-ref HEAD)
  if [ "$RAMO" != "hotfix/$VERSAO" ]; then
    echo "recusado: --hotfix exige estar no ramo hotfix/$VERSAO (ramo atual: $RAMO)" >&2
    exit 1
  fi
fi

TAG="v$VERSAO"
if [ -n "$(git tag -l "$TAG")" ]; then
  echo "recusado: etiqueta $TAG já existe" >&2
  exit 1
fi

DIR_SAIDA="$APP_DIR/var/releases"
mkdir -p "$DIR_SAIDA"
# gerar_changelog_release.py/o RELEASE_MANIFEST.json são stdlib puro (json/argparse/subprocess): plain
# python3 basta, sem depender da venv do produto (que pode nem existir no ambiente que empacota).
PY=(python3)

echo "== 1/7 validação de versão: $VERSAO ($([ "$HOTFIX" = 1 ] && echo hotfix || echo normal))"

echo "== 2/7 rascunho de changelog"
ULTIMA_TAG=$(git describe --tags --abbrev=0 2>/dev/null || true)
INTERVALO="HEAD"
[ -n "$ULTIMA_TAG" ] && INTERVALO="$ULTIMA_TAG..HEAD"
CHANGELOG_DRAFT="$DIR_SAIDA/$VERSAO.changelog.md"
"${PY[@]}" "$AQUI/gerar_changelog_release.py" \
  --repo "$APP_DIR" --versao "$VERSAO" --range "$INTERVALO" --saida "$CHANGELOG_DRAFT" > /dev/null
echo "rascunho: $CHANGELOG_DRAFT (desde ${ULTIMA_TAG:-o início})"

echo "== 3/7 make check (escopo verde)"
CMD_CHECK=${PLAT_RELEASE_CHECK_CMD:-"make check"}
if ! (cd "$APP_DIR" && eval "$CMD_CHECK"); then
  echo "RELEASE RECUSADA: '$CMD_CHECK' falhou — nada foi empacotado nem assinado" >&2
  exit 2
fi

echo "== 4/7 make homolog"
CMD_HOMOLOG=${PLAT_RELEASE_HOMOLOG_CMD:-"make homolog"}
if ! (cd "$APP_DIR" && eval "$CMD_HOMOLOG"); then
  echo "RELEASE RECUSADA: '$CMD_HOMOLOG' falhou — nada foi empacotado nem assinado" >&2
  exit 3
fi

echo "== 5/7 empacotar"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
read -r -a ITENS <<< "${PLAT_PACOTE_ITENS:-app web db deploy docs install.sh Makefile requirements.txt VERSAO}"
for item in "${ITENS[@]}"; do
  [ -e "$APP_DIR/$item" ] && cp -a "$APP_DIR/$item" "$STAGE/$item"
done
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "sem-git")
QUANDO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
"${PY[@]}" -c "
import json
json.dump(
    {'versao': '$VERSAO', 'commit': '$COMMIT', 'quando': '$QUANDO', 'make_check': 'passou', 'make_homolog': 'passou'},
    open('$STAGE/RELEASE_MANIFEST.json', 'w'), indent=2, ensure_ascii=False,
)
"
PACOTE="$DIR_SAIDA/plat-$VERSAO.tar.gz"
rm -f "$PACOTE"
# --transform tira o prefixo './' que '-C "$STAGE" .' deixaria (senão publicar_release.sh não acha
# RELEASE_MANIFEST.json pelo nome exato dentro do tar)
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner --transform='s,^\./,,' -czf "$PACOTE" -C "$STAGE" .
SHA=$(sha256sum "$PACOTE" | cut -d' ' -f1)
echo "pacote: $PACOTE (sha256=$SHA)"

echo "== 6/7 assinar"
ASSINAR=${PLAT_ASSINAR_SCRIPT:-"$AQUI/assinar_pacote.sh"}
# APP_DIR explícito para ESTE subprocesso: assinar_pacote.sh precisa da SUA PRÓPRIA venv/deploy (item
# L7-16), que pode viver num repositório diferente do que está sendo empacotado (é o caso do teste
# deste item, com uma árvore git sintética); nunca herda o APP_DIR deste script por acidente.
APP_DIR="$(cd "$(dirname "$ASSINAR")/.." && pwd)" bash "$ASSINAR" "$PACOTE"

echo "== 7/7 etiqueta git + conferência changelog×etiqueta"
git tag -a "$TAG" -m "release $VERSAO"
if ! bash "$AQUI/conferir_changelog_releases.sh" > /dev/null 2>&1; then
  echo "AVISO: $TAG ainda não tem seção em CHANGELOG.md — cole $CHANGELOG_DRAFT lá antes de publicar" >&2
fi

echo
echo "PRONTO — pacote testado em homologação com este sha: $SHA"
echo "Falta a decisão humana: (1) revisar $CHANGELOG_DRAFT e colar em CHANGELOG.md; (2) publicar com"
echo "  bash scripts/publicar_release.sh $PACOTE"
echo "(publicar_release.sh recusa qualquer pacote — inclusive um assinado à mão — que não tenha o"
echo "RELEASE_MANIFEST.json com make_check/make_homolog aprovados DENTRO do próprio arquivo assinado.)"
