#!/usr/bin/env bash
# Publica (instala) um pacote de release já preparado por scripts/preparar_release.sh — a decisão humana que
# aquele script deixa em aberto (item L7-15-processo-release, docs/RELEASE.md). Recusa (saída != 0) sempre
# que o pacote não prova, por si só, que passou pela linha inteira:
#   4  assinatura não confere (scripts/verificar_pacote.sh, item L7-16 — pacote alterado ou chave desconhecida)
#   5  sem RELEASE_MANIFEST.json dentro do pacote (não foi gerado por preparar_release.sh)
#   6  RELEASE_MANIFEST.json presente mas não diz make_check/make_homolog = "passou"
# O manifesto viaja DENTRO do arquivo que a assinatura cobre (Ed25519 assina os bytes inteiros do .tar.gz):
# forjar "passou por homologação" sem a chave privada do release é impossível — só reassinar o arquivo
# INTEIRO faria a assinatura bater de novo, e só quem corta o release tem a chave.
#
# Uso: bash scripts/publicar_release.sh <pacote.tar.gz>
set -euo pipefail
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
PACOTE=${1:?"uso: bash scripts/publicar_release.sh <pacote.tar.gz>"}
[ -f "$PACOTE" ] || { echo "recusado: pacote não existe: $PACOTE" >&2; exit 1; }

VERIFICAR=${PLAT_VERIFICAR_SCRIPT:-"$APP_DIR/scripts/verificar_pacote.sh"}
# APP_DIR explícito para ESTE subprocesso, mesmo cuidado de preparar_release.sh: verificar_pacote.sh
# precisa da SUA PRÓPRIA venv/deploy (item L7-16), nunca herdar o APP_DIR deste script por acidente.
if ! APP_DIR="$(cd "$(dirname "$VERIFICAR")/.." && pwd)" bash "$VERIFICAR" "$PACOTE"; then
  echo "RECUSADO: assinatura não confere para $PACOTE (o pacote pode ter sido alterado, ou a chave que" >&2
  echo "assinou não é confiável nesta versão)" >&2
  exit 4
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if ! tar -xzf "$PACOTE" -C "$TMP" RELEASE_MANIFEST.json 2>/dev/null; then
  echo "RECUSADO: $PACOTE não tem RELEASE_MANIFEST.json — não passou por scripts/preparar_release.sh" >&2
  echo "(assinatura válida sozinha não basta: sem o manifesto não há prova de que rodou make check/homolog)" >&2
  exit 5
fi

OK=$(env PYTHONNOUSERSITE=1 python3 -c "
import json
try:
    m = json.load(open('$TMP/RELEASE_MANIFEST.json'))
except Exception:
    print('0'); raise SystemExit
print('1' if m.get('make_check') == 'passou' and m.get('make_homolog') == 'passou' else '0')
" 2>/dev/null || echo 0)
if [ "$OK" != "1" ]; then
  echo "RECUSADO: RELEASE_MANIFEST.json presente mas não confirma make_check/make_homolog aprovados ($PACOTE)" >&2
  exit 6
fi

SHA=$(sha256sum "$PACOTE" | cut -d' ' -f1)
echo "aprovado para produção: $PACOTE (sha256=$SHA)"
echo "próximo passo humano: extrair sobre o diretório de produção e rodar install.sh <dominio> [porta] de lá"
echo "(este script não roda install.sh sozinho: instalar em produção de verdade é sempre decisão humana"
echo "explícita, e install.sh exige root/domínio que este comando não tem contexto para escolher por você)"
