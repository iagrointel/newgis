"""Modo somente-leitura/manutenção global e por inquilino (item L7-33-modo-somente-leitura; ADR deste item;
paridade com o `mode` do Portal e o site mode READ_ONLY do ArcGIS Server).

A bandeira vive em `plat.sistema` (chave/valor com quem/quando/motivo, escrita só pelas funções
`plat.modo_ligar/modo_desligar` via CLI `plat modo`, role do worker) e é lida AQUI pelo middleware:
todo verbo de escrita (POST/PUT/PATCH/DELETE) recebe 503 com `Retry-After` (RFC 9110 seção 10.2.3) e o
contrato de erro da casa (ADR 0002 seção 14 — é o "problem details" da plataforma: código curto, mensagem
em português, detalhe com motivo/escopo/desde/quem e req_id). Leitura, tiles e exportação (GET/HEAD)
nunca passam por aqui.

Isenções fixas, nunca bloqueadas:
- `/saude` e `/status`: o monitoramento tem de continuar vendo a plataforma durante a manutenção;
- `/api/modo`: a própria consulta do estado (é o que a faixa do front lê);
- `/api/login`, `/api/login/2fa`, `/api/login/ldap` e `/api/logout`: entrar e sair não são edição —
  no modo READ_ONLY do ArcGIS o usuário continua entrando para CONSULTAR; bloquear o login deixaria
  até o operador do lado de fora. A sessão grava linha em plat.sessao, mas isso é escrita de sistema,
  como a do worker: o modo barra a escrita do USUÁRIO nos dados, não a da própria plataforma.
- `POST /api/jobs` de tipo `somente_leitura` (hoje `catalogo.exportar_lista`): a hipótese do item
  manda a exportação continuar. O job só lê o catálogo e materializa um artefato no armazenamento;
  a fila também deixa esse tipo correr durante o modo (cláusula de `plat.job_pegar` na migração).
  Tipo desconhecido, corpo que não é JSON ou tipo comum (que altera dado) FECHAM: o 503 é a resposta
  segura e a rota nunca é chamada.

Escopo: global vence sempre; sem flag global, vale a do inquilino da credencial (cookie de sessão ou
Bearer). Pedido anônimo só enxerga o modo global — a rota segue e responde o 401/400 dela, como antes
(limitação declarada no ADR: sem credencial não há inquilino para resolver, e o modo por inquilino
mira o uso autenticado).

ASGI puro, não `@app.middleware("http")`: aqui também se LÊ o corpo (a isenção de `POST /api/jobs`
precisa do JSON), e o próprio repositório mediu que exceção durante a leitura do corpo dentro de
BaseHTTPMiddleware vira "400 There was an error parsing the body" genérica em vez da resposta do
contrato (app/limite_corpo.py, docstring). O padrão de drenar e reproduzir o `receive()` é o mesmo
de LimiteCorpoMiddleware; o corpo já chega limitado a 10 MiB porque limite_corpo é mais externo.

Instalado em app/main.py ANTES de app.auth.middleware.instalar(app): no empilhamento do Starlette o
middleware acrescentado por último é o mais externo, então este roda DEPOIS do de log — a escrita
bloqueada sai com X-Req-Id, Cache-Control e linha em plat.log_acesso com status 503 (a recusa fica
auditável no mesmo lugar de qualquer outra resposta). Erro aqui é RESPOSTA montada na hora, nunca
exceção: middleware de usuário fica fora do ExceptionMiddleware do Starlette (ver app/limite_corpo.py).
"""

import json
import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import db
from app.erros import ErroAPI, corpo_erro

log = logging.getLogger("plat.modo")

VERBOS_ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ISENTOS = frozenset(
    {
        "/saude",
        "/status",
        "/api/modo",
        "/api/login",
        "/api/login/2fa",
        "/api/login/ldap",
        "/api/logout",
    }
)
RETRY_AFTER_PADRAO_S = 300

router = APIRouter(tags=["modo"])


def estado(tenant_id: int | None) -> dict:
    """Estado efetivo do modo para o inquilino (None = anônimo: só o global)."""
    with db.db() as cur:
        cur.execute("SELECT plat.modo_ler(%s) AS m", (tenant_id,))
        return dict(cur.fetchone()["m"])


def _tenant_da_requisicao(request: Request) -> int | None:
    """Inquilino da credencial, quando houver; credencial ruim NÃO é assunto deste middleware
    (a rota responde o 401/400 dela como sempre respondeu)."""
    from app.auth import sessao

    try:
        auth = sessao.resolver(request)
    except ErroAPI:
        return None
    return auth.tenant_id if auth is not None else None


def _resposta_503(request: Request, m: dict) -> JSONResponse:
    retry = int(m.get("retry_after_s") or RETRY_AFTER_PADRAO_S)
    escopo = "a plataforma" if m.get("escopo") == "global" else "este inquilino"
    mensagem = f"{escopo} está em manutenção (somente leitura): {m.get('motivo')}"
    detalhe = {k: m.get(k) for k in ("motivo", "escopo", "desde", "quem", "tenant_id") if m.get(k) is not None}
    detalhe["retry_after_s"] = retry
    corpo = corpo_erro(request, "modo_manutencao", mensagem, detalhe)
    log.info(
        "escrita bloqueada pelo modo de manutenção: %s %s (%s)",
        request.method,
        request.url.path,
        m.get("motivo"),
    )
    return JSONResponse(corpo, status_code=503, headers={"Retry-After": str(retry)})


def _bloqueio(request: Request) -> JSONResponse | None:
    m = estado(_tenant_da_requisicao(request))
    return _resposta_503(request, m) if m.get("ativo") else None


async def _corpo_json_jobs(receive: Receive) -> tuple[object, Receive]:
    """Drena o corpo de POST /api/jobs e devolve (dados_json, receive de reprodução): a decisão de
    isenção precisa do JSON, mas a rota também — então o corpo lido é repassado íntegro adiante.
    dados=None quando o corpo não é JSON válido (fecha: a isenção não se prova)."""
    pedacos: list[Message] = []
    corpo = b""
    while True:
        mensagem = await receive()
        pedacos.append(mensagem)
        if mensagem["type"] != "http.request":
            break
        corpo += mensagem.get("body") or b""
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

    try:
        dados = json.loads(corpo or b"{}")
    except ValueError:
        dados = None
    return dados, receive_reproduzido


def _tipo_somente_leitura(dados: object) -> bool:
    """True só quando o tipo pedido existe no registro e é declarado `somente_leitura` (exportação:
    lê o catálogo e grava artefato, nunca altera dado do inquilino). Qualquer dúvida fecha."""
    from app.jobs.registro import REGISTRO

    if not isinstance(dados, dict):
        return False
    t = REGISTRO.get(dados.get("tipo") or "")
    return bool(t and t.somente_leitura)


class ModoMiddleware:
    """O bloqueio em si. ASGI puro pelo motivo no docstring do módulo (leitura de corpo + contrato
    de erro sob nosso controle, igual a LimiteCorpoMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        metodo, caminho = scope["method"], scope["path"]
        if metodo not in VERBOS_ESCRITA or caminho in ISENTOS:
            await self.app(scope, receive, send)
            return
        if caminho == "/api/jobs" and metodo == "POST":
            dados, receive = await _corpo_json_jobs(receive)
            if _tipo_somente_leitura(dados):
                await self.app(scope, receive, send)
                return
        bloqueio = await run_in_threadpool(_bloqueio, Request(scope))
        if bloqueio is not None:
            await bloqueio(scope, receive, send)
            return
        await self.app(scope, receive, send)


def instalar(app: FastAPI) -> None:
    app.add_middleware(ModoMiddleware)


@router.get("/api/modo", summary="estado do modo de manutenção (global ou do inquilino da sessão)")
def modo_estado(request: Request) -> dict:
    """Público e sempre 200: é o que a faixa do front consulta para mostrar o motivo da manutenção."""
    return estado(_tenant_da_requisicao(request))
