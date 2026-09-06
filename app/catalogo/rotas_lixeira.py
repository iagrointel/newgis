"""Lixeira (ADR 0004 seção 9): as rotas ligam plat.lixeira = on na transação (única forma de a RLS mostrar item
apagado); restaurar mantém uuid, compartilhamentos, relações, versões e favoritos; esvaziar enfileira o job de expurgo
com dias = 0 e ids explícitos (o expurgo físico é o mesmo caminho do periódico)."""

import datetime

from fastapi import APIRouter, Request

from app import db, limites
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo.comum import item_json, item_ou_404, ligar_lixeira, registrar_evento, uuid_ok
from app.catalogo.modelos import EsvaziarEntrada, Item, JobCriado, Pagina
from app.catalogo.rotas_itens import _params_lista, carregar_varios, listar_ids
from app.erros import ErroAPI
from app.jobs import servico
from app.jobs.contexto import sessao_de

router = APIRouter(prefix="/api/lixeira", tags=["lixeira"])
X = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade|conteudo.apagar_tudo"}


def _expurga_em(j: dict) -> dict:
    if j.get("apagado_em"):
        dt = datetime.datetime.strptime(j["apagado_em"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
        j["expurga_em"] = iso(dt + datetime.timedelta(days=limites.LIXEIRA_DIAS))
    return j


@router.get("", response_model=Pagina, openapi_extra=X)
def listar(
    request: Request,
    limite: int | None = None,
    deslocamento: int | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    p = _params_lista(request, limite, deslocamento)
    p.pop("favoritos", None)
    if not auth.tem("conteudo.apagar_tudo"):
        p["meus"] = True
    with db.db(auth.contexto()) as cur:
        ligar_lixeira(cur)
        total, ids, proximo, _ = listar_ids(cur, auth, p, lixeira=True)
        itens = [_expurga_em(j) for j in carregar_varios(cur, ids, auth)]
    return {"total": total, "itens": itens, "proximo_cursor": proximo}


@router.post("/{id}/restaurar", response_model=Item, openapi_extra=X)
def restaurar(id: str, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        ligar_lixeira(cur)
        r = item_ou_404(cur, iid)
        if r["apagado_em"] is None:
            raise ErroAPI(409, "nao_esta_na_lixeira", "o item não está na lixeira")
        cur.execute("SELECT plat.item_lixeira(%s::uuid, false) AS ok", (iid,))
        if not cur.fetchone()["ok"]:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        registrar_evento(cur, request, "itens/restaurar", "item", iid, {"titulo": r["titulo"][:250]})
        return item_json(item_ou_404(cur, iid), auth)


@router.post("/esvaziar", response_model=JobCriado, status_code=202, openapi_extra=X)
def esvaziar(request: Request, corpo: EsvaziarEntrada | None = None, auth: Auth = autenticado("jobs.executar")):
    ids = [uuid_ok(x) for x in (corpo.ids if corpo and corpo.ids else [])]
    pediu_ids = bool(ids)
    with db.db(auth.contexto()) as cur:
        ligar_lixeira(cur)
        if ids:
            cur.execute("SELECT id FROM plat.item WHERE id = ANY (%s::uuid[]) AND apagado_em IS NOT NULL", (ids,))
        elif auth.tem("conteudo.apagar_tudo"):
            cur.execute("SELECT id FROM plat.item WHERE apagado_em IS NOT NULL")
        else:
            cur.execute("SELECT id FROM plat.item WHERE apagado_em IS NOT NULL AND dono_id = %s", (auth.usuario_id,))
        alvo = [str(r["id"]) for r in cur.fetchall()]
        if not auth.tem("conteudo.apagar_tudo"):
            cur.execute(
                "SELECT id FROM plat.item WHERE id = ANY (%s::uuid[]) AND dono_id = %s", (alvo, auth.usuario_id)
            )
            alvo = [str(r["id"]) for r in cur.fetchall()]
    # lista vazia NUNCA vira "tudo": se o pedido nomeou ids e nenhum deles resolveu (não existe, não está na
    # lixeira, é de outro inquilino ou de outro dono), o pedido é recusado em vez de virar expurgo do inquilino.
    if pediu_ids and not alvo:
        raise ErroAPI(404, "nenhum_item_na_lixeira", "nenhum dos itens informados está na lixeira deste usuário")
    if not alvo:
        raise ErroAPI(409, "lixeira_vazia", "a lixeira já está vazia")
    job = servico.criar(sessao_de(auth), "catalogo.lixeira_expurgar", {"dias": 0, "ids": alvo})
    with db.db(auth.contexto()) as cur:
        registrar_evento(cur, request, "lixeira/esvaziar", "item", None, {"job_id": job["id"], "itens": len(alvo)})
    return {"job_id": job["id"]}
