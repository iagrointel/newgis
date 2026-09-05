"""Favoritos por usuário (ADR 0004 seção 8.5): PUT/DELETE /api/favoritos/{item_id}; a RLS (WITH CHECK pode_ler)
recusa favoritar item sem acesso; GET = /api/itens?favoritos=true."""

import psycopg2
from fastapi import APIRouter, Request, Response

from app import db, limites
from app.auth.sessao import Auth, autenticado
from app.catalogo.comum import item_ou_404, registrar_evento, uuid_ok
from app.catalogo.modelos import Pagina
from app.catalogo.rotas_itens import _params_lista, carregar_varios, listar_ids
from app.erros import ErroAPI

router = APIRouter(prefix="/api/favoritos", tags=["favoritos"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}


@router.get("", response_model=Pagina, openapi_extra=X)
def listar(
    request: Request,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    p = _params_lista(request, limite, deslocamento)
    p["favoritos"] = True
    with db.db(auth.contexto()) as cur:
        total, ids, proximo, _ = listar_ids(cur, auth, p)
        return {"total": total, "itens": carregar_varios(cur, ids, auth), "proximo_cursor": proximo}


@router.put("/{item_id}", status_code=204, response_class=Response, openapi_extra=X)
def adicionar(item_id: str, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(item_id)
    try:
        with db.db(auth.contexto()) as cur:
            item_ou_404(cur, iid)
            cur.execute("SELECT count(*) AS n FROM plat.favorito WHERE usuario_id = %s", (auth.usuario_id,))
            if cur.fetchone()["n"] >= limites.FAVORITOS_POR_USUARIO:
                raise ErroAPI(
                    422, "limite_favoritos", f"no máximo {limites.FAVORITOS_POR_USUARIO} favoritos por usuário"
                )
            cur.execute(
                "INSERT INTO plat.favorito(usuario_id, item_id, tenant_id) VALUES (%s, %s::uuid, %s) "
                "ON CONFLICT DO NOTHING",
                (auth.usuario_id, iid, auth.tenant_id),
            )
            if cur.rowcount:
                registrar_evento(cur, request, "favoritos/adicionar", "item", iid)
    except psycopg2.errors.InsufficientPrivilege as e:
        raise ErroAPI(404, "item_inexistente", "item inexistente") from e
    return Response(status_code=204)


@router.delete("/{item_id}", status_code=204, response_class=Response, openapi_extra=X)
def remover(item_id: str, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(item_id)
    with db.db(auth.contexto()) as cur:
        cur.execute("DELETE FROM plat.favorito WHERE usuario_id = %s AND item_id = %s::uuid", (auth.usuario_id, iid))
        if cur.rowcount:
            registrar_evento(cur, request, "favoritos/remover", "item", iid)
    return Response(status_code=204)
