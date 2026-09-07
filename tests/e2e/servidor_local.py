"""Servidor de e2e para UMA trilha (worktree), quando não há nginx na frente.

Em produção e em `make homolog` quem serve `web/` em `/static/` é o nginx (ADR 0001 seção 4.3), e a app
nunca monta arquivo estático. Numa trilha em worktree não há nginx: este módulo embrulha `app.main:app` e
acrescenta SÓ o `/static/`, para o playwright conseguir carregar os módulos JS da tela sob teste. Nada aqui
entra em produção — é o ponto de entrada do uvicorn do e2e da trilha, e não é importado pela app.

    /home/dev/plataforma/enterprise/venv/bin/python -m uvicorn tests.e2e.servidor_local:app --port 8161
"""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

WEB = Path(__file__).resolve().parents[2] / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")
