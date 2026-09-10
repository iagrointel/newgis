"""Servidor de e2e para uma BASE DE TRILHA (item L2-01-l).

Em produção o nginx serve `web/` em `/static/` e repassa o resto à aplicação (ver `deploy/nginx.conf`),
então um `uvicorn app.main:app` sozinho devolve 404 em todo arquivo da interface e nenhuma tela do e2e
carrega. Este módulo é a MESMA aplicação com `/static` montado a partir do disco — nada mais. Serve só
para rodar o e2e sem tocar no nginx compartilhado da máquina:

    venv/bin/python -m uvicorn tests.e2e.servidor_local:app --port 8303

Nunca é usado em produção: lá quem serve o estático é o nginx, que faz cache e range request (o
mapa-base PMTiles depende disso) e não passa por Python.
"""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

RAIZ = Path(__file__).resolve().parents[2]
app.mount("/static", StaticFiles(directory=RAIZ / "web"), name="static-e2e")

__all__ = ["app"]
