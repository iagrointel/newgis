#!/usr/bin/env bash
# Acrescenta uma chave pública de release à lista de confiança do produto
# (deploy/chaves_publicas_release.txt). É o ÚNICO caminho para confiar numa chave nova depois que a
# instalação já tem âncora — item L7-16, endurecimento de 06/09/2026 (ataque adversarial ao grupo G6).
#
# Por que existe: até 06/09 quem assinava registrava a própria chave pública no arquivo que o verificador
# consulta, o que fazia da assinatura uma autoafirmação (medido: pacote assinado por terceiro aceito pelo
# caminho padrão). A separação é a correção: assinar não confia; confiar é ato explícito de quem opera a
# instalação, com o material público na linha de comando, revisado em code review e commitado no git.
#
# Uso: bash scripts/confiar_chave_release.sh <chave_id> <chave_publica_base64> [nota...] --confirmo
#
# O par (chave_id, chave_publica_base64) sai do JSON de `scripts/assinar_pacote.sh` (campo "chave_id" e
# "publica_b64" do subcomando gerar-chave) ou de `venv/bin/python scripts/plat_assinatura.py gerar-chave`
# na máquina que corta o release. NUNCA copie chave PRIVADA para lugar nenhum.
set -euo pipefail
APP_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CONFIAVEIS="$APP_DIR/deploy/chaves_publicas_release.txt"
# Em ambiente declarado de desenvolvimento (PLAT_AMBIENTE=dev/teste/homolog) o alvo pode ser outro
# arquivo — é assim que a suíte exercita a rotação sem tocar na lista do produto. Em produção a variável
# é ignorada: a lista é sempre a do repositório.
AMBIENTE=$(printf '%s' "${PLAT_AMBIENTE:-}" | tr '[:upper:]' '[:lower:]')
case "$AMBIENTE" in
  dev|teste|test|homolog|homologacao)
    if [ -n "${PLAT_CHAVES_CONFIAVEIS:-}" ]; then
      CONFIAVEIS="$PLAT_CHAVES_CONFIAVEIS"
      echo "AVISO: ambiente declarado '$AMBIENTE' — escrevendo em $CONFIAVEIS" >&2
    fi
    ;;
  *)
    [ -n "${PLAT_CHAVES_CONFIAVEIS:-}" ] && echo "AVISO: PLAT_CHAVES_CONFIAVEIS ignorada em produção" >&2
    ;;
esac

CONFIRMO=0
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--confirmo" ]; then CONFIRMO=1; else ARGS+=("$arg"); fi
done
CHAVE_ID=${ARGS[0]:-}
PUBLICA=${ARGS[1]:-}
NOTA="${ARGS[*]:2}"

if [ -z "$CHAVE_ID" ] || [ -z "$PUBLICA" ]; then
  echo "uso: bash scripts/confiar_chave_release.sh <chave_id> <chave_publica_base64> [nota...] --confirmo" >&2
  exit 1
fi
if ! [[ "$CHAVE_ID" =~ ^k[0-9a-f]{16}$ ]]; then
  echo "recusado: chave_id '$CHAVE_ID' fora do formato k<16 hex>" >&2
  exit 1
fi
if [ "$CONFIRMO" != 1 ]; then
  echo "recusado: falta --confirmo. Confiar numa chave de release significa aceitar TODA atualização" >&2
  echo "assinada por ela. Confira o chave_id com quem corta o release por um canal fora deste, e só" >&2
  echo "então repita o comando com --confirmo." >&2
  exit 2
fi

# Confere que o material público é uma chave Ed25519 de verdade e que o id declarado é o dela (o id é o
# sha256 dos 32 bytes crus: id trocado por engano ou de propósito não passa daqui).
env PYTHONNOUSERSITE=1 "$APP_DIR/venv/bin/python" - "$CHAVE_ID" "$PUBLICA" "$CONFIAVEIS" "$NOTA" "$APP_DIR" <<'PY'
import base64
import importlib.util
import sys
from pathlib import Path

chave_id, publica_b64, confiaveis, nota = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
raiz = Path(sys.argv[5])
spec = importlib.util.spec_from_file_location("plat_assinatura", raiz / "scripts" / "plat_assinatura.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

try:
    raw = base64.b64decode(publica_b64, validate=True)
except Exception as e:  # noqa: BLE001
    print(f"recusado: chave pública não é base64 válido ({e})", file=sys.stderr)
    raise SystemExit(1)
if len(raw) != 32:
    print(f"recusado: chave Ed25519 tem 32 bytes, esta tem {len(raw)}", file=sys.stderr)
    raise SystemExit(1)
esperado = mod.chave_id_de(raw)
if esperado != chave_id:
    print(f"recusado: o id desta chave pública é {esperado}, não {chave_id}", file=sys.stderr)
    raise SystemExit(1)
existentes = mod.ler_chaves_confiaveis(confiaveis)
if chave_id in existentes:
    print(f"{chave_id} já era confiável em {confiaveis} — nada a fazer")
    raise SystemExit(0)
mod.escrever_linha_de_confianca(confiaveis, chave_id, publica_b64, nota)
print(f"{chave_id} acrescentada a {confiaveis} ({len(existentes) + 1} chave(s) confiável(is))")
PY

echo
echo "AÇÃO NECESSÁRIA: 'git add $CONFIAVEIS && git commit' e distribuir esta versão (assinada com a chave"
echo "ANTIGA) ANTES de assinar qualquer pacote de verdade com a chave nova — é assim que a rotação não"
echo "deixa nenhum appliance para trás (ADR 0007 seção 2)."
