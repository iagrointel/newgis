#!/bin/bash
# Item L0-14-identidade-visual, cláusulas (f) contraste AA e (g) captura antes/depois.
# A prova tem de ser REPETÍVEL: nenhuma imagem solta. Este script sobe as DUAS instâncias que o par
# antes/depois compara, roda tests/e2e/test_estilo.py contra elas e grava as medidas.
#
#   bash tests/e2e/regerar_capturas_L0-14.sh [<sha do "antes">] [<porta antes>] [<porta depois>]
#
# O "antes" é o commit ANTERIOR ao conserto (padrão: o pai do HEAD); o "depois" é a árvore de trabalho.
# As duas sobem com `tests.e2e.frente_estatica` (API + /static servido pelo próprio processo, sem nginx)
# e falam com o MESMO banco, para a única diferença entre as fotos ser o código da interface.
#
# Por que não a produção como "antes": plat.iagrointel.com roda código antigo cuja tela de entrada envia o
# formulário por GET — a senha vai parar na barra de endereço e o navegador do teste não consegue entrar.
# Está registrado como achado à parte; o par antes/depois não depende disso.
#
# Chromium: o do PLAYWRIGHT (~/.cache/ms-playwright). O `google-chrome` do sistema quebra nesta máquina
# (dumped core/crashpad); o do playwright é outro binário e funciona.
set -euo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SHA_ANTES=${1:-$(git -C "$RAIZ" rev-parse HEAD~1)}
PORTA_ANTES=${2:-8872}
PORTA_DEPOIS=${3:-8871}
ANTES_DIR=${PLAT_DIR_ANTES:-/home/dev/plataforma/wt/identantes}
URL_PUBLICA=${PLAT_URL_PUBLICA:-https://plat.iagrointel.com}

segredo() { sudo cat "/etc/plat/segredos/$1" 2>/dev/null || true; }
export PLAT_DSN=${PLAT_DSN:-$(segredo PLAT_DSN)}
export PLAT_SECRET=${PLAT_SECRET:-$(segredo PLAT_SECRET)}
[ -n "${PLAT_DSN:-}" ] || { echo "sem PLAT_DSN (rode como quem pode ler /etc/plat/segredos)" >&2; exit 2; }

subir() {  # <diretorio> <porta>
  ( cd "$1" && PLAT_URL_PUBLICA="$URL_PUBLICA" PLAT_DSN="$PLAT_DSN" PLAT_SECRET="$PLAT_SECRET" \
      "$RAIZ/venv/bin/python" -m uvicorn tests.e2e.frente_estatica:app \
      --host 127.0.0.1 --port "$2" --log-level warning ) &
  echo $!
  for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:$2/api/versao" >/dev/null && return 0
    sleep 1
  done
  echo "instância em :$2 não subiu" >&2; exit 3
}

if [ ! -d "$ANTES_DIR" ]; then
  git -C "$RAIZ" worktree add "$ANTES_DIR" --detach "$SHA_ANTES"
  ln -sfn "$RAIZ/venv" "$ANTES_DIR/venv"
  ln -sfn "$RAIZ/.env" "$ANTES_DIR/.env"
  ln -sfn "$RAIZ/tests/credenciais.txt" "$ANTES_DIR/tests/credenciais.txt"
fi

PID_ANTES=$(subir "$ANTES_DIR" "$PORTA_ANTES")
PID_DEPOIS=$(subir "$RAIZ" "$PORTA_DEPOIS")
trap 'kill '"$PID_ANTES $PID_DEPOIS"' 2>/dev/null || true' EXIT

echo "antes  :$PORTA_ANTES -> $(curl -s "http://127.0.0.1:$PORTA_ANTES/api/versao")"
echo "depois :$PORTA_DEPOIS -> $(curl -s "http://127.0.0.1:$PORTA_DEPOIS/api/versao")"

cd "$RAIZ"
# (g) "antes": só grava o que ainda não existe — o par sobrevive a um novo deploy do próprio item
PLAT_URL_ANTES="http://127.0.0.1:$PORTA_ANTES" PLAT_CREDENCIAIS_ANTES="$RAIZ/tests/credenciais.txt" \
  venv/bin/pytest tests/e2e/test_estilo.py::test_g_captura_antes_da_url_de_producao \
  --base-url="http://127.0.0.1:$PORTA_DEPOIS" -q -p no:cacheprovider

# (f) contraste AA + axe + (g) "depois", nos dois temas
PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/e2e/test_estilo.py \
  --base-url="http://127.0.0.1:$PORTA_DEPOIS" -q -p no:cacheprovider

ls -1 tests/e2e/capturas/L0-14_*.png | wc -l | xargs echo "capturas:"
