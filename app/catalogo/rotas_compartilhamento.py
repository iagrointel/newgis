"""Compartilhamento (ADR 0004 seção 6): estado inteiro em GET/PUT /api/itens/{id}/compartilhamento (acesso, grupos,
destaques, aplicar a dependências — nunca em silêncio), links por token (64 hex, só o sha256 no banco, revogável,
validade ≤ 365 d, contagem de acessos), leitura anônima por /api/compartilhado/{token} (404 revogado/inexistente,
410 expirado, sem cache), leitura pública por /api/publico/itens/{id} (só com o inquilino autorizando) e a URL
assinada de objeto (/api/objetos/{chave}) do adaptador local."""

import datetime
import hashlib
import secrets

import psycopg2
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import db, limites, objetos
from app.auth.sessao import Auth, autenticado, iso
from app.catalogo import comum, miniatura, relacoes
from app.catalogo.comum import (
    carregar,
    contexto_anonimo,
    exigir_edicao,
    item_json,
    item_ou_404,
    registrar_evento,
    uuid_ok,
)
from app.catalogo.modelos import (
    Compartilhado,
    Compartilhamento,
    CompartilhamentoEntrada,
    Item,
    Link,
    LinkCriado,
    LinkEntrada,
)
from app.erros import ErroAPI
from app.settings import settings

router = APIRouter(tags=["compartilhamento"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


# ---------------------------------------------------------------- estado do compartilhamento
def _grupos_do_item(cur, iid: str) -> list[dict]:
    cur.execute(
        "SELECT g.id, g.nome, ig.destaque, ig.criado_em FROM plat.item_grupo ig JOIN plat.grupo g ON "
        "g.id = ig.grupo_id "
        "WHERE ig.item_id = %s::uuid ORDER BY g.nome",
        (iid,),
    )
    return [
        {"id": str(r["id"]), "nome": r["nome"], "destaque": r["destaque"], "criado_em": iso(r["criado_em"])}
        for r in cur.fetchall()
    ]


def _link_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "prefixo": r["prefixo"],
        "nome": r["nome"],
        "criado_por": r["criado_por"],
        "criado_em": iso(r["criado_em"]),
        "expira_em": iso(r["expira_em"]),
        "revogado_em": iso(r["revogado_em"]),
        "acessos": r["acessos"],
        "ultimo_acesso_em": iso(r["ultimo_acesso_em"]),
        "permite_download": r["permite_download"],
        "itens_incluidos": [str(x) for x in (r["itens_incluidos"] or [])],
        "url": f"/c/{r['prefixo']}...",
    }


SQL_LINK = (
    "SELECT k.*, ARRAY(SELECT li.item_id FROM plat.compartilhamento_link_item li WHERE li.link_id = "
    "k.id)::text[] AS itens_incluidos "
    "FROM plat.compartilhamento_link k WHERE k.item_id = %s::uuid"
)


def _links_do_item(cur, iid: str) -> list[dict]:
    cur.execute(SQL_LINK + " ORDER BY k.criado_em DESC", (iid,))
    return [_link_json(r) for r in cur.fetchall()]


def _dependencias(cur, iid: str) -> list[dict]:
    return [d for d in relacoes.criado_a_partir_de(cur, iid)]


def estado(cur, auth: Auth, r: dict) -> dict:
    iid = str(r["id"])
    completo = bool(r["pode_editar"])
    return {
        "acesso": r["acesso"],
        "grupos": _grupos_do_item(cur, iid),
        "links": _links_do_item(cur, iid) if completo else [],
        "publico_permitido": bool((auth.config or {}).get("auth", {}).get("compartilhar_publico", False)),
        "dependencias": _dependencias(cur, iid) if completo else [],
        "pode_editar": completo,
    }


@router.get("/api/itens/{id}/compartilhamento", response_model=Compartilhamento, openapi_extra=LER)
def ver_compartilhamento(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    with db.db(auth.contexto()) as cur:
        return estado(cur, auth, item_ou_404(cur, id))


def aplicar_compartilhamento(
    cur,
    request: Request,
    auth: Auth,
    iid: str,
    acesso: str | None,
    grupos: list[str] | None,
    destaques: list[str] | None,
    aplicar_a: list[str] | None = None,
) -> dict:
    r = exigir_edicao(cur, iid)
    antes = {"acesso": r["acesso"], "grupos": sorted(g["id"] for g in _grupos_do_item(cur, iid))}
    if acesso is not None and acesso != r["acesso"]:
        exigido = {"inquilino": "compartilhar.inquilino", "publico": "compartilhar.publico"}.get(acesso)
        if exigido and not auth.tem(exigido):
            raise ErroAPI(403, "sem_permissao", f"a operação exige o privilégio {exigido}", {"exigido": exigido})
        if acesso == "publico" and not (auth.config or {}).get("auth", {}).get("compartilhar_publico", False):
            raise ErroAPI(400, "publico_desligado", "o inquilino não permite compartilhamento público")
        cur.execute("UPDATE plat.item SET acesso = %s WHERE id = %s::uuid", (acesso, iid))
    if grupos is not None:
        if not auth.tem("compartilhar.grupo") and grupos:
            raise ErroAPI(
                403,
                "sem_permissao",
                "a operação exige o privilégio compartilhar.grupo",
                {"exigido": "compartilhar.grupo"},
            )
        alvo = [uuid_ok(g, "grupo_inexistente", "grupo inexistente") for g in dict.fromkeys(grupos)]
        for g in alvo:
            cur.execute("SELECT 1 FROM plat.grupo WHERE id = %s::uuid", (g,))
            if cur.fetchone() is None:
                raise ErroAPI(404, "grupo_inexistente", "grupo inexistente", {"grupo": g})
        atuais = set(antes["grupos"])
        for g in atuais - set(alvo):
            cur.execute("DELETE FROM plat.item_grupo WHERE item_id = %s::uuid AND grupo_id = %s::uuid", (iid, g))
        for g in alvo:
            if g not in atuais:
                cur.execute(
                    "INSERT INTO plat.item_grupo(item_id, grupo_id, tenant_id, criado_por) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s)",
                    (iid, g, auth.tenant_id, auth.usuario_id),
                )
    if destaques is not None:
        ids = [uuid_ok(g, "grupo_inexistente", "grupo inexistente") for g in destaques]
        cur.execute(
            "UPDATE plat.item_grupo SET destaque = (grupo_id = ANY (%s::uuid[])) WHERE item_id = %s::uuid", (ids, iid)
        )
    depois = {
        "acesso": acesso if acesso is not None else r["acesso"],
        "grupos": sorted(g["id"] for g in _grupos_do_item(cur, iid)),
    }
    if antes != depois:
        registrar_evento(cur, request, "compartilhamento/alterar", "item", iid, {"antes": antes, "depois": depois})
    if aplicar_a:
        deps = {d["id"]: d for d in _dependencias(cur, iid) if not d.get("oculto")}
        sem_edicao = [d for d in aplicar_a if d not in deps or not deps[d]["pode_editar"]]
        if sem_edicao:
            raise ErroAPI(403, "sem_edicao_no_item", "você não pode editar todas as dependências marcadas", sem_edicao)
        for d in aplicar_a:
            aplicar_compartilhamento(cur, request, auth, d, depois["acesso"], depois["grupos"], None, None)
    return item_ou_404(cur, iid)


@router.put(
    "/api/itens/{id}/compartilhamento",
    response_model=Compartilhamento,
    openapi_extra={"x-auth": "S/T", "x-privilegio": "compartilhar.grupo|compartilhar.inquilino|compartilhar.publico"},
)
def alterar_compartilhamento(id: str, corpo: CompartilhamentoEntrada, request: Request, auth: Auth = autenticado()):
    iid = uuid_ok(id)
    try:
        with db.db(auth.contexto()) as cur:
            r = aplicar_compartilhamento(
                cur,
                request,
                auth,
                iid,
                corpo.acesso,
                corpo.grupos,
                corpo.destaques,
                [uuid_ok(x) for x in (corpo.aplicar_a_dependencias or [])],
            )
            return estado(cur, auth, r)
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


# ---------------------------------------------------------------- links por token
def _expira(valor: str | None) -> datetime.datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError as e:
        raise ErroAPI(422, "validacao", "expira_em exige ISO 8601", {"campo": "expira_em"}) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    agora = datetime.datetime.now(datetime.UTC)
    if dt <= agora:
        raise ErroAPI(422, "validacao", "expira_em precisa ser no futuro", {"campo": "expira_em"})
    if dt > agora + datetime.timedelta(days=limites.LINK_VALIDADE_MAX_DIAS):
        raise ErroAPI(400, "validade_acima_do_maximo", f"validade máxima de {limites.LINK_VALIDADE_MAX_DIAS} dias")
    return dt


@router.post(
    "/api/itens/{id}/links",
    response_model=LinkCriado,
    status_code=201,
    openapi_extra={"x-auth": "S", "x-privilegio": "compartilhar.link"},
)
def criar_link(
    id: str, corpo: LinkEntrada, request: Request, auth: Auth = autenticado("compartilhar.link", so_sessao=True)
):
    iid = uuid_ok(id)
    expira = _expira(corpo.expira_em)
    try:
        with db.db(auth.contexto()) as cur:
            exigir_edicao(cur, iid)
            cur.execute(
                "SELECT count(*) AS n FROM plat.compartilhamento_link WHERE item_id = %s::uuid AND revogado_em IS NULL",
                (iid,),
            )
            if cur.fetchone()["n"] >= limites.LINKS_POR_ITEM:
                raise ErroAPI(422, "limite_links", f"no máximo {limites.LINKS_POR_ITEM} links ativos por item")
            incluidos = [uuid_ok(x) for x in dict.fromkeys(corpo.itens_incluidos or []) if uuid_ok(x) != iid]
            if incluidos:
                deps = {d["id"]: d for d in _dependencias(cur, iid) if not d.get("oculto")}
                sem = [x for x in incluidos if x not in deps or not deps[x]["pode_editar"]]
                if sem:
                    raise ErroAPI(
                        403, "sem_edicao_no_item", "só se inclui no link dependência que você pode editar", sem
                    )
            token = secrets.token_hex(limites.LINK_TOKEN_BYTES)
            h = hashlib.sha256(token.encode()).hexdigest()
            cur.execute(
                "INSERT INTO plat.compartilhamento_link(tenant_id, item_id, token_hash, prefixo, "
                "nome, criado_por, expira_em, permite_download) "
                "VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s) RETURNING id",
                (auth.tenant_id, iid, h, token[:8], corpo.nome, auth.usuario_id, expira, corpo.permite_download),
            )
            lid = str(cur.fetchone()["id"])
            for x in incluidos:
                cur.execute(
                    "INSERT INTO plat.compartilhamento_link_item(link_id, item_id, tenant_id) "
                    "VALUES (%s::uuid, %s::uuid, %s)",
                    (lid, x, auth.tenant_id),
                )
            registrar_evento(
                cur,
                request,
                "compartilhamento/link_criar",
                "link",
                lid,
                {"item_id": iid, "prefixo": token[:8], "itens_incluidos": incluidos, "expira_em": iso(expira)},
            )
            cur.execute(SQL_LINK + " AND k.id = %s::uuid", (iid, lid))
            j = _link_json(cur.fetchone())
            j.update({"token": token, "url": f"{settings.PLAT_URL_PUBLICA}/c/{token}"})
            return j
    except psycopg2.Error as e:
        raise comum.erro_do_banco(e) from e


@router.get(
    "/api/itens/{id}/links",
    response_model=list[Link],
    openapi_extra={"x-auth": "S", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"},
)
def listar_links(id: str, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        exigir_edicao(cur, iid)
        return _links_do_item(cur, iid)


@router.delete(
    "/api/itens/{id}/links/{lid}",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-auth": "S", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"},
)
def revogar_link(id: str, lid: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    lid = uuid_ok(lid, "link_inexistente", "link inexistente")
    with db.db(auth.contexto()) as cur:
        exigir_edicao(cur, iid)
        cur.execute(
            "SELECT revogado_em, prefixo FROM plat.compartilhamento_link WHERE id = %s::uuid AND item_id = %s::uuid",
            (lid, iid),
        )
        r = cur.fetchone()
        if r is None:
            raise ErroAPI(404, "link_inexistente", "link inexistente")
        if r["revogado_em"] is None:
            cur.execute(
                "UPDATE plat.compartilhamento_link SET revogado_em = now(), revogado_por = %s WHERE id = %s::uuid",
                (auth.usuario_id, lid),
            )
            registrar_evento(
                cur, request, "compartilhamento/link_revogar", "link", lid, {"item_id": iid, "prefixo": r["prefixo"]}
            )
    return Response(status_code=204)


# ---------------------------------------------------------------- leitura anônima por link
def resolver_link(cur, token: str, request: Request) -> dict:
    """Valida o token (64 hex), resolve pré-contexto e abre o contexto anônimo do inquilino do link."""
    if len(token) != limites.LINK_TOKEN_BYTES * 2 or any(c not in "0123456789abcdef" for c in token):
        raise ErroAPI(404, "link_invalido", "link inexistente ou revogado")
    h = hashlib.sha256(token.encode()).hexdigest()
    cur.execute(
        "SELECT motivo, tenant_id, item_id, itens_incluidos::text[] AS itens_incluidos, permite_download, link_id "
        "FROM plat.link_resolver(%s, %s)",
        (h, request.client.host if request.client else None),
    )
    r = cur.fetchone()
    if r["motivo"] == "expirado":
        raise ErroAPI(410, "link_expirado", "este link expirou")
    if r["motivo"] != "ok":
        raise ErroAPI(404, "link_invalido", "link inexistente ou revogado")
    itens = [str(x) for x in r["itens_incluidos"]]
    contexto_anonimo(cur, r["tenant_id"], itens)
    return {
        "tenant_id": r["tenant_id"],
        "item_id": str(r["item_id"]),
        "itens": itens,
        "permite_download": r["permite_download"],
    }


@router.get(
    "/api/compartilhado/{token}", response_model=Compartilhado, openapi_extra={"x-auth": "-", "x-privilegio": "publico"}
)
def compartilhado(token: str, request: Request):
    with db.db() as cur:
        link = resolver_link(cur, token, request)
        r = carregar(cur, link["item_id"])
        if r is None:
            raise ErroAPI(404, "link_invalido", "link inexistente ou revogado")
        incluidos = []
        for x in link["itens"][1:]:
            ri = carregar(cur, x)
            if ri is not None:
                incluidos.append(item_json(ri, None, completo=True, publico=True))
        corpo = {
            "item": item_json(r, None, completo=True, publico=True),
            "itens_incluidos": incluidos,
            "permite_download": link["permite_download"],
        }
    return JSONResponse(corpo, headers=SEM_CACHE)


@router.get(
    "/api/compartilhado/{token}/itens/{id}",
    response_model=Item,
    openapi_extra={"x-auth": "-", "x-privilegio": "publico"},
)
def compartilhado_item(token: str, id: str, request: Request):
    iid = uuid_ok(id)
    with db.db() as cur:
        link = resolver_link(cur, token, request)
        if iid not in link["itens"]:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        r = carregar(cur, iid)
        if r is None:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        corpo = item_json(r, None, completo=True, publico=True)
    return JSONResponse(corpo, headers=SEM_CACHE)


@router.get("/api/compartilhado/{token}/itens/{id}/miniatura", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def compartilhado_miniatura(token: str, id: str, request: Request):
    iid = uuid_ok(id)
    with db.db() as cur:
        link = resolver_link(cur, token, request)
        if iid not in link["itens"]:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        r = carregar(cur, iid)
        if r is None:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
    # sem cache no cliente (G2-6): link revogado nega em ≤ 1 s também na miniatura, não só no JSON
    return miniatura.entregar(r, request, cache=SEM_CACHE["Cache-Control"])


# ---------------------------------------------------------------- leitura pública (D24: só com o inquilino autorizando)
def _contexto_publico(cur, iid: str) -> dict | None:
    """Item público: resolve o inquilino pelo próprio item (função SECURITY DEFINER inexistente de propósito: a rota
    tenta o contexto de cada inquilino que permite público — o dado é aberto por decisão do admin do inquilino)."""
    cur.execute("SELECT t.id FROM plat.tenant_publico_itens(%s::uuid) t", (iid,))
    r = cur.fetchone()
    if r is None:
        return None
    contexto_anonimo(cur, r["id"], [])
    return carregar(cur, iid)


@router.get("/api/publico/itens/{id}", response_model=Item, openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def publico_item(id: str):
    iid = uuid_ok(id)
    with db.db() as cur:
        r = _contexto_publico(cur, iid)
        if r is None:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
        corpo = item_json(r, None, completo=True, publico=True)
    return JSONResponse(corpo, headers=SEM_CACHE)


@router.get("/api/publico/itens/{id}/miniatura", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def publico_miniatura(id: str, request: Request):
    iid = uuid_ok(id)
    with db.db() as cur:
        r = _contexto_publico(cur, iid)
        if r is None:
            raise ErroAPI(404, "item_inexistente", "item inexistente")
    # item que deixa de ser público some do cliente na hora, como o link revogado (mesmo motivo do G2-6)
    return miniatura.entregar(r, request, cache=SEM_CACHE["Cache-Control"])


# ---------------------------------------------------------------- objeto por URL assinada (adaptador local,
# contrato 11.3)
@router.get("/api/objetos/{chave:path}", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def objeto_assinado(chave: str, ate: int = 0, assinatura: str = ""):
    if not objetos.assinatura_valida(chave, ate, assinatura):
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente ou assinatura inválida")
    try:
        dados = objetos.ler(chave)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise ErroAPI(404, "objeto_inexistente", "objeto inexistente") from e
    tipo = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "gif": "image/gif",
        "json": "application/json",
        "csv": "text/csv",
    }.get(chave.rsplit(".", 1)[-1], "application/octet-stream")
    return Response(
        dados, media_type=tipo, headers={"Cache-Control": "private, max-age=60", "X-Robots-Tag": "noindex, nofollow"}
    )
