"""Contrato de erro da API (ADR 0002 seção 14, decisão D18): toda resposta de erro é
{"erro": "<codigo_curto>", "mensagem": "<frase em português>", "detalhe": <opcional>, "req_id": "<16 hex>"}.
Quem levanta é `ErroAPI`; os dois handlers cobrem também o HTTPException do FastAPI (404 de rota, 405) e o
RequestValidationError (422 com a lista do pydantic). Outras trilhas importam daqui; nenhuma redefine.

Item L7-08-d (ADR 0018): a mesma resposta passou a ser também um Problem Details da RFC 9457 — tipo de
conteúdo `application/problem+json` e os membros `type`, `title`, `status`, `detail` e `instance`. Isto é
ACRÉSCIMO, não troca: `erro`, `mensagem`, `detalhe` e `req_id` continuam onde estavam, como membros de
extensão (a RFC 9457 seção 3.2 admite membros de extensão), e nenhum cliente da casa precisou mudar. O
motivo de acrescentar: a chave de API é consumida por programa de terceiro, e `type`/`status` é o que
biblioteca de cliente sabe ler sem conhecer o vocabulário da casa. `type` é uma URN estável por código de
erro (`urn:plat:erro:<codigo>`), nunca uma URL que alguém precise buscar."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as HTTPExceptionStarlette

MENSAGENS_HTTP = {
    400: "pedido inválido",
    401: "autenticação necessária",
    403: "sem permissão",
    404: "recurso inexistente",
    405: "método não permitido",
    409: "conflito",
    410: "recurso expirado",
    415: "tipo de conteúdo não aceito",
    422: "pedido inválido",
    423: "bloqueado",
    429: "muitas tentativas; aguarde",
    503: "serviço indisponível",
}
CODIGOS_HTTP = {
    400: "pedido_invalido",
    401: "nao_autenticado",
    403: "sem_permissao",
    404: "nao_encontrado",
    405: "metodo_nao_permitido",
    409: "conflito",
    410: "expirado",
    415: "tipo_nao_aceito",
    422: "validacao",
    423: "bloqueado",
    429: "muitas_tentativas",
    503: "indisponivel",
}


class ErroAPI(HTTPException):
    """Erro com código curto; `detalhe` é livre (lista, dicionário) e só aparece quando informado."""

    def __init__(
        self,
        status: int,
        erro: str,
        mensagem: str | None = None,
        detalhe: Any = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status, detail=mensagem or MENSAGENS_HTTP.get(status, "erro"), headers=headers)
        self.erro = erro
        self.mensagem = self.detail
        self.detalhe = detalhe


TIPO_PROBLEMA = "application/problem+json"
URN_ERRO = "urn:plat:erro:"


def corpo_erro(request: Request, erro: str, mensagem: str, detalhe: Any = None, status: int = 400) -> dict:
    """Problem Details da RFC 9457 com os quatro campos da casa como membros de extensão (ver o cabeçalho)."""
    corpo = {
        "type": URN_ERRO + erro,
        "title": MENSAGENS_HTTP.get(status, "erro"),
        "status": status,
        "detail": mensagem,
        "instance": request.url.path,
        "erro": erro,
        "mensagem": mensagem,
    }
    if detalhe is not None:
        corpo["detalhe"] = detalhe
    corpo["req_id"] = getattr(request.state, "req_id", None)
    return corpo


async def tratar_http(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc, ErroAPI):
        corpo = corpo_erro(request, exc.erro, exc.mensagem, exc.detalhe, exc.status_code)
    else:
        mensagem = exc.detail if isinstance(exc.detail, str) else MENSAGENS_HTTP.get(exc.status_code, "erro")
        if mensagem == "Not Found":
            mensagem = MENSAGENS_HTTP[404]
        elif mensagem == "Method Not Allowed":
            mensagem = MENSAGENS_HTTP[405]
        corpo = corpo_erro(request, CODIGOS_HTTP.get(exc.status_code, "erro"), mensagem, status=exc.status_code)
    return JSONResponse(corpo, status_code=exc.status_code, headers=exc.headers, media_type=TIPO_PROBLEMA)


async def tratar_validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    detalhe = []
    for e in exc.errors():
        item = {
            "campo": ".".join(str(p) for p in e.get("loc", ())),
            "erro": e.get("msg", ""),
            "tipo": e.get("type", ""),
        }
        detalhe.append(item)
    return JSONResponse(
        corpo_erro(request, "validacao", "pedido inválido: corpo ou parâmetros fora do esquema", detalhe, 422),
        status_code=422,
        media_type=TIPO_PROBLEMA,
    )


def instalar(app: FastAPI) -> None:
    # o roteador do Starlette levanta a SUA HTTPException no 404/405; a do FastAPI é subclasse dela
    app.add_exception_handler(HTTPExceptionStarlette, tratar_http)
    app.add_exception_handler(RequestValidationError, tratar_validacao)
