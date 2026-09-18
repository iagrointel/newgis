#!/bin/bash
# Uma leva da migracao de folha, do inicio ao veredito. Complementa regerar_capturas_migracao.sh:
# aqui as duas instancias ja estao de pe (portas 8872 "antes" e 8871 "depois") e nao se sobe nem se
# derruba nada entre levas -- subir dois uvicorn por leva custava mais que a medida.
#
#   bash tests/e2e/leva.sh <leva> <sha do "antes">
#   PLAT_TELAS=nome,nome bash tests/e2e/leva.sh <leva> <sha>   (pedaco da leva; ver _telas_da_leva)
#
# Chromium do playwright. Teto de memoria por cgroup (systemd-run), NUNCA `ulimit -v`.
set -euo pipefail
RAIZ=/home/dev/plataforma/wt/telas
ANTES_DIR=/home/dev/plataforma/wt/telasantes
LEVA=${1:?leva}
SHA=${2:?sha do "antes"}
set -a; source /home/dev/plataforma/laco/var/trilha/telas.env; set +a
cd "$RAIZ"

git -C "$ANTES_DIR" checkout --detach --force "$SHA" >/dev/null 2>&1
# a instancia "antes" le web/ do disco a cada pedido (StaticFiles), entao trocar o checkout basta;
# o modulo python ja carregado nao muda, e a API nao e o que esta sendo medido.
curl -sf "http://127.0.0.1:8872/api/versao" >/dev/null || { echo "instancia 'antes' fora do ar" >&2; exit 3; }
curl -sf "http://127.0.0.1:8871/api/versao" >/dev/null || { echo "instancia 'depois' fora do ar" >&2; exit 3; }

fase() {
  sudo systemd-run --scope --quiet --uid="$(id -u)" --gid="$(id -g)" \
    -p MemoryMax=4G -p MemorySwapMax=0 \
    --setenv=HOME="$HOME" --setenv=PLAT_CREDENCIAIS_ARQUIVO="$PLAT_CREDENCIAIS_ARQUIVO" \
    --setenv=PLAT_DSN="$PLAT_DSN" --setenv=PLAT_SECRET="$PLAT_SECRET" \
    --setenv=PLAT_URL_PUBLICA="$PLAT_URL_PUBLICA" \
    --setenv=PLAT_FASE="$1" --setenv=PLAT_LEVA="$LEVA" --setenv=PLAT_TELAS="${PLAT_TELAS:-}" \
    "$RAIZ/venv/bin/pytest" tests/e2e/test_migracao_folha.py \
    --base-url="http://127.0.0.1:$2" -q -p no:cacheprovider 2>&1 | tail -6
}
fase antes 8872
fase depois 8871
venv/bin/python tests/e2e/compara_migracao.py "$LEVA"
