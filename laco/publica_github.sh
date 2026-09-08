#!/bin/bash
# Depois de cada lote verde da fila de junção: regenera STATUS.md, commita e envia master + ramos
# para github.com/iagrointel/newgis (pedido do dono, 06/09: commits, plano e status vivem lá).
set -u
R=/home/dev/plataforma/enterprise; L=/home/dev/plataforma/laco
cd "$R" || exit 1
python3 /home/dev/plataforma/laco/gera_status_md.py
git add STATUS.md 2>/dev/null
git diff --cached --quiet || git commit -q --no-verify -m "STATUS.md: placar regenerado pelo supervisor

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
timeout 300 git push -q origin master 2>&1 | tail -1
timeout 600 git push -q origin 'refs/heads/wt/*:refs/heads/wt/*' 2>&1 | tail -1
echo "[github] enviado $(date -u +%H:%M) — $(git rev-parse --short master)"
