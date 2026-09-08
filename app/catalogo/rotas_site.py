"""Rotas do site do inquilino (item L5-20-sites-paginas-publicas; ADR 20260908T1140-sites-paginas-publicas).

Duas famílias de rota:

- administração, por sessão: `GET/PUT/DELETE /api/itens/{id}/site` — estado da publicação, publicar/republicar
  (com a opção `indexavel`, falsa por padrão) e retirar do ar. Mesma checagem de `exigir_edicao` das rotas de
  publicação do L5-14.
- vitrine anônima: `GET /s/{inquilino}` e `GET /s/{inquilino}/{caminho}` — HTML renderizado no servidor
  (`app/catalogo/site_render.py`), fora do OpenAPI como toda página. Cabeçalhos: `X-Robots-Tag` `noindex,
  nofollow` a menos que a publicação seja indexável, e uma política de conteúdo estreita (`default-src 'self'`)
  com `frame-src` limitado ao que o próprio documento declara.

O `X-Frame-Options: DENY` global do nginx continua valendo para `/s/` — um site público não precisa ser
emoldurado por terceiro; quem precisa disso é `/p/` (L5-14).
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, site, site_render
from app.catalogo.comum import uuid_ok
from app.catalogo.modelos import Site, SiteEntrada
from app.erros import ErroAPI

router = APIRouter(tags=["site"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}


@router.get("/api/itens/{id}/site", response_model=Site | None, openapi_extra=LER)
def ver_site(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        comum.item_ou_404(cur, iid)
        r = site.estado(cur, iid)
    return JSONResponse(r, headers=SEM_CACHE)


@router.put("/api/itens/{id}/site", response_model=Site, openapi_extra=EDITAR)
def publicar_site(id: str, corpo: SiteEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = site.publicar(cur, request, auth, iid, corpo.indexavel, corpo.versao)
    return JSONResponse(r, headers=SEM_CACHE)


@router.delete("/api/itens/{id}/site", status_code=204, response_class=Response, openapi_extra=EDITAR)
def despublicar_site(id: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        site.despublicar(cur, request, iid)
    return Response(status_code=204)


# ---------------------------------------------------------------- vitrine anônima
def _csp(hosts: list[str]) -> str:
    frame = " ".join(["'self'", *hosts]) if hosts else "'self'"
    return ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            f"frame-src {frame}; base-uri 'none'; form-action 'self'")


def _pagina(inquilino: str, caminho: str, request: Request) -> HTMLResponse:
    with db.db() as cur:
        r = site.resolver(cur, inquilino)
        corpo = site.corpo_publicado(cur, str(r["item_id"]), r["versao"])
        pagina = site_render.pagina_por_caminho(corpo, caminho)
        if pagina is None:
            raise ErroAPI(404, "pagina_inexistente", "página inexistente neste site")
        ctx = site_render.Contexto(
            cur=cur, tenant_id=r["tenant_id"], tenant_slug=inquilino, tenant_nome=r["tenant_nome"],
            cor=r["tenant_cor"], logo=r["tenant_logo"], indexavel=bool(r["indexavel"]),
            parametros=dict(request.query_params),
        )
        html = site_render.renderizar(ctx, corpo, pagina)
        hosts = site_render.hosts_incorporados(corpo, pagina.get("id"))
    robos = "index, follow" if r["indexavel"] else "noindex, nofollow"
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-store", "X-Robots-Tag": robos, "Content-Security-Policy": _csp(hosts)},
    )


@router.get("/s/{inquilino}", include_in_schema=False)
@router.get("/s/{inquilino}/", include_in_schema=False)
def pagina_inicial_do_site(inquilino: str, request: Request):
    return _pagina(inquilino, "", request)


@router.get("/s/{inquilino}/{caminho}", include_in_schema=False)
def pagina_do_site(inquilino: str, caminho: str, request: Request):
    return _pagina(inquilino, caminho, request)
