"""Rotas do editor de estilo (item L2-02-c-editor-simbologia-vetor): `POST /api/estilos/compilar` devolve as
camadas MapLibre e a legenda de um `plat_construtor` SEM gravar nada — é a pré-visualização ao vivo do editor,
pela MESMA função que grava (`app/estilos/compilador.py`), para o navegador nunca ter um segundo compilador
(regra do L5_CONCEITO: zero renderizador duplicado). Erro de construtor vira 422 com o campo apontado."""

from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.estilos import compilador

router = APIRouter(tags=["estilos"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}


class Compilacao(BaseModel):
    plat_construtor: dict
    id_base: str = "camada"


@router.post("/api/estilos/compilar", openapi_extra=X)
def compilar(corpo: Compilacao = Body(...), auth: Auth = autenticado(escopo_token="catalogo:ler")):  # noqa: B008
    """Compila um `plat_construtor` (sem gravar): {maplibre, legenda}. Puro cálculo, sem dado de inquilino."""
    if not corpo.id_base or len(corpo.id_base) > 80 or not corpo.id_base.replace("-", "").replace("_", "").isalnum():
        raise ErroAPI(422, "id_base_invalido", "id_base deve ser um identificador curto")
    try:
        maplibre = compilador.compilar(corpo.plat_construtor, corpo.id_base)
        legenda = compilador.legenda(corpo.plat_construtor)
    except compilador.EstiloInvalido as e:
        raise ErroAPI(422, "plat_construtor_invalido", str(e), {"campo": e.campo}) from e
    return JSONResponse({"maplibre": maplibre, "legenda": legenda}, headers={"Cache-Control": "no-store"})
