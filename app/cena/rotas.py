"""Rota da cena 3D (item L2-09-b-cena-extrusao-slides).

Uma rota só: `GET /api/cena/sol`, que devolve azimute e elevação do Sol para uma coordenada e um
instante, mais a luz já no formato do estilo do MapLibre (`map.setLight`). É cálculo puro sobre
`app/cena/sol.py` — não lê nem escreve tabela nenhuma, não toca dado de inquilino — mas pede sessão
ou token como todas as outras: é a superfície da aplicação, não um serviço aberto.

O documento de cena em si NÃO tem rota própria: ele é um item do catálogo do tipo `cena` e usa
`/api/itens` (criar, editar, versões, publicar) como qualquer outro documento — o mesmo mecanismo do
L0-03/L5-05. Rota nova para isso seria um segundo caminho para a mesma coisa.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Query

from app.auth.sessao import Auth, autenticado
from app.cena import sol as mod_sol
from app.erros import ErroAPI

router = APIRouter(tags=["cena"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}


@router.get("/api/cena/sol", openapi_extra=X)
def sol(
    lat: float = Query(..., ge=-90, le=90, description="latitude em graus, norte positivo"),
    lon: float = Query(..., ge=-180, le=180, description="longitude em graus, leste positivo"),
    instante: str = Query(..., max_length=40,
                          description="instante ISO 8601 com fuso (ex.: 2026-06-21T12:00:00-03:00)"),
    intensidade: float = Query(0.35, ge=0, le=1, description="intensidade da luz devolvida no bloco do MapLibre"),
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Posição geométrica do Sol (sem refração) pelo algoritmo do NOAA, e a luz correspondente."""
    try:
        quando = datetime.datetime.fromisoformat(instante)
    except ValueError as e:
        raise ErroAPI(422, "instante_invalido", "instante fora do formato ISO 8601", [
            {"campo": "instante", "erro": str(e)[:200], "regra": "iso8601"}]) from e
    if quando.tzinfo is None:
        raise ErroAPI(422, "instante_sem_fuso", "o instante precisa trazer o fuso horário", [
            {"campo": "instante", "erro": "sem fuso", "regra": "tzinfo"}])
    p = mod_sol.posicao(lat, lon, quando)
    return {
        "azimute": round(p.azimute, 4),
        "elevacao": round(p.elevacao, 4),
        "declinacao": round(p.declinacao, 4),
        "equacao_do_tempo_min": round(p.equacao_do_tempo_min, 4),
        "instante_utc": p.instante_utc,
        "luz": mod_sol.luz_maplibre(p, intensidade),
    }
