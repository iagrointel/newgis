"""`GET /api/qr.svg?texto=` — QR gerado NA PLATAFORMA (pacote `qrcode`, o mesmo do 2FA em app/auth/totp.py), para o
widget "compartilhar" (item L5-01-d) nunca depender de serviço externo. SVG de caminho vetorial, sem script.
Qualquer sessão ou token pode pedir; o texto é limitado (limites.QR_TEXTO_MAX) e vai como conteúdo do QR, nunca
interpretado."""

from fastapi import APIRouter, Query, Response

from app import limites
from app.auth.sessao import Auth, autenticado
from app.auth.totp import qr_svg

router = APIRouter(tags=["utilidades"])


@router.get("/api/qr.svg", openapi_extra={"x-auth": "S/T", "x-privilegio": "proprio"})
def qr(texto: str = Query(..., min_length=1, max_length=limites.QR_TEXTO_MAX),
       auth: Auth = autenticado(escopo_token="catalogo:ler")):
    return Response(content=qr_svg(texto), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"})
