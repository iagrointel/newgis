"""Vídeos por tarefa (item L7-04-d-videos-por-tarefa): manifesto em GET /api/videos e arquivos gerados
pelo alvo `make videos` (scripts/videos/gerar.py) em GET /videos/arquivo/{caminho}. Sessão de usuário
(nunca token); a página /videos é registrada em app/paginas.py. Sem manifesto, /api/videos devolve 404
com a razão escrita — nunca uma lista vazia que pareça produto."""

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.auth.sessao import autenticado
from app.erros import ErroAPI

ROOT = Path(__file__).resolve().parents[1]
VIDEOS = ROOT / "web" / "videos"
SUFIXOS_OK = (".mp4", ".vtt", ".json")
SEGURA = re.compile(r"^[\w.\-]+$")

router = APIRouter(tags=["videos"])


@router.get("/api/videos")
def manifesto(_auth=autenticado(so_sessao=True)):
    caminho = VIDEOS / "manifesto.json"
    if not caminho.is_file():
        raise ErroAPI(404, "videos_nao_gerados", "vídeos ainda não gerados nesta instalação (rode make videos)")
    return FileResponse(
        caminho, media_type="application/json; charset=utf-8", headers={"Cache-Control": "no-store"}
    )


@router.get("/videos/arquivo/{caminho}")
def arquivo(caminho: str, _auth=autenticado(so_sessao=True)):
    """Entrega um mp4/vtt/manifesto gerado. Nome simples (sem caminho), sufixo conhecido, arquivo real."""
    if not SEGURA.match(caminho) or not caminho.endswith(SUFIXOS_OK):
        raise ErroAPI(404, "nao_encontrado", "arquivo de vídeo inexistente")
    alvo = VIDEOS / caminho
    if not alvo.is_file():
        raise ErroAPI(404, "nao_encontrado", "arquivo de vídeo inexistente")
    tipo = "video/mp4" if caminho.endswith(".mp4") else (
        "text/vtt; charset=utf-8" if caminho.endswith(".vtt") else "application/json; charset=utf-8")
    return FileResponse(alvo, media_type=tipo, headers={"Cache-Control": "no-store"})
