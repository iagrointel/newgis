"""Contrato de erro da API (ADR 0002 seção 14, decisão D18): toda resposta de erro é
{"erro": "<codigo_curto>", "mensagem": "<frase em português>", "detalhe": <opcional>, "req_id": "<16 hex>"}.
Quem levanta é `ErroAPI`; os dois handlers cobrem também o HTTPException do FastAPI (404 de rota, 405) e o
RequestValidationError (422 com a lista do pydantic). Outras trilhas importam daqui; nenhuma redefine."""

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


def corpo_erro(request: Request, erro: str, mensagem: str, detalhe: Any = None) -> dict:
    corpo = {"erro": erro, "mensagem": mensagem}
    if detalhe is not None:
        corpo["detalhe"] = detalhe
    corpo["req_id"] = getattr(request.state, "req_id", None)
    return corpo


async def tratar_http(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc, ErroAPI):
        corpo = corpo_erro(request, exc.erro, exc.mensagem, exc.detalhe)
    else:
        mensagem = exc.detail if isinstance(exc.detail, str) else MENSAGENS_HTTP.get(exc.status_code, "erro")
        if mensagem == "Not Found":
            mensagem = MENSAGENS_HTTP[404]
        elif mensagem == "Method Not Allowed":
            mensagem = MENSAGENS_HTTP[405]
        corpo = corpo_erro(request, CODIGOS_HTTP.get(exc.status_code, "erro"), mensagem)
    return JSONResponse(corpo, status_code=exc.status_code, headers=exc.headers)


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
        corpo_erro(request, "validacao", "pedido inválido: corpo ou parâmetros fora do esquema", detalhe),
        status_code=422,
    )


def instalar(app: FastAPI) -> None:
    # o roteador do Starlette levanta a SUA HTTPException no 404/405; a do FastAPI é subclasse dela
    app.add_exception_handler(HTTPExceptionStarlette, tratar_http)
    app.add_exception_handler(RequestValidationError, tratar_validacao)
