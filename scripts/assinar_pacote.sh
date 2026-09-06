#!/usr/bin/env bash
# Assina um pacote de atualização do plat com Ed25519 (item L7-16-assinatura-pacote, ADR 0007 seção 2).
# Gera o par de chaves na primeira execução; a privada NUNCA entra no repositório (fica fora, no caminho
# de PLAT_CHAVE_PRIVADA).
#
# ⛔ ENDURECIDO em 06/09/2026 (ataque adversarial ao grupo G6, laudo em
# laco/handoffs/T3/ataque-g6-ADVERSARIO.md): quem assina NÃO escreve mais na lista de confiança. Antes,
# esta ferramenta acrescentava a própria chave pública nova em deploy/chaves_publicas_release.txt — o
# mesmo arquivo que scripts/verificar_pacote.sh consulta —, de modo que qualquer pessoa que a rodasse
# virava origem confiável (pacote forjado aceito pelo caminho PADRÃO, sem variável nenhuma). Hoje a
# escrita só acontece quando a lista está SEM NENHUMA CHAVE (âncora inicial de uma instalação que ainda
# não cortou release), com aviso em stderr; com âncora presente, confiar numa chave nova é o ato separado
# de scripts/confiar_chave_release.sh --confirmo, feito por quem opera a instalação, revisado e commitado.
#
# Uso: bash scripts/assinar_pacote.sh <arquivo> [<saida.sig>] [--versao X.Y.Z]
#
# Variáveis:
#   PLAT_CHAVE_PRIVADA      caminho da chave privada (PEM). Padrão: /etc/plat/chaves/release_ed25519_priv.pem
#                           como root, ou $HOME/.config/plat/chaves/release_ed25519_priv.pem como usuário
#                           comum — assinar é tarefa de quem corta o release, não do appliance.
#   PLAT_CHAVES_CONFIAVEIS  só em ambiente declarado de desenvolvimento (PLAT_AMBIENTE em
#                           dev/teste/homolog): arquivo de confiança alternativo para a REGISTRO da chave.
#                           Em produção é ignorada — a lista é sempre deploy/chaves_publicas_release.txt.
set -euo pipefail
# A raiz vem SEMPRE do arquivo que está rodando, nunca de APP_DIR do ambiente: senão apontar APP_DIR para
# outra árvore troca a lista de confiança inteira (achado 2 do laudo).
APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ARQUIVO=""
SAIDA=""
VERSAO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --versao) VERSAO=${2:?"--versao exige X.Y.Z"}; shift 2 ;;
    --versao=*) VERSAO=${1#--versao=}; shift ;;
    *) if [ -z "$ARQUIVO" ]; then ARQUIVO=$1; elif [ -z "$SAIDA" ]; then SAIDA=$1; fi; shift ;;
  esac
done
[ -n "$ARQUIVO" ] || { echo "uso: bash scripts/assinar_pacote.sh <arquivo> [<saida.sig>] [--versao X.Y.Z]" >&2; exit 1; }
SAIDA=${SAIDA:-"$ARQUIVO.sig"}
[ -f "$ARQUIVO" ] || { echo "arquivo não existe: $ARQUIVO" >&2; exit 1; }

if [ -n "${PLAT_CHAVE_PRIVADA:-}" ]; then
  CHAVE_PRIVADA="$PLAT_CHAVE_PRIVADA"
elif [ "$(id -u)" -eq 0 ]; then
  CHAVE_PRIVADA=/etc/plat/chaves/release_ed25519_priv.pem
else
  CHAVE_PRIVADA="$HOME/.config/plat/chaves/release_ed25519_priv.pem"
fi

CONFIAVEIS="$APP_DIR/deploy/chaves_publicas_release.txt"
AMBIENTE=$(printf '%s' "${PLAT_AMBIENTE:-}" | tr '[:upper:]' '[:lower:]')
case "$AMBIENTE" in
  dev|teste|test|homolog|homologacao)
    if [ -n "${PLAT_CHAVES_CONFIAVEIS:-}" ]; then
      CONFIAVEIS="$PLAT_CHAVES_CONFIAVEIS"
      echo "AVISO: ambiente declarado '$AMBIENTE' — registrando em $CONFIAVEIS (em produção seria" \
           "$APP_DIR/deploy/chaves_publicas_release.txt)" >&2
    fi
    ;;
  *)
    if [ -n "${PLAT_CHAVES_CONFIAVEIS:-}" ]; then
      echo "AVISO: PLAT_CHAVES_CONFIAVEIS ignorada (ambiente '${AMBIENTE:-nao-declarado}' vale como" \
           "produção); a lista de confiança é $CONFIAVEIS" >&2
    fi
    ;;
esac

PY=(env PYTHONNOUSERSITE=1 "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/plat_assinatura.py")

if [ ! -f "$CHAVE_PRIVADA" ]; then
  echo "== gerando par de chaves Ed25519 (primeira execução): $CHAVE_PRIVADA"
  "${PY[@]}" gerar-chave --chave-privada "$CHAVE_PRIVADA" --confiaveis "$CONFIAVEIS" \
    --nota "gerada em $(date -u +%Y-%m-%dT%H:%M:%SZ) por $(id -un)@$(hostname -s 2>/dev/null || echo host)"
fi

"${PY[@]}" assinar "$ARQUIVO" --chave-privada "$CHAVE_PRIVADA" --saida "$SAIDA" \
  --versao "$VERSAO" --quando "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "assinado: $SAIDA"
