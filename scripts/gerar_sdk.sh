#!/usr/bin/env bash
# Gera (ou regenera) sdk/python/src/plat_gerado a partir de docs/openapi.json (item L7-08-b-sdk-python).
# Reprodutível por construção: a mesma docs/openapi.json + o mesmo sdk/python/config_geracao.yaml
# sempre produzem os MESMOS arquivos (tests/sdk/test_regeneracao.py confere isso gerando de novo
# num diretório temporário e comparando com o que está comitado). Nunca editar plat_gerado/ à mão.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
DESTINO=${1:-sdk/python/src/plat_gerado}
export PATH="$PWD/venv/bin:$PATH"
venv/bin/openapi-python-client generate \
    --path docs/openapi.json \
    --meta none \
    --output-path "$DESTINO" \
    --config sdk/python/config_geracao.yaml \
    --overwrite
echo "gerado em $DESTINO"
