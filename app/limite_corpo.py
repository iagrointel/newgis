"""Limite de tamanho de corpo por requisição, transversal a toda rota de API (item L0-12; ADR 0001 seção 12;
docs/CONTRATO_API.md seção "Limites"). Padrão `limites.CORPO_MAX_PADRAO_BYTES` (10 MiB) para tudo que comece
com `/api/`, `/svc/`, `/ogc/` ou `/tiles/`. PREFIXOS_ISENTOS tira a rota deste middleware inteiramente (hoje a
lista está vazia: nenhuma rota de upload existe ainda, multipart entra com o L0-11/L1-01-e) — de propósito,
porque a defesa daqui bufferiza o corpo em memória antes de repassá-lo (ver abaixo), o que é aceitável até o
limite padrão de 10 MiB mas SERIA ERRADO para os 2 GiB de `limites.CORPO_MAX_UPLOAD_BYTES`: a rota de upload
grande precisa aplicar o próprio teto em streaming, gravando em disco (L1-01-e), não bufferizado aqui.

ASGI puro, não `BaseHTTPMiddleware`: um `BaseHTTPMiddleware` que tentasse levantar exceção durante a leitura
do corpo esbarraria no `except Exception` genérico de `fastapi/routing.py` (que converte QUALQUER exceção
ali dentro em "400 There was an error parsing the body", medido nesta máquina) — a exceção nunca chegaria ao
middleware. Por isso a defesa acontece ANTES de chamar a aplicação: o corpo é lido e contado por completo
aqui (interrompendo a leitura assim que ultrapassa o limite) e só então repassado à aplicação por um
`receive()` de reprodução, ou nunca repassado se excedeu.
1. `Content-Length` presente e acima do limite -> 413 imediato, sem ler um byte do corpo.
2. corpo sem `Content-Length` (chunked) ou que mente sobre o próprio tamanho -> os bytes são contados
   conforme chegam pelo ASGI `receive()`; ao ultrapassar o limite a leitura para e responde 413 sem nunca
   invocar a aplicação (é a via que um adversário tentaria para escapar do cabeçalho declarado — ver
   docs/CONTRATO_API.md, refutação do item).

Instalado em app/main.py DEPOIS de app.auth.middleware.instalar(app): no empilhamento do Starlette o
middleware acrescentado por último fica mais externo e roda primeiro na entrada da requisição, então o corpo
grande é rejeitado antes de chegar ao middleware de log/sessão (sem log em plat.log_acesso para essa via —
rejeitar uma requisição maliciosa não pode depender do banco; fica um aviso no journal)."""

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import limites
from app.log import req_id as novo_req_id

log = logging.getLogger("plat.limites")

PREFIXOS_COM_LIMITE = ("/api/", "/svc/", "/ogc/", "/tiles/")
# upload de arquivo (L0-11; ADR 0006): POST /api/arquivos aplica o próprio teto (limites.ARQUIVO_BYTES_MAX) em
# streaming (app/rotas_arquivos.py), sem bufferizar o corpo aqui — é a rota que este comentário previa desde o
# L0-12. GET/DELETE do mesmo prefixo não têm corpo grande; ficarem isentos junto não muda nada para eles.
PREFIXOS_ISENTOS: tuple[str, ...] = ("/api/arquivos",)


def limite_para(caminho: str) -> int | None:
    """None = middleware não se aplica (páginas HTML, /static/ do nginx, ou rota isenta que cuida de si mesma)."""
    if not caminho.startswith(PREFIXOS_COM_LIMITE) or caminho.startswith(PREFIXOS_ISENTOS):
        return None
    return limites.CORPO_MAX_PADRAO_BYTES


async def _responder_413(send: Send, maximo: int) -> None:
    rid = novo_req_id()
    corpo = {
        "erro": "corpo_grande",
        "mensagem": f"corpo da requisição acima do limite de {maximo} bytes",
        "req_id": rid,
    }
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(dados)).encode()),
                (b"x-req-id", rid.encode()),
                (b"cache-control", b"no-store, must-revalidate"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": dados})
    log.warning("corpo_grande: rejeitado com req_id=%s maximo=%s", rid, maximo)


class LimiteCorpoMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        maximo = limite_para(scope["path"])
        if maximo is None:
            await self.app(scope, receive, send)
            return

        cabecalhos = dict(scope.get("headers") or [])
        cl = cabecalhos.get(b"content-length")
        if cl is not None:
            try:
                declarado = int(cl)
            except ValueError:
                declarado = None
            if declarado is not None and declarado > maximo:
                await _responder_413(send, maximo)
                return

        # drena e conta o corpo INTEIRO antes de chamar a aplicação (nunca repassa por partes): é a única forma
        # de garantir um 413 limpo quando não há Content-Length (chunked) ou quando ele mente sobre o tamanho —
        # ver o docstring do módulo sobre por que levantar exceção durante a leitura do FastAPI não funciona.
        total = 0
        pedacos: list[Message] = []
        while True:
            mensagem = await receive()
            if mensagem["type"] != "http.request":
                pedacos.append(mensagem)
                break
            total += len(mensagem.get("body") or b"")
            pedacos.append(mensagem)
            if total > maximo:
                await _responder_413(send, maximo)
                return
            if not mensagem.get("more_body", False):
                break

        indice = 0

        async def receive_reproduzido() -> Message:
            nonlocal indice
            if indice < len(pedacos):
                mensagem = pedacos[indice]
                indice += 1
                return mensagem
            return await receive()  # raro: disconnect chegando depois do fim do corpo

        await self.app(scope, receive_reproduzido, send)


def instalar(app) -> None:
    app.add_middleware(LimiteCorpoMiddleware)
