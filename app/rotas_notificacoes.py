"""Rotas de notificação interna (item L0-03-k): sino, lista, marcar lida, apagar.

`GET /api/notificacoes/contagem` é o que o sino da barra chama: uma contagem por índice parcial, medida em
`tests/medidas/L0-03-catalogo.json` (cláusula "sino consulta <= 20 ms" do portão). A segurança de linha da
tabela é por `usuario_id`: notificação de outro usuário não aparece na lista e não é alcançável por id (404).
"""

import datetime

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app import db, limites, notificacoes
from app.auth.comum import registrar_evento
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import uuid_ok
from app.erros import ErroAPI

router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class Contagem(Saida):
    nao_lidas: int


class ListaNotificacoes(Saida):
    total: int
    nao_lidas: int
    itens: list[dict]


class MarcarEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] | None = Field(default=None, max_length=limites.NOTIFICACOES_PAGINA_MAX)
    todas: bool = False


def _iso(v) -> str | None:
    return v.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if v else None


def _linha(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "tipo": r["tipo"],
        "titulo": r["titulo"],
        "corpo": r["corpo"],
        "url": r["url"],
        "alvo_tipo": r["alvo_tipo"],
        "alvo_id": r["alvo_id"],
        "criado_em": _iso(r["criado_em"]),
        "lida_em": _iso(r["lida_em"]),
    }


@router.get("/contagem", response_model=Contagem, openapi_extra=X)
def contagem(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O sino: só o número de não lidas."""
    with db.db(auth.contexto()) as cur:
        return {"nao_lidas": notificacoes.nao_lidas(cur, auth.usuario_id)}


@router.get("", response_model=ListaNotificacoes, openapi_extra=X)
def listar(
    limite: int = Query(20, ge=1, le=limites.NOTIFICACOES_PAGINA_MAX),
    deslocamento: int = Query(0, ge=0, le=10000),
    apenas_nao_lidas: bool = False,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    with db.db(auth.contexto()) as cur:
        onde = "usuario_id = %s" + (" AND lida_em IS NULL" if apenas_nao_lidas else "")
        cur.execute(f"SELECT count(*) AS n FROM plat.notificacao WHERE {onde}", (auth.usuario_id,))
        total = int(cur.fetchone()["n"])
        cur.execute(
            f"SELECT * FROM plat.notificacao WHERE {onde} ORDER BY criado_em DESC, id LIMIT %s OFFSET %s",
            (auth.usuario_id, limite, deslocamento),
        )
        itens = [_linha(r) for r in cur.fetchall()]
        return {"total": total, "nao_lidas": notificacoes.nao_lidas(cur, auth.usuario_id), "itens": itens}


@router.post("/lidas", response_model=Contagem, openapi_extra=X)
def marcar_lidas(corpo: MarcarEntrada, request: Request, auth: Auth = autenticado()):
    """Marca como lidas as notificações informadas, ou todas com `todas: true`. Lista vazia nunca é `todas`."""
    if corpo.todas == bool(corpo.ids):
        raise ErroAPI(422, "validacao", "informe ids OU todas (uma coisa só)")
    ids = [uuid_ok(x) for x in (corpo.ids or [])]
    with db.db(auth.contexto()) as cur:
        if corpo.todas:
            cur.execute(
                "UPDATE plat.notificacao SET lida_em = now() WHERE usuario_id = %s AND lida_em IS NULL",
                (auth.usuario_id,),
            )
        else:
            cur.execute(
                "UPDATE plat.notificacao SET lida_em = now() WHERE usuario_id = %s AND lida_em IS NULL "
                "AND id = ANY (%s::uuid[])",
                (auth.usuario_id, ids),
            )
        marcadas = cur.rowcount
        if not corpo.todas and marcadas == 0:
            cur.execute(
                "SELECT count(*) AS n FROM plat.notificacao WHERE usuario_id = %s AND id = ANY (%s::uuid[])",
                (auth.usuario_id, ids),
            )
            if int(cur.fetchone()["n"]) == 0:
                raise ErroAPI(404, "notificacao_inexistente", "nenhuma das notificações informadas é sua")
        if marcadas:
            registrar_evento(cur, request, "notificacoes/lida", "usuario", auth.usuario_id, {"marcadas": marcadas})
        return {"nao_lidas": notificacoes.nao_lidas(cur, auth.usuario_id), "marcadas": marcadas}


@router.delete("/{id}", status_code=204, response_class=Response, openapi_extra=X)
def apagar(id: str, auth: Auth = autenticado()):
    nid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        cur.execute("DELETE FROM plat.notificacao WHERE usuario_id = %s AND id = %s::uuid", (auth.usuario_id, nid))
        if cur.rowcount == 0:
            raise ErroAPI(404, "notificacao_inexistente", "notificação inexistente")
    return Response(status_code=204)
