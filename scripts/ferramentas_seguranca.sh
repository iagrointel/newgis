#!/bin/bash
# Instala (idempotente) as ferramentas binárias listadas em deploy/ferramentas_binarias.txt em
# ~/.cache/plat/ferramentas (ou PLAT_FERRAMENTAS_DIR; cache do usuário, como ~/.cache/pip — fora do PATH): baixa o pacote de release, CONFERE o sha256 fixado na lista antes de
# extrair (pacote com sha diferente é apagado e o script sai com 3), extrai em <cache>/<nome>-<versão>/
# e aponta <cache>/bin/<nome> para o executável. Nunca escreve fora do cache, nunca
# toca /usr/local, PATH ou apt (item HARD-01; ADR de varredura contínua).
#
#   bash scripts/ferramentas_seguranca.sh            # instala o que falta
#   bash scripts/ferramentas_seguranca.sh gitleaks    # só uma
#   bash scripts/ferramentas_seguranca.sh --conferir  # não baixa nada: sai 1 se alguma falta ou está com versão diferente
#
# Saídas: 0 ok · 1 falta ferramenta (--conferir) · 2 lista ilegível/url fora do ar · 3 sha256 não confere.
set -euo pipefail
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
LISTA=$RAIZ/deploy/ferramentas_binarias.txt
DEST=${PLAT_FERRAMENTAS_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/plat/ferramentas}
CONFERIR=0; SO=""
for a in "$@"; do case "$a" in --conferir) CONFERIR=1;; *) SO=$a;; esac; done
[ -r "$LISTA" ] || { echo "ferramentas_seguranca: lista ausente: $LISTA" >&2; exit 2; }
mkdir -p "$DEST/bin" "$DEST/pacotes"
faltando=0
while read -r nome versao url sha caminho; do
  [ -z "$nome" ] && continue; case "$nome" in \#*) continue;; esac
  [ -n "$SO" ] && [ "$SO" != "$nome" ] && continue
  dir="$DEST/$nome-$versao"; exe="$dir/$caminho"; elo="$DEST/bin/$nome"
  if [ -x "$exe" ] && [ "$(readlink -f "$elo" 2>/dev/null || true)" = "$(readlink -f "$exe")" ]; then
    [ "$CONFERIR" = 1 ] || echo "  = $nome $versao já instalada"
    continue
  fi
  if [ "$CONFERIR" = 1 ]; then echo "  ! falta $nome $versao (rode scripts/ferramentas_seguranca.sh)" >&2; faltando=1; continue; fi
  pacote="$DEST/pacotes/$(basename "$url")"
  if [ ! -f "$pacote" ] || [ "$(sha256sum "$pacote" | cut -d' ' -f1)" != "$sha" ]; then
    echo "  v baixando $nome $versao ($url)"
    curl -fsSL --retry 3 -m 900 -o "$pacote.parte" "$url" || { echo "ferramentas_seguranca: download falhou: $url" >&2; rm -f "$pacote.parte"; exit 2; }
    mv "$pacote.parte" "$pacote"
  fi
  obtido=$(sha256sum "$pacote" | cut -d' ' -f1)
  if [ "$obtido" != "$sha" ]; then
    echo "ferramentas_seguranca: sha256 de $(basename "$pacote") NÃO confere: esperado $sha, obtido $obtido — pacote apagado" >&2
    rm -f "$pacote"; exit 3
  fi
  rm -rf "$dir"; mkdir -p "$dir"
  case "$pacote" in
    *.tar.gz|*.tgz) tar -xzf "$pacote" -C "$dir";;
    *.zip) unzip -q "$pacote" -d "$dir";;
    *) echo "ferramentas_seguranca: formato desconhecido: $pacote" >&2; exit 2;;
  esac
  [ -f "$exe" ] || { echo "ferramentas_seguranca: $caminho não existe dentro de $(basename "$pacote")" >&2; exit 2; }
  chmod +x "$exe"; ln -sfn "$exe" "$elo"
  echo "  + $nome $versao -> $elo (sha256 do pacote conferido)"
done < "$LISTA"
[ "$faltando" = 0 ] || exit 1
