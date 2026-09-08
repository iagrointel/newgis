"""API do motor de render no servidor (item L2-12-a-motor-render-servidor; ADR 0023).

`POST /api/render/mapa`: recebe extensão/zoom/tamanho/DPI/formato, resolve a URL da página headless
(`/render/mapa`, o MESMO código do visualizador — reaproveita `web/js/mapa/estilo.js`) e devolve PNG ou PDF.
Sem `mapa_id` (ou com um documento sem camadas) desenha só o mapa-base local; com camadas, hoje devolve 501 —
não existe servidor de tiles vetoriais/raster nesta máquina (mesma fronteira honesta já declarada em
`app/mapas/documento.py`: MOTIVO_TILES_VETOR/MOTIVO_TILES_RASTER). Item futuro (composição de camada dentro do
render) puxa isso quando L2-01-b/L1-02 existirem — a fila e o pool já servem qualquer página nova sem mudar.

`POST /api/render/token` + `GET /api/render/interno/eco`: prova isolada do token interno de curta duração e
do bloqueio por host (cláusula "token interno expira em ≤ 60 s e não serve fora do host"), sem depender do
pipeline inteiro de imagem.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field

from app import db
from app.auth.sessao import Auth, autenticado
from app.catalogo.modelos import Modelo
from app.erros import ErroAPI
from app.mapas import documento as doc_mapa
from app.mapas.rotas import _mapa_ou_404
from app.render import token as render_token
from app.render.motor import ErroFilaCheia, ErroRenderTimeout, motor
from app.settings import settings

router = APIRouter(tags=["render"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}

MEDIA = {"png": "image/png", "pdf": "application/pdf"}


class RenderEntrada(Modelo):
    mapa_id: str | None = None
    largura: int = Field(default=1024, ge=64, le=settings.PLAT_RENDER_MAX_PX)
    altura: int = Field(default=768, ge=64, le=settings.PLAT_RENDER_MAX_PX)
    dpi: int = Field(default=96, ge=72, le=600)
    formato: Literal["png", "pdf"] = "png"
    extensao: list[float] | None = Field(default=None, min_length=4, max_length=4)
    zoom: float | None = None
    centro: list[float] | None = Field(default=None, min_length=2, max_length=2)


def _url_pagina(base: str, corpo: RenderEntrada) -> str:
    q = []
    if corpo.extensao:
        oeste, sul, leste, norte = corpo.extensao
        q += [f"oeste={oeste}", f"sul={sul}", f"leste={leste}", f"norte={norte}"]
    if corpo.zoom is not None:
        q.append(f"zoom={corpo.zoom}")
    if corpo.centro:
        q += [f"lng={corpo.centro[0]}", f"lat={corpo.centro[1]}"]
    qs = "&".join(q)
    return f"{base}/render/mapa" + (f"?{qs}" if qs else "")


@router.post("/api/render/mapa", openapi_extra=LER)
async def render_mapa(corpo: RenderEntrada, request: Request, auth: Auth = autenticado(escopo_token="catalogo:ler")):
    if corpo.mapa_id:
        with db.db(auth.contexto()) as cur:
            r = _mapa_ou_404(cur, corpo.mapa_id)
            resolvido = doc_mapa.completo(cur, {"id": str(r["id"]), "titulo": r["titulo"], "tipo": r["tipo"]},
                                           r["dados"])
        if resolvido.get("camadas"):
            raise ErroAPI(
                501, "render_de_camada_nao_suportado",
                "o motor de render ainda desenha só o mapa-base local; compor as camadas do documento "
                "depende de servidor de tiles vetoriais/raster nesta máquina (L2-01-b, L1-02), que não existem "
                "aqui — fronteira honesta do item L2-12-a-motor-render-servidor, não um bug",
            )
    base = f"{request.url.scheme}://{request.url.netloc}"
    url = _url_pagina(base, corpo)
    m = motor()
    if not m.ativo:
        await m.iniciar()
    try:
        dados, media = await m.renderizar(url, largura=corpo.largura, altura=corpo.altura, dpi=corpo.dpi,
                                           formato=corpo.formato)
    except ErroFilaCheia as e:
        raise ErroAPI(429, "fila_cheia", str(e)) from e
    except ErroRenderTimeout as e:
        raise ErroAPI(504, "render_timeout", str(e)) from e
    return Response(content=dados, media_type=media, headers={"Cache-Control": "no-store"})


@router.post("/api/render/token", openapi_extra=LER)
def emitir_token(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """Token interno de curta duração (≤ 60 s), só para a página headless do PRÓPRIO host chamar uma rota
    interna do motor de render durante a janela do pedido — nunca uma sessão, nunca reutilizável fora daqui."""
    tok = render_token.gerar()
    exp = int(tok.split(".")[0])
    return {"token": tok, "expira_em": exp, "ttl_s": settings.PLAT_RENDER_TOKEN_TTL_S}


@router.get(
    "/api/render/interno/eco", include_in_schema=False, openapi_extra={"x-auth": "-", "x-privilegio": "interno"}
)
def eco_interno(request: Request, token: str):
    """Rota de prova do token interno + bloqueio por host: NÃO faz parte do caminho de imagem (esse injeta o
    documento na página sem precisar de uma segunda chamada autenticada); existe para o portão poder testar
    as duas defesas (token e host) isoladas do pipeline de render inteiro."""
    host = request.client.host if request.client else None
    if not render_token.host_e_interno(host):
        raise ErroAPI(403, "fora_do_host", "esta rota só responde a um chamador no mesmo host")
    if not render_token.validar(token):
        raise ErroAPI(401, "token_invalido", "token interno inválido ou expirado")
    return {"ok": True}


@router.get("/api/render/saude", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def saude_render():
    m = motor()
    corpo = m.stats.como_dict()
    corpo["ativo"] = m.ativo
    return corpo
