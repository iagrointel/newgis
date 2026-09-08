#!/bin/bash
# Traz o ramo de um worktree para master por fast-forward (rebase antes). Uso: merge_wt.sh <nome>
set -e
N=$1; WT=/home/dev/plataforma/wt/$N; MAIN=/home/dev/plataforma/enterprise
cd "$WT" && git rebase master
cd "$MAIN"
# só arquivos que o ramo muda e que estão sujos na árvore principal são risco
sujos=$(git status --porcelain | awk '{print $2}')
mudados=$(git diff --name-only master wt/$N)
conf=$(comm -12 <(echo "$sujos" | sort) <(echo "$mudados" | sort))
if [ -n "$conf" ]; then echo "CONFLITO com trabalho não commitado da árvore principal:"; echo "$conf"; exit 3; fi
git merge --ff-only wt/$N && git log -1 --oneline
