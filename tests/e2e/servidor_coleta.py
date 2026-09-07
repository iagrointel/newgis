"""Servidor da trilha para os e2e de coleta: a API + `web/` em /static (em produção o nginx serve web/ direto).
Uso: `venv/bin/uvicorn tests.e2e.servidor_coleta:app --port 85NN` com o ambiente da trilha carregado."""

from pathlib import Path

from starlette.staticfiles import StaticFiles

from app.main import app

app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "web")), name="static")
