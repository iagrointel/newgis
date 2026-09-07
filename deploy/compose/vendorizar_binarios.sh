#!/usr/bin/env bash
# Copia para dentro do contexto de build do repositório os binários/arquivos que já existem em produção
# nesta máquina e que as imagens do perfil `appliance` reaproveitam em vez de baixar de novo (item
# L7-01-a-compose-perfis; disco a 95-96% no dia deste item — nunca baixa imagem oficial do Garage/Martin).
#
# Rode ANTES de `docker compose ... build`: o Dockerfile não alcança caminho fora do diretório de build
# (deploy/compose/vendor/ fica FORA do git — ver .gitignore desta pasta — porque são binários de host,
# não fonte do repositório).
set -euo pipefail
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEST="$AQUI/vendor"
mkdir -p "$DEST"

GARAGE_BIN=${GARAGE_BIN:-/home/dev/plataforma/pipeline/bin/garage}
MARTIN_BIN=${MARTIN_BIN:-/usr/local/bin/martin}
TITILER_APP=${TITILER_APP:-/home/dev/plataforma/pipeline/app.py}

for par in "GARAGE_BIN:$GARAGE_BIN:garage" "MARTIN_BIN:$MARTIN_BIN:martin" "TITILER_APP:$TITILER_APP:titiler_app.py"; do
  var=${par%%:*}; resto=${par#*:}; origem=${resto%%:*}; alvo=${resto#*:}
  if [ ! -e "$origem" ]; then
    echo "AUSENTE: $var não achado em $origem (confira a máquina) — appliance sem esta peça" >&2
    continue
  fi
  cp -f "$origem" "$DEST/$alvo"
  echo "vendorizado: $origem -> deploy/compose/vendor/$alvo ($(du -h "$DEST/$alvo" | cut -f1))"
done
