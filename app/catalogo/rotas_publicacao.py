"""Publicação de documento de construtor (item L5-14-publicacao-links-embed; ADR 0018): estado da publicação
em `/api/itens/{id}/publicacao` (POST publica/republica, GET lê, DELETE despublica), exportação estática em
`/api/itens/{id}/publicacao/exportacao`, contagem de visualização em `/api/itens/{id}/publicacao/visualizacoes`
e a vitrine pública em duas rotas sem sessão: `GET /api/p/{inquilino}/{slug}` (JSON, conta a visualização) e
`GET /p/{inquilino}/{slug}` (a casca HTML, com o cabeçalho `Content-Security-Policy: frame-ancestors`
calculado por app — nunca o `X-Frame-Options: DENY` genérico da API, que bloquearia todo iframe)."""

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo import comum, publicacao
from app.catalogo.comum import uuid_ok
from app.catalogo.modelos import DocumentoPublico, Publicacao, PublicacaoEntrada, VisualizacaoDia
from app.erros import ErroAPI

router = APIRouter(tags=["publicacao"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
EDITAR = {"x-auth": "S", "x-privilegio": "rls:visibilidade|conteudo.editar_tudo"}
SEM_CACHE = {"Cache-Control": "no-store, must-revalidate"}
WEB = Path(__file__).resolve().parents[2] / "web"


@router.get("/api/itens/{id}/publicacao", response_model=Publicacao | None, openapi_extra=LER)
def ver_publicacao(id: str, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        comum.item_ou_404(cur, iid)
        r = publicacao.estado(cur, iid)
    if r is None:
        return JSONResponse(None, headers=SEM_CACHE)
    return JSONResponse(r, headers=SEM_CACHE)


@router.post(
    "/api/itens/{id}/publicacao",
    response_model=Publicacao,
    status_code=201,
    openapi_extra=EDITAR,
)
def publicar(id: str, corpo: PublicacaoEntrada, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        r = publicacao.publicar(cur, request, auth, iid, corpo.slug, corpo.dominios_permitidos, corpo.versao)
    return JSONResponse(r, status_code=201, headers=SEM_CACHE)


@router.delete(
    "/api/itens/{id}/publicacao",
    status_code=204,
    response_class=Response,
    openapi_extra=EDITAR,
)
def despublicar(id: str, request: Request, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        publicacao.despublicar(cur, request, iid)
    return Response(status_code=204)


@router.get(
    "/api/itens/{id}/publicacao/visualizacoes",
    response_model=list[VisualizacaoDia],
    openapi_extra=EDITAR,
)
def ver_visualizacoes(id: str, dias: int = 30, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        return publicacao.visualizacoes(cur, iid, dias)


@router.get(
    "/api/itens/{id}/publicacao/exportacao",
    openapi_extra=EDITAR,
)
def exportar(id: str, auth: Auth = autenticado(so_sessao=True)):
    iid = uuid_ok(id)
    with db.db(auth.contexto()) as cur:
        pacote = publicacao.exportacao_estatica(cur, iid)
    return Response(
        pacote,
        media_type="text/html; charset=utf-8",
        headers={**SEM_CACHE, "Content-Disposition": f'attachment; filename="publicacao-{iid}.html"'},
    )


# ---------------------------------------------------------------- vitrine pública (sem sessão)
PUBLICO = {"x-auth": "-", "x-privilegio": "publico"}


@router.get("/api/p/{inquilino}/{slug}", response_model=DocumentoPublico, openapi_extra=PUBLICO)
def documento_publico(inquilino: str, slug: str, request: Request, link: str | None = None):
    with db.db() as cur:
        corpo = publicacao.documento_publico(cur, inquilino, slug, request, link)
    return JSONResponse(corpo, headers=SEM_CACHE)


def _csp_frame_ancestors(dominios: list[str]) -> str:
    fontes = "'self' " + " ".join(dominios) if dominios else "'self'"
    return f"frame-ancestors {fontes}"


@router.get("/p/{inquilino}/{slug}", include_in_schema=False)
def pagina_publicada(inquilino: str, slug: str):
    """Casca HTML de `/p/<inquilino>/<slug>`: 404 se a publicação não existir; cabeçalho
    `Content-Security-Policy: frame-ancestors` calculado pelos domínios do app (nunca `X-Frame-Options: DENY` —
    essa é a exceção controlada que o item pede). Não conta visualização aqui: quem conta é a chamada JSON
    que a própria página faz (`GET /api/p/...`), uma por carregamento."""
    with db.db() as cur:
        dominios = publicacao.dominios_de(cur, inquilino, slug)
    if dominios is None:
        raise ErroAPI(404, "publicacao_inexistente", "aplicativo publicado inexistente")
    caminho = WEB / "publicado.html"
    if not caminho.is_file():
        raise ErroAPI(404, "pagina_inexistente", "página inexistente")
    return FileResponse(
        caminho,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": _csp_frame_ancestors(dominios),
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
