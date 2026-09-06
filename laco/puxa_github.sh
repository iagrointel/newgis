#!/bin/bash
# Modelo híbrido: puxa do GitHub os ramos wt/* que nasceram FORA do servidor, cria worktree local e enfileira.
set -u
R=/home/dev/plataforma/enterprise; W=/home/dev/plataforma/wt; L=/home/dev/plataforma/laco
cd "$R" || exit 1
timeout 120 git fetch -q origin 2>&1 | tail -1
novos=0
for ref in $(git for-each-ref --format='%(refname:short)' 'refs/remotes/origin/wt/*'); do
  ramo=${ref#origin/}; nome=${ramo#wt/}
  if git show-ref --verify --quiet "refs/heads/$ramo"; then
    # ramo já existe localmente: se o remoto avançou, avisa (não sobrescreve trabalho local)
    l=$(git rev-parse "$ramo"); r=$(git rev-parse "$ref")
    if [ "$l" != "$r" ] && git merge-base --is-ancestor "$l" "$r"; then
      # 06/09: segunda versão do mesmo ramo vinda de fora ANTES só imprimia aviso e não entrava na fila.
      # Agora: se o worktree local está limpo, avança rápido e reenfileira; se tem trabalho local, avisa.
      if [ -d "$W/$nome" ] && [ -z "$(git -C "$W/$nome" status --porcelain | grep -vE 'venv|\.env')" ]; then
        git -C "$W/$nome" merge -q --ff-only "$ref" && bash "$L/fila_merge.sh" entrar "$ramo" "$nome" >/dev/null 2>&1 \
          && echo "[puxa] $ramo atualizado do remoto (${r:0:7}) e reenfileirado" && novos=$((novos+1))
      else
        echo "[puxa] $ramo avançou no remoto (${r:0:7}) mas o worktree local tem trabalho não commitado — não toquei"
      fi
    fi
    continue
  fi
  git branch -q --track "$ramo" "$ref" && git worktree add -q "$W/$nome" "$ramo" 2>/dev/null \
    && ln -sfn "$R/venv" "$W/$nome/venv" && ln -sfn "$R/.env" "$W/$nome/.env" \
    && bash "$L/fila_merge.sh" entrar "$ramo" "${nome}" >/dev/null 2>&1 \
    && echo "[puxa] novo: $ramo -> worktree $W/$nome, enfileirado" && novos=$((novos+1))
done
echo "[puxa] $(date -u +%H:%M) — $novos ramo(s) novo(s) do GitHub"
