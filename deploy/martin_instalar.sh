#!/bin/bash
# Instala o binário do Martin (item L2-01-b-martin-tiles-vetoriais): servidor de tiles vetoriais que fala
# direto com o PostGIS. Baixa o pacote fixo da release do GitHub, confere o sha256 do PACOTE inteiro contra
# o valor fixado abaixo (medido e fixado nesta máquina no dia da instalação; qualquer bit alterado no
# download — corrupção ou adulteração — reprova antes de o binário tocar o disco) e instala só o
# executável `martin` (musl, estático, sem dependência de glibc). MIT/Apache-2.0.
#
# Uso:  bash deploy/martin_instalar.sh <diretório de destino>      (ex.: /opt/plat/bin, ou APP_DIR/bin)
# Idempotente: se o binário já existe com a versão certa, não baixa de novo.
set -euo pipefail
VERSAO="1.15.0"
TAG="martin-v$VERSAO"
ARQUIVO="martin-x86_64-unknown-linux-musl.tar.gz"
URL="https://github.com/maplibre/martin/releases/download/$TAG/$ARQUIVO"
# sha256 do PACOTE .tar.gz inteiro (não do binário extraído), medido nesta máquina em 06/09/2026 a partir
# da própria release pública — ver docs/adr/0021-martin-binario-fixo.md.
SHA256_PACOTE="4db541da2b76fec89e2b5b6e9d0fb6daa6da7141ad91f58537ea33db2d288d61"

DESTINO=${1:?uso: martin_instalar.sh <diretório de destino do binário>}
BIN="$DESTINO/martin"

if [ -x "$BIN" ]; then
  ATUAL=$("$BIN" --version 2>/dev/null | awk '{print $2}')
  if [ "$ATUAL" = "$VERSAO" ]; then
    echo "martin $VERSAO já instalado em $BIN"
    exit 0
  fi
  echo "martin instalado é $ATUAL, esperado $VERSAO — reinstalando"
fi

mkdir -p "$DESTINO"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
echo "baixando $URL"
curl -fsSL -o "$TMP/$ARQUIVO" "$URL"
SHA_BAIXADO=$(sha256sum "$TMP/$ARQUIVO" | cut -d' ' -f1)
if [ "$SHA_BAIXADO" != "$SHA256_PACOTE" ]; then
  echo "sha256 do pacote não confere: esperado $SHA256_PACOTE, baixado $SHA_BAIXADO" >&2
  echo "download corrompido ou release alterada — instalação abortada" >&2
  exit 1
fi
tar -xzf "$TMP/$ARQUIVO" -C "$TMP" martin
install -m 0755 "$TMP/martin" "$BIN"
INSTALADO=$("$BIN" --version 2>/dev/null | awk '{print $2}')
[ "$INSTALADO" = "$VERSAO" ] || { echo "binário instalado relata versão $INSTALADO, esperado $VERSAO" >&2; exit 1; }
echo "martin $VERSAO instalado em $BIN (sha256 do pacote conferido: $SHA_BAIXADO)"
