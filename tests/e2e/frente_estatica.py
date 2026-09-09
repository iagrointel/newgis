"""Frente de teste para e2e sem nginx (base de trilha): a API de app.main mais `/static/` servido de web/ pelo
próprio processo, como o nginx faz em produção (ADR 0001 seção 4.3). Só para o navegador do playwright numa
trilha; nunca em produção (lá o nginx serve web/ do disco, com o Cache-Control dele).

    set -a; source laco/var/trilha/<nome>.env; set +a
    venv/bin/python -m uvicorn tests.e2e.frente_estatica:app --port <porta>
    venv/bin/pytest tests/e2e/test_plataforma.py --base-url http://127.0.0.1:<porta>

PLAT_URL_PUBLICA exige https:// (app/settings.py) e o CSRF de escrita sob cookie (app.auth.sessao) compara o
Origin do navegador com ela; o navegador manda `http://127.0.0.1:<porta>`, e o Chromium não deixa o playwright
reescrever Origin. Por isso esta frente troca o cabeçalho Origin pela URL pública antes de entregar à API —
exatamente o que o domínio real faz sozinho. Cookies `Secure` valem em http://127.0.0.1 (contexto seguro)."""

from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from app.main import app as api
from app.settings import settings

WEB = Path(__file__).resolve().parents[2] / "web"


class OrigemPublica:
    """ASGI: Origin presente -> Origin da URL pública (só a chave `origin`; o resto do pedido segue intacto)."""

    def __init__(self, interno):
        self.interno = interno

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            cabecalhos = [(k, v) for k, v in scope["headers"] if k != b"origin"]
            if any(k == b"origin" for k, _ in scope["headers"]):
                cabecalhos.append((b"origin", settings.PLAT_URL_PUBLICA.encode()))
            scope = {**scope, "headers": cabecalhos}
        await self.interno(scope, receive, send)


app = Starlette(
    routes=[
        Mount("/static", app=StaticFiles(directory=str(WEB)), name="static"),
        Mount("/", app=OrigemPublica(api)),
    ]
)
