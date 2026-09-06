#!/usr/bin/env bash
# Assina um pacote de atualização do plat com Ed25519 (item L7-16-assinatura-pacote, ADR 0007 seção 2).
# Gera o par de chaves na primeira execução; a privada NUNCA entra no repositório (fica fora, no caminho
# de PLAT_CHAVE_PRIVADA); a pública é registrada em deploy/chaves_publicas_release.txt para ser
# versionada no git por quem cortar o release. Funciona sem rede.
#
# Uso: bash scripts/assinar_pacote.sh <arquivo> [<saida.sig>]
#
# Variáveis (todas opcionais):
#   PLAT_CHAVE_PRIVADA    caminho da chave privada (PEM). Padrão: /etc/plat/chaves/release_ed25519_priv.pem
#                         como root, ou $HOME/.config/plat/chaves/release_ed25519_priv.pem como usuário
#                         comum — a assinatura é uma tarefa de quem corta o release, não do appliance.
#   PLAT_CHAVES_CONFIAVEIS  caminho do arquivo de chaves públicas versionado. Padrão: deploy/chaves_publicas_release.txt
set -euo pipefail
APP_DIR=${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
ARQUIVO=${1:?uso: bash scripts/assinar_pacote.sh <arquivo> [<saida.sig>]}
SAIDA=${2:-"$ARQUIVO.sig"}
[ -f "$ARQUIVO" ] || { echo "arquivo não existe: $ARQUIVO" >&2; exit 1; }

if [ -n "${PLAT_CHAVE_PRIVADA:-}" ]; then
  CHAVE_PRIVADA="$PLAT_CHAVE_PRIVADA"
elif [ "$(id -u)" -eq 0 ]; then
  CHAVE_PRIVADA=/etc/plat/chaves/release_ed25519_priv.pem
else
  CHAVE_PRIVADA="$HOME/.config/plat/chaves/release_ed25519_priv.pem"
fi
CONFIAVEIS=${PLAT_CHAVES_CONFIAVEIS:-"$APP_DIR/deploy/chaves_publicas_release.txt"}
PY=(env PYTHONNOUSERSITE=1 "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/plat_assinatura.py")

if [ ! -f "$CHAVE_PRIVADA" ]; then
  echo "== gerando par de chaves Ed25519 (primeira execução): $CHAVE_PRIVADA"
  "${PY[@]}" gerar-chave --chave-privada "$CHAVE_PRIVADA" --confiaveis "$CONFIAVEIS" \
    --nota "gerada em $(date -u +%Y-%m-%dT%H:%M:%SZ) por $(id -un)@$(hostname -s 2>/dev/null || echo host)"
  echo "chave pública registrada em $CONFIAVEIS"
  echo "AÇÃO NECESSÁRIA: 'git add $CONFIAVEIS && git commit' e distribuir essa versão ANTES de assinar" \
       "qualquer pacote de verdade com esta chave (rotação segura, ADR 0007 seção 2)"
fi

"${PY[@]}" assinar "$ARQUIVO" --chave-privada "$CHAVE_PRIVADA" --saida "$SAIDA"
echo "assinado: $SAIDA"
