#!/bin/bash
# Migracao da folha antiga web/style.css, uma leva por vez, com prova antes/depois.
# Molde: tests/e2e/regerar_capturas_L0-14.sh (item L0-14). O que muda aqui: o "antes" nao e a producao nem o
# commit pai qualquer - e a arvore ANTES desta leva, e as duas instancias falam com o banco da TRILHA desta
# worktree (schema plat_ttelas, criado por `bash laco/trilha_ambiente.sh telas`), nunca com o schema `plat` de
# producao: as telas desta migracao sao muitas e o banco de producao serve cliente pagante.
#
#   bash tests/e2e/regerar_capturas_migracao.sh <leva> [<sha do "antes">] [<porta antes>] [<porta depois>]
#
# Depois de rodar, tests/e2e/compara_migracao.py escreve o veredito da leva em tests/e2e/migracao_saida/.
#
# Chromium: o do PLAYWRIGHT (~/.cache/ms-playwright). NUNCA conter memoria com `ulimit -v` (o Chromium morre
# com SIGTRAP: enderecamento virtual nao e memoria); use
#   sudo systemd-run --scope --uid=dev --gid=dev -p MemoryMax=4G -p MemorySwapMax=0 <comando>
set -euo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
LEVA=${1:?leva (1..8; a lista esta em tests/e2e/telas_migracao.json)}
SHA_ANTES=${2:-$(git -C "$RAIZ" rev-parse HEAD)}
PORTA_ANTES=${3:-8872}
PORTA_DEPOIS=${4:-8871}
ANTES_DIR=${PLAT_DIR_ANTES:-/home/dev/plataforma/wt/telasantes}
ENV_TRILHA=${PLAT_ENV_TRILHA:-/home/dev/plataforma/laco/var/trilha/telas.env}

[ -f "$ENV_TRILHA" ] || { echo "sem $ENV_TRILHA (rode: bash laco/trilha_ambiente.sh telas)" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
source "$ENV_TRILHA"
set +a

subir() {  # <diretorio> <porta>
  ( cd "$1" && "$RAIZ/venv/bin/python" -m uvicorn tests.e2e.frente_estatica:app \
      --host 127.0.0.1 --port "$2" --log-level warning >/tmp/plat_mig_$2.log 2>&1 ) &
  echo $!
  for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:$2/api/versao" >/dev/null && return 0
    sleep 1
  done
  echo "instancia em :$2 nao subiu (veja /tmp/plat_mig_$2.log)" >&2; exit 3
}

if [ ! -d "$ANTES_DIR" ]; then
  git -C "$RAIZ" worktree add "$ANTES_DIR" --detach "$SHA_ANTES"
else
  # leva seguinte: o "antes" e o HEAD de agora, nao o de quando a worktree nasceu
  git -C "$ANTES_DIR" checkout --detach --force "$SHA_ANTES" >/dev/null 2>&1
fi
ln -sfn "$RAIZ/venv" "$ANTES_DIR/venv"

PID_ANTES=$(subir "$ANTES_DIR" "$PORTA_ANTES")
PID_DEPOIS=$(subir "$RAIZ" "$PORTA_DEPOIS")
trap 'kill '"$PID_ANTES $PID_DEPOIS"' 2>/dev/null || true' EXIT

echo "antes  :$PORTA_ANTES ($SHA_ANTES) -> $(curl -s "http://127.0.0.1:$PORTA_ANTES/api/versao")"
echo "depois :$PORTA_DEPOIS (arvore de trabalho) -> $(curl -s "http://127.0.0.1:$PORTA_DEPOIS/api/versao")"

cd "$RAIZ"
# Teto de memoria opcional (PLAT_LIMITE_MEM=4G): esta maquina ja derrubou o Postgres por falta de memoria.
# Nunca `ulimit -v` - o Chromium morre com SIGTRAP sob teto de enderecamento virtual.
rodar_fase() {  # <fase> <porta>
  if [ -n "${PLAT_LIMITE_MEM:-}" ]; then
    sudo systemd-run --scope --quiet --uid=dev --gid=dev \
      -p "MemoryMax=$PLAT_LIMITE_MEM" -p MemorySwapMax=0 \
      --setenv=HOME="$HOME" --setenv=PLAT_CREDENCIAIS_ARQUIVO="${PLAT_CREDENCIAIS_ARQUIVO:-}" \
      --setenv=PLAT_DSN="$PLAT_DSN" --setenv=PLAT_SECRET="$PLAT_SECRET" \
      --setenv=PLAT_URL_PUBLICA="$PLAT_URL_PUBLICA" \
      --setenv=PLAT_FASE="$1" --setenv=PLAT_LEVA="$LEVA" \
      "$RAIZ/venv/bin/pytest" tests/e2e/test_migracao_folha.py \
      --base-url="http://127.0.0.1:$2" -q -p no:cacheprovider
  else
    PLAT_FASE="$1" PLAT_LEVA="$LEVA" venv/bin/pytest tests/e2e/test_migracao_folha.py \
      --base-url="http://127.0.0.1:$2" -q -p no:cacheprovider
  fi
}

rodar_fase antes "$PORTA_ANTES"
rodar_fase depois "$PORTA_DEPOIS"

venv/bin/python tests/e2e/compara_migracao.py "$LEVA"
