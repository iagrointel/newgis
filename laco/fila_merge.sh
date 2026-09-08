#!/bin/bash
# Fila de junção de ramos de worktree em master (laço PLATAFORMA ENTERPRISE).
#
#   fila_merge.sh entrar <ramo> <item> [item...]   grava o pedido em laco/vivo/merge/<ramo>.json
#   fila_merge.sh listar                           mostra a fila em ordem de chegada
#   fila_merge.sh sair <ramo>                      tira o ramo da fila
#   fila_merge.sh processar                        junta um lote (6 a 8) em master
#
# Serial: tudo dentro de flock laco/.merge.lock. A verificação do lote roda sob
# laco/.pytest.lock, para nunca coincidir com a suíte da árvore principal.
# Verde: avanço rápido em master. Vermelho: bisseção por metades, o culpado volta
# ao dono com laco/vivo/merge/<ramo>.REPROVADO.log e o resto do lote é juntado.
set -uo pipefail

LACO=/home/dev/plataforma/laco
MAIN=/home/dev/plataforma/enterprise
FILA=$LACO/vivo/merge
INTEGRA=${PLAT_FILA_INTEGRA:-/home/dev/plataforma/wt/integra}
RAMO_INTEGRA=${PLAT_FILA_RAMO_INTEGRA:-fila/integra}
ALVO=${PLAT_FILA_ALVO:-master}
LOTE_MAX=${PLAT_FILA_LOTE_MAX:-8}
LOTE_MIN=${PLAT_FILA_LOTE_MIN:-6}
CHECK=${PLAT_FILA_CHECK:-make check}
AGREGADOS=${PLAT_FILA_AGREGADOS:-make openapi}
# ramos reais com refutação aberta: a junção é do dono, a fila nunca os toca
PROTEGIDOS=${PLAT_FILA_PROTEGIDOS:-"wt/valida wt/amc wt/garage wt/stac"}

mkdir -p "$FILA/feitos" "$FILA/reprovados" "$LACO/vivo/leases"

# 06/09: msg escrevia em stdout, o MESMO canal que busca_culpado usa para DEVOLVER o nome do ramo
# culpado. O chamador capturava mensagem e nome juntos, e a fila criou um diretorio chamado
# "[fila] bissecao: metade A (wt". Mensagem de progresso vai para stderr; stdout e so valor de retorno.
msg() { echo "[fila] $*" >&2; }
erro() { echo "[fila] ERRO: $*" >&2; }
seguro() { echo "$1" | tr '/' '_'; }

protegido() {
  local r=$1 p
  for p in $PROTEGIDOS; do [ "$r" = "$p" ] && return 0; done
  return 1
}

# ---------------------------------------------------------------- entrar/listar
cmd_entrar() {
  local ramo=${1:-}; shift || true
  [ -n "$ramo" ] || { erro "uso: entrar <ramo> <item> [item...]"; exit 2; }
  [ $# -ge 1 ] || { erro "declare ao menos um item"; exit 2; }
  git -C "$MAIN" show-ref --verify --quiet "refs/heads/$ramo" || { erro "ramo inexistente: $ramo"; exit 2; }
  if protegido "$ramo" && [ "${PLAT_FILA_FORCA:-0}" != "1" ]; then
    erro "$ramo está na lista de protegidos (refutação aberta, junção do dono). Recusado."; exit 2
  fi
  local arvore
  arvore=$(git -C "$MAIN" worktree list --porcelain | awk -v r="refs/heads/$ramo" '
    /^worktree /{w=$2} /^branch /{if ($2==r) print w}')
  [ -n "$arvore" ] || arvore=$(pwd)
  ITENS="$*" RAMO="$ramo" ARVORE="$arvore" python3 - "$FILA/$ramo.json" <<'PY'
import json, os, sys, datetime, pathlib
alvo = pathlib.Path(sys.argv[1]); alvo.parent.mkdir(parents=True, exist_ok=True)
alvo.write_text(json.dumps({
    "ramo": os.environ["RAMO"],
    "itens": os.environ["ITENS"].split(),
    "arvore": os.environ["ARVORE"],
    "quando": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
PY
  msg "na fila: $ramo (itens: $*)"
}

cmd_sair() {
  local ramo=${1:-}
  [ -n "$ramo" ] || { erro "uso: sair <ramo>"; exit 2; }
  rm -f "$FILA/$ramo.json" && msg "fora da fila: $ramo"
}

# ordem de chegada, ramos protegidos fora
fila_ordenada() {
  python3 - "$FILA" "$PROTEGIDOS" <<'PY'
import json, pathlib, sys
raiz = pathlib.Path(sys.argv[1]); prot = set(sys.argv[2].split())
itens = []
for f in raiz.rglob("*.json"):
    if {"feitos", "reprovados"} & set(f.relative_to(raiz).parts):
        continue
    try: d = json.loads(f.read_text(encoding="utf-8"))
    except Exception: continue
    if d.get("ramo") in prot: continue
    itens.append((d.get("quando", ""), d.get("ramo", f.stem)))
for _, r in sorted(itens):
    print(r)
PY
}

cmd_listar() {
  local n=0 r
  while read -r r; do [ -n "$r" ] || continue; n=$((n+1)); echo "$n. $r"; done < <(fila_ordenada)
  [ "$n" -gt 0 ] || msg "fila vazia"
}

# ------------------------------------------------------- numeração de migração
# Dois casos: (a) numeração NNN_*.sql -> confere colisão do que o ramo ACRESCENTA
# contra o que a árvore de integração já tem; (b) carimbo de tempo 2026*.sql ->
# não há o que reconferir. Escreve o motivo em stdout e devolve 1 se colidir.
confere_migracoes() {
  local ramo=$1
  local base_files ramo_files novos
  base_files=$(git -C "$INTEGRA" ls-tree -r --name-only HEAD -- db/migracoes 2>/dev/null | xargs -r -n1 basename)
  ramo_files=$(git -C "$MAIN" ls-tree -r --name-only "$ramo" -- db/migracoes 2>/dev/null | xargs -r -n1 basename)
  novos=$(comm -13 <(echo "$base_files" | sort) <(echo "$ramo_files" | sort))
  # a família legada de três dígitos está FECHADA (brief, ADR 0014): arquivo novo com NNN_ reprova
  local tresdig
  tresdig=$(echo "$novos" | grep -E '^[0-9]{3}_' || true)
  if echo "$base_files$ramo_files" | grep -qE '^[0-9]{8}T[0-9]{4}'; then
    if [ -n "$tresdig" ]; then
      echo "carimbo de tempo em uso e o ramo acrescenta migração de três dígitos: $(echo "$tresdig" | tr '\n' ' ')"; return 1
    fi
    echo "carimbo de tempo em uso: nada a reconferir"; return 0
  fi
  # regime antigo (só três dígitos): colisão de número entre o ramo e o que já está na integração
  local f num choque=""
  while read -r f; do
    [ -n "$f" ] || continue
    num=${f%%_*}
    echo "$num" | grep -qE '^[0-9]{3}$' || continue
    local ja
    ja=$(echo "$base_files" | grep -E "^${num}_" || true)
    [ -n "$ja" ] && choque="$choque $f<->$ja"
  done <<< "$novos"
  if [ -n "$choque" ]; then
    echo "colisão de numeração de migração:$choque"; return 1
  fi
  echo "numeração livre"; return 0
}

# --------------------------------------------------------- montagem do lote
prep_integra() {
  git -C "$MAIN" worktree remove --force "$INTEGRA" >/dev/null 2>&1
  git -C "$MAIN" branch -D "$RAMO_INTEGRA" >/dev/null 2>&1
  git -C "$MAIN" worktree add -q -b "$RAMO_INTEGRA" "$INTEGRA" "$ALVO" || return 1
  # mesma montagem dos worktrees das trilhas: venv e .env são links para os do repositório
  ln -sfn "$MAIN/venv" "$INTEGRA/venv"
  ln -sfn "$MAIN/.env" "$INTEGRA/.env"
}

RAMO_PROBLEMA=""; MOTIVO_PROBLEMA=""
# monta_lote <ramo...>  0 = montou, 4 = ramo problemático em $RAMO_PROBLEMA
monta_lote() {
  RAMO_PROBLEMA=""; MOTIVO_PROBLEMA=""
  prep_integra || { erro "não consegui preparar $INTEGRA"; return 1; }
  local ramo tmp saida
  for ramo in "$@"; do
    saida=$(confere_migracoes "$ramo")
    if [ $? -ne 0 ]; then
      RAMO_PROBLEMA=$ramo; MOTIVO_PROBLEMA="$saida"; return 4
    fi
    msg "  $ramo: $saida"
    tmp="fila/tmp/$(seguro "$ramo")"
    git -C "$INTEGRA" branch -f "$tmp" "$ramo" >/dev/null 2>&1
    git -C "$INTEGRA" checkout -q "$tmp" || { RAMO_PROBLEMA=$ramo; MOTIVO_PROBLEMA="checkout falhou"; return 4; }
    if ! saida=$(git -C "$INTEGRA" rebase "$RAMO_INTEGRA" 2>&1); then
      git -C "$INTEGRA" rebase --abort >/dev/null 2>&1
      git -C "$INTEGRA" checkout -q "$RAMO_INTEGRA"
      RAMO_PROBLEMA=$ramo; MOTIVO_PROBLEMA="rebase sobre $RAMO_INTEGRA falhou:"$'\n'"$saida"; return 4
    fi
    git -C "$INTEGRA" checkout -q "$RAMO_INTEGRA"
    if ! saida=$(git -C "$INTEGRA" merge --ff-only "$tmp" 2>&1); then
      RAMO_PROBLEMA=$ramo; MOTIVO_PROBLEMA="avanço rápido recusado:"$'\n'"$saida"; return 4
    fi
    msg "  $ramo: juntado"
  done
  return 0
}

regenera_agregados() {
  local saida
  saida=$(cd "$INTEGRA" && eval "$AGREGADOS" 2>&1)
  if [ $? -ne 0 ]; then msg "agregados falharam (segue, o check julga):"; echo "$saida" | tail -5; return 0; fi
  local mudados
  # 06/09: `status --porcelain` lista TUDO que mudou, inclusive os elos `venv` e `.env` que a trilha
  # cria e que estao no .gitignore — e `git add <caminho>` FORCA a entrada de arquivo ignorado.
  # O primeiro lote comitou o elo `venv`, que aponta para um caminho absoluto desta maquina e
  # quebraria qualquer outro worktree. So entram os arquivos que a lista de agregados produz.
  mudados=$(git -C "$INTEGRA" status --porcelain | awk '{print $2}' \
            | grep -vxE 'venv|\.env|venv/.*' || true)
  if [ -n "$mudados" ]; then
    local a; for a in $mudados; do
      git -C "$INTEGRA" check-ignore -q "$a" && { msg "  ignorado (esta no .gitignore): $a"; continue; }
      git -C "$INTEGRA" add "$a"
    done
    git -C "$INTEGRA" commit -q -m "Agregados regerados pela fila de junção

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SyPMRBvMqaNjtymPz9Sihb" >/dev/null
    msg "  agregados num commit só: $(echo "$mudados" | tr '\n' ' ')"
  fi
}

# roda_check <arquivo de log>  -> 0 verde, 1 vermelho
# Por padrão a verificação usa o schema `plat` compartilhado, então roda sob
# laco/.pytest.lock — nunca ao mesmo tempo que a suíte da árvore principal. Se
# PLAT_FILA_ENV apontar para um ambiente de trilha próprio (laco/trilha_ambiente.sh
# integra -> laco/var/trilha/integra.env), a verificação usa aquele schema e dispensa a trava.
roda_check() {
  local log=$1
  msg "  verificando o lote: $CHECK"
  if [ -n "${PLAT_FILA_ENV:-}" ] && [ -f "$PLAT_FILA_ENV" ]; then
    ( cd "$INTEGRA" && set -a && . "$PLAT_FILA_ENV" && set +a && eval "$CHECK" ) >"$log" 2>&1
  else
    ( cd "$INTEGRA" && flock "$LACO/.pytest.lock" bash -c "$CHECK" ) >"$log" 2>&1
  fi
}

# busca_culpado <ramo...>  -> imprime o culpado; log da rodada final fica em $LOG_CULPADO
LOG_CULPADO=""
busca_culpado() {
  local -a lista=("$@")
  local n=${#lista[@]} log
  if [ "$n" -eq 1 ]; then LOG_CULPADO=$(mktemp); monta_lote "${lista[0]}"
    if [ $? -eq 4 ]; then printf '%s\n' "$MOTIVO_PROBLEMA" > "$LOG_CULPADO"; echo "${lista[0]}"; return 0; fi
    regenera_agregados; roda_check "$LOG_CULPADO"; echo "${lista[0]}"; return 0
  fi
  local meio=$(( n / 2 ))
  local -a a=("${lista[@]:0:$meio}") b=("${lista[@]:$meio}")
  log=$(mktemp)
  msg "bisseção: metade A (${a[*]})"
  monta_lote "${a[@]}"
  if [ $? -eq 4 ]; then printf '%s\n' "$MOTIVO_PROBLEMA" > "$log"; LOG_CULPADO=$log; echo "$RAMO_PROBLEMA"; return 0; fi
  regenera_agregados
  if roda_check "$log"; then
    msg "bisseção: metade A verde -> culpado está em B (${b[*]})"
    busca_culpado "${b[@]}"
  else
    msg "bisseção: metade A vermelha -> culpado está em A"
    busca_culpado "${a[@]}"
  fi
}

reprova() {
  local ramo=$1 log=$2 motivo=$3
  local destino="$FILA/$ramo.REPROVADO.log"
  mkdir -p "$(dirname "$destino")"
  { echo "ramo: $ramo"; echo "quando: $(date -Is)"; echo "motivo: $motivo";
    echo "comando: $CHECK"; echo "reproduza: cd $INTEGRA (recriado pela fila) ou no seu worktree";
    echo "---"; cat "$log" 2>/dev/null; } > "$destino"
  [ -f "$FILA/$ramo.json" ] && mv "$FILA/$ramo.json" "$FILA/reprovados/$(seguro "$ramo").$(date +%Y%m%d_%H%M%S).json"
  erro "REPROVADO $ramo -> $destino"
}

publica() {
  local sujos mudados conf checado
  checado=$(git -C "$MAIN" rev-parse --abbrev-ref HEAD)
  if [ "$checado" = "$ALVO" ]; then
    sujos=$(git -C "$MAIN" status --porcelain | awk '{print $2}' | sort)
    mudados=$(git -C "$MAIN" diff --name-only "$ALVO" "$RAMO_INTEGRA" | sort)
    conf=$(comm -12 <(echo "$sujos") <(echo "$mudados"))
    if [ -n "$conf" ]; then
      erro "conflito com trabalho não commitado da árvore principal:"; echo "$conf" >&2
      erro "o lote ficou no ramo $RAMO_INTEGRA e no worktree $INTEGRA; junte à mão quando limpar"
      return 3
    fi
    git -C "$MAIN" merge --ff-only "$RAMO_INTEGRA" || return 3
  else
    # alvo não está em nenhuma árvore de trabalho: avanço rápido pelo ref
    git -C "$MAIN" merge-base --is-ancestor "$ALVO" "$RAMO_INTEGRA" || { erro "$RAMO_INTEGRA não descende de $ALVO"; return 3; }
    git -C "$MAIN" branch -f "$ALVO" "$RAMO_INTEGRA" || return 3
  fi
  msg "$ALVO avançou: $(git -C "$MAIN" log -1 --oneline "$ALVO")"
  git -C "$MAIN" worktree remove --force "$INTEGRA" >/dev/null 2>&1
  git -C "$MAIN" branch -D "$RAMO_INTEGRA" >/dev/null 2>&1
  git -C "$MAIN" for-each-ref --format='%(refname:short)' 'refs/heads/fila/tmp/*' | while read -r t; do
    git -C "$MAIN" branch -D "$t" >/dev/null 2>&1; done
  return 0
}

cmd_processar() {
  local -a lote=()
  while read -r r; do [ -n "$r" ] || continue; lote+=("$r"); [ ${#lote[@]} -ge "$LOTE_MAX" ] && break; done < <(fila_ordenada)
  if [ ${#lote[@]} -eq 0 ]; then msg "fila vazia, nada a processar"; return 0; fi
  msg "lote de ${#lote[@]} (mínimo desejado $LOTE_MIN, teto $LOTE_MAX): ${lote[*]}"
  local rodada=0 log
  while [ ${#lote[@]} -gt 0 ]; do
    rodada=$((rodada+1)); log=$(mktemp)
    msg "rodada $rodada: montando ${lote[*]}"
    monta_lote "${lote[@]}"
    if [ $? -eq 4 ]; then
      reprova "$RAMO_PROBLEMA" /dev/null "$MOTIVO_PROBLEMA"
      local -a novo=(); local x; for x in "${lote[@]}"; do [ "$x" = "$RAMO_PROBLEMA" ] || novo+=("$x"); done
      lote=("${novo[@]}"); continue
    fi
    regenera_agregados
    if roda_check "$log"; then
      msg "lote verde em $rodada rodada(s)"
      publica || return 3
      local x; for x in "${lote[@]}"; do
        [ -f "$FILA/$x.json" ] && mv "$FILA/$x.json" "$FILA/feitos/$(seguro "$x").$(date +%Y%m%d_%H%M%S).json"
        rm -f "$FILA/$x.REPROVADO.log"
      done
      msg "juntados: ${lote[*]}"
      # 06/09, pedido do dono: cada lote verde vai para github.com/iagrointel/newgis com STATUS.md novo
      bash /home/dev/plataforma/laco/publica_github.sh >&2 || msg "aviso: envio ao GitHub falhou (o lote está em master)"
      return 0
    fi
    msg "lote vermelho; bisseção por metades sobre ${#lote[@]} ramos"
    local culpado; culpado=$(busca_culpado "${lote[@]}")
    local achou=0 x
    for x in "${lote[@]}"; do [ "$x" = "$culpado" ] && achou=1; done
    if [ "$achou" = 0 ]; then
      erro "bisseção devolveu algo que não é ramo do lote ($culpado); parando para não girar em falso"
      return 1
    fi
    reprova "$culpado" "${LOG_CULPADO:-$log}" "reprovou a verificação do lote ($CHECK)"
    local -a novo=(); for x in "${lote[@]}"; do [ "$x" = "$culpado" ] || novo+=("$x"); done
    lote=("${novo[@]}")
    [ ${#lote[@]} -eq 0 ] && { msg "nada sobrou do lote"; git -C "$MAIN" worktree remove --force "$INTEGRA" >/dev/null 2>&1; git -C "$MAIN" branch -D "$RAMO_INTEGRA" >/dev/null 2>&1; return 1; }
  done
}

case "${1:-}" in
  entrar) shift; cmd_entrar "$@" ;;
  sair) shift; cmd_sair "$@" ;;
  listar) cmd_listar ;;
  processar) shift; exec flock -w "${PLAT_FILA_ESPERA:-7200}" "$LACO/.merge.lock" bash -c 'PLAT_FILA_TRAVADO=1 "$0" _processar' "$0" ;;
  _processar) [ "${PLAT_FILA_TRAVADO:-0}" = "1" ] || { erro "use 'processar'"; exit 2; }; cmd_processar ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
