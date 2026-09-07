"""CORS aberto — e SÓ — nos caminhos de serviço geoespacial (`/svc`, `/ogc`, `/tiles`), item L2-04-b.

Por que aberto: um visualizador web de terceiro (Leaflet, OpenLayers, o Map Viewer da Esri, uma
página do próprio cliente) busca o FeatureServer pelo navegador, de outra origem. Sem cabeçalho de
CORS o navegador descarta a resposta e o mapa fica vazio — sem erro visível no servidor. E o segredo
não está na origem: nesses caminhos a credencial é o token, que vai na URL. Uma origem qualquer com
o token já teria o dado por `curl`; recusá-la no navegador não protege nada.

Por que NÃO em `/api`: lá a credencial é o cookie de sessão, que o navegador manda sozinho. CORS
aberto ali seria falsificação de requisição entre sítios com resposta legível. O middleware nunca
toca em caminho fora dos prefixos declarados, e nunca ecoa `Access-Control-Allow-Credentials`."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

PREFIXOS = ("/svc/", "/ogc/", "/tiles/")
METODOS = "GET, POST, OPTIONS"
CABECALHOS = "Authorization, Content-Type, X-Requested-With, X-Plat-Inquilino"
MAX_IDADE = "600"


def alcanca(caminho: str) -> bool:
    return caminho.startswith(PREFIXOS)


class CorsServicos(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        caminho = request.url.path
        if not alcanca(caminho):
            return await call_next(request)
        if request.method == "OPTIONS":
            resposta = Response(status_code=204)
        else:
            resposta = await call_next(request)
        resposta.headers["Access-Control-Allow-Origin"] = "*"
        resposta.headers["Access-Control-Allow-Methods"] = METODOS
        resposta.headers["Access-Control-Allow-Headers"] = CABECALHOS
        resposta.headers["Access-Control-Max-Age"] = MAX_IDADE
        resposta.headers["Vary"] = "Origin"
        return resposta


def instalar(app) -> None:
    app.add_middleware(CorsServicos)
