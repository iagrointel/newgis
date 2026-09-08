#!/bin/bash
# Lança UM agente no modelo do dono (Kimi K3) com o prompt já gerado do item.
# Uso: lanca_kimi.sh <id-do-item>
set -u
B=/home/dev/plataforma/laco; I=${1:?uso: lanca_kimi.sh <id>}
P="$B/vivo/prompts/$I.md"; [ -f "$P" ] || { echo "prompt ausente: $P (rode prompt_item.py $I)"; exit 2; }
mkdir -p "$B/vivo/logs"; L="$B/vivo/logs/kimi-$I-$(date +%H%M%S).log"
set -a; . "$B/var/kimi.env"; set +a; unset ANTHROPIC_API_KEY
EXTRA=$(cat <<'EOF'

--- ACRESCENTOS OBRIGATORIOS DO SUPERVISOR ---
Base propria, sem flock: `bash /home/dev/plataforma/laco/trilha_ambiente.sh <nome-curto>` e depois
`set -a; source /home/dev/plataforma/laco/var/trilha/<nome>.env; set +a; venv/bin/pytest ... -q`.
Apague o schema ao fim. NUNCA `db/migrar.sh` (recusa de worktree de proposito). NUNCA a suite contra o
schema `plat` de producao a partir de worktree. Em base de trilha NAO use `make teste`/`make openapi`/
`make e2e`: eles injetam os segredos de PRODUCAO por cima do seu ambiente — rode `venv/bin/pytest` direto.
`git add` por arquivo nomeado, nunca -A. Migracao nova com carimbo `YYYYMMDDTHHMM_<slug>.sql`.
Clausula que voce nao provar vira FRONTEIRA HONESTA no repasse, nunca item entregue.
Ao fechar: `python3 /home/dev/plataforma/laco/marcar_item.py <id> <entregue|parcial> "<prova>" <sha>`
e repasse em /home/dev/plataforma/laco/handoffs/T4/<id>.md.
Rodape do commit: Co-Authored-By: Kimi K3 <noreply@moonshot.ai>
EOF
)
setsid nohup "/home/dev/.local/bin/claude" -p "$(cat "$P")$EXTRA" --dangerously-skip-permissions \
  > "$L" 2>&1 < /dev/null &
echo "[kimi] $I lancado (pid $!) modelo=$ANTHROPIC_MODEL log=$L"
