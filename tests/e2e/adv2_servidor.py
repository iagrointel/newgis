"""Harness do adversário G2: sobe a aplicação com /static servido pelo próprio processo (em produção é o
nginx que serve web/); usado só para rodar o playwright fora do servidor de produção."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

RAIZ = Path(__file__).resolve().parents[2] / "web"
app.mount("/static", StaticFiles(directory=RAIZ), name="static")

# fixture do adversário: certificado autoassinado no harness local
