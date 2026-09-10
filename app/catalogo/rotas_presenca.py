"""Rotas de presença em documento (item L5-13-edicao-concorrente):
  POST /api/itens/{id}/presenca            {"sessao": "<id da aba>", "no": "<id do nó ou null>", "sair": false}
                                            -> lista de quem está no documento (batimento a cada 5 s pelo cliente)
  GET  /api/itens/{id}/presenca            -> a mesma lista (sem batimento)
  GET  /api/itens/{id}/presenca/eventos    -> SSE: evento `presenca` com a lista a cada mudança
Quem pode ler o item entra na presença (RLS de plat.item: outro inquilino = 404 antes de qualquer registro)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import presenca
from app.catalogo.comum import item_ou_404, uuid_ok
from app.erros import ErroAPI

router = APIRouter(tags=["presenca"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}


class PresencaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessao: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    no: str | None = Field(default=None, max_length=26, pattern=r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
    sair: bool = False


def _item_legivel(cur, iid: str) -> None:
    item_ou_404(cur, iid)  # RLS: item de outro inquilino ou sem leitura = 404


@router.post("/api/itens/{id}/presenca", openapi_extra=LER)
def bater(id: str, corpo: PresencaEntrada, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        _item_legivel(cur, iid)
        lista = presenca.bater(cur, auth.tenant_id, iid, auth.usuario_id, auth.login, auth.nome, corpo.sessao,
                               corpo.no, sair=corpo.sair)
    return {"itens": lista, "expira_s": presenca.EXPIRA_S}


@router.get("/api/itens/{id}/presenca", openapi_extra=LER)
def listar(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        _item_legivel(cur, iid)
    return {"itens": presenca.listar(auth.tenant_id, iid), "expira_s": presenca.EXPIRA_S}


@router.get("/api/itens/{id}/presenca/eventos", openapi_extra=LER,
            responses={200: {"content": {"text/event-stream": {}}}})
async def eventos(id: str, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    from starlette.concurrency import run_in_threadpool

    def _checar():
        with db.db(auth.contexto()) as cur:
            _item_legivel(cur, iid)

    await run_in_threadpool(_checar)
    if not presenca.reservar(auth.tenant_id, auth.usuario_id):
        raise ErroAPI(429, "sse_limite", f"máximo de {presenca.POR_USUARIO_MAX} conexões de presença por usuário")
    return StreamingResponse(
        presenca.gerar(auth.tenant_id, iid, auth.usuario_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
