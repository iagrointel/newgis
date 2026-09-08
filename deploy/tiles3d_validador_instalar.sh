#!/usr/bin/env bash
# Instala o validador oficial de OGC 3D Tiles (3d-tiles-validator, Apache-2.0, do CesiumGS) numa pasta
# fora do repositório versionado (`var/tiles3d/`, que está no .gitignore), para os testes do item
# L2-09-c conferirem o tileset que a plataforma gera com uma ferramenta que NÃO é nossa.
#
# Não é dependência de produção: o gerador é Python puro (app/modelos3d/tiles3d.py) e a aplicação não
# executa Node em momento nenhum. Este script existe para a bancada de teste e para quem quiser repetir
# a conferência à mão. Sem ele, o teste do validador SALTA dizendo o motivo — nunca passa por omissão.
#
# Uso:  bash deploy/tiles3d_validador_instalar.sh
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSAO="0.6.1"
DESTINO="$RAIZ/var/tiles3d"

command -v npm >/dev/null || { echo "npm não encontrado nesta máquina" >&2; exit 1; }
mkdir -p "$DESTINO"
[ -f "$DESTINO/package.json" ] || echo '{"name":"plat-tiles3d","private":true}' > "$DESTINO/package.json"
npm install --prefix "$DESTINO" --no-audit --no-fund "3d-tiles-validator@$VERSAO"
echo "instalado em $DESTINO/node_modules/.bin/3d-tiles-validator"
"$DESTINO/node_modules/.bin/3d-tiles-validator" --help >/dev/null && echo "validador responde"
