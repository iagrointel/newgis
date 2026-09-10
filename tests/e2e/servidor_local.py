"""ASGI de TESTE: a aplicação do plat mais `/static` servido pelo próprio processo.

Por que existe: em produção e em homologação quem serve `web/` em `/static/` é o nginx (ver o comentário do
`scripts/homolog_e2e.sh`, achado do 1º turno). Uma trilha em worktree não tem nginx próprio, e mexer no nginx
da máquina é compartilhado — então, só para o e2e da trilha, a mesma pasta é montada aqui. Nada disto entra
na aplicação de produção: `app/main.py` continua sem `StaticFiles`.

  venv/bin/uvicorn tests.e2e.servidor_local:app --port <porta da trilha>
"""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app

WEB = Path(__file__).resolve().parents[2] / "web"
app.mount("/static", StaticFiles(directory=str(WEB)), name="estatico_de_teste")
