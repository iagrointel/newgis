"""Rotas /api/rota, /api/matriz e /api/isocrona (item L2-11-c-rota-matriz-isocrona). Serviço de
localização sobre o OSRM isolado de teste `plat-osrm-guarulhos` (127.0.0.1:5010, recorte de Guarulhos
≤ 50 MB — nunca a base de outra frente da casa). Sem tabela `plat.*` própria: não há estado do
inquilino aqui, só cálculo sobre dado aberto (OSM); a autenticação exige o escopo `rota:usar` (token)
ou sessão de usuário — sem RLS porque não há linha de banco para isolar (P6 não se aplica: nada é
lido/escrito por inquilino)."""

import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app import limites
from app.auth.sessao import autenticado
from app.db import db
from app.erros import ErroAPI
from app.rede import isocrona as isocrona_mod
from app.rede import osrm
from app.rede import pgr
from app.rede.instrucoes import resumir_rota
from app.settings import settings

log = logging.getLogger("plat.rede.rotas")
router = APIRouter(prefix="/api", tags=["rede"])
# "proprio": só exige autenticação (sessão ou token com o escopo rota:usar), sem privilégio nomeado — o
# cálculo é sobre dado aberto (OSM), não sobre um recurso do inquilino (mesmo valor de /api/eu, /api/arquivos)
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

_PROVENIENCIA = osrm.PROVENIENCIA  # arquivo, sha256 e data do recorte OSM (fonte única em app/rede/osrm.py)


def _ponto_valido(p: list[float]) -> list[float]:
    if len(p) != 2:
        raise ValueError("ponto precisa de exatamente [longitude, latitude]")
    lon, lat = p
    if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
        raise ValueError(f"coordenada fora do intervalo geográfico: {p!r}")
    return [float(lon), float(lat)]


class PedidoRota(BaseModel):
    origem: list[float] = Field(..., examples=[[-46.5330, -23.4628]])
    destino: list[float] = Field(..., examples=[[-46.4730, -23.4356]])
    perfil: Literal["carro", "bicicleta", "pe"] = "carro"

    @field_validator("origem", "destino")
    @classmethod
    def _v_ponto(cls, v):
        return _ponto_valido(v)


class PedidoMatriz(BaseModel):
    origens: list[list[float]] = Field(..., min_length=1)
    destinos: list[list[float]] = Field(..., min_length=1)
    perfil: Literal["carro", "bicicleta", "pe"] = "carro"

    @field_validator("origens", "destinos")
    @classmethod
    def _v_pontos(cls, v):
        return [_ponto_valido(p) for p in v]


class PedidoIsocrona(BaseModel):
    ponto: list[float] = Field(..., examples=[[-46.5330, -23.4628]])
    minutos: float = Field(..., gt=0, le=limites.ROTA_MINUTOS_MAX)
    perfil: Literal["carro", "bicicleta", "pe"] = "carro"
    ratio_casco: float | None = Field(None, ge=0.0, le=1.0)

    @field_validator("ponto")
    @classmethod
    def _v_ponto(cls, v):
        return _ponto_valido(v)


class PedidoMaisProximo(BaseModel):
    ponto: list[float] = Field(..., examples=[[-46.5330, -23.4628]])
    perfil: Literal["carro", "bicicleta", "pe"] = "carro"

    @field_validator("ponto")
    @classmethod
    def _v_ponto(cls, v):
        return _ponto_valido(v)


class PedidoAjusteTrajeto(BaseModel):
    pontos: list[list[float]] = Field(..., min_length=2)
    perfil: Literal["carro", "bicicleta", "pe"] = "carro"
    raio_m: float = Field(50.0, gt=0, le=500)

    @field_validator("pontos")
    @classmethod
    def _v_pontos(cls, v):
        return [_ponto_valido(p) for p in v]


@router.post("/rota", openapi_extra=X)
def calcular_rota(pedido: PedidoRota, auth=autenticado(escopo_token="rota:usar")):
    resposta = osrm.rota(pedido.origem, pedido.destino, pedido.perfil)
    rota_osrm = resposta["routes"][0]
    passos = [s for leg in rota_osrm["legs"] for s in leg["steps"]]
    return {
        "distancia_m": rota_osrm["distance"],
        "duracao_s": rota_osrm["duration"],
        "geometria": rota_osrm["geometry"],
        "instrucoes": resumir_rota(passos),
        "perfil": pedido.perfil,
        "proveniencia": _PROVENIENCIA,
    }


@router.post("/matriz", openapi_extra=X)
def calcular_matriz(pedido: PedidoMatriz, auth=autenticado(escopo_token="rota:usar")):
    n, m = len(pedido.origens), len(pedido.destinos)
    teto = settings.PLAT_ROTA_MATRIZ_JOB_MAX
    if n * m > teto:
        raise ErroAPI(
            422,
            "matriz_grande_demais",
            f"{n}×{m} = {n * m} pedidos excede o teto de {teto} células por job (PLAT_ROTA_MATRIZ_JOB_MAX)",
            {"origens": n, "destinos": m, "teto": teto},
        )
    # acima do teto de UMA chamada /table (--max-table-size do contêiner), o serviço é chamado em blocos
    # e a matriz remontada (matriz_grande); abaixo, uma chamada só
    if n * m > settings.PLAT_ROTA_MATRIZ_MAX:
        resposta = osrm.matriz_grande(pedido.origens, pedido.destinos, pedido.perfil)
    else:
        resposta = osrm.matriz(pedido.origens, pedido.destinos, pedido.perfil)
    return {
        "duracoes_s": resposta.get("durations"),
        "distancias_m": resposta.get("distances"),
        "origens": n,
        "destinos": m,
        "perfil": pedido.perfil,
        "proveniencia": _PROVENIENCIA,
    }


@router.post("/isocrona-rede", openapi_extra=X)
def calcular_isocrona_rede(pedido: PedidoIsocrona, auth=autenticado(escopo_token="rota:usar")):
    """Isócrona pela REDE roteável em PostGIS (pgRouting), alternativa ao método de grade do
    /api/isocrona: pgr_drivingDistance sobre `plat.rota_pgr_demo` (mesmo recorte OSM do OSRM)."""
    with db(somente_leitura=True) as cur:
        if not pgr.rede_presente(cur):
            raise ErroAPI(
                422, "rede_ausente", "rede de demonstração pgRouting não carregada (scripts/rota_pgr_demo_carga.py)"
            )
        resultado = pgr.isocrona_poligono(cur, pedido.ponto[0], pedido.ponto[1], pedido.minutos)
    if resultado is None:
        raise ErroAPI(
            422, "isocrona_vazia", "menos de 3 nós alcançáveis no orçamento de tempo pedido (rede insuficiente)"
        )
    return {
        "poligono": resultado["poligono"],
        "minutos": pedido.minutos,
        "ponto": pedido.ponto,
        "metodo": resultado["metodo"],
        "nos_alcancaveis": resultado["nos_alcancaveis"],
        "proveniencia": _PROVENIENCIA,
    }


@router.post("/mais-proximo", openapi_extra=X)
def calcular_mais_proximo(pedido: PedidoMaisProximo, auth=autenticado(escopo_token="rota:usar")):
    resposta = osrm.mais_proximo(pedido.ponto, pedido.perfil)
    ponto_rede = resposta["waypoints"][0]
    return {
        "ponto_rede": ponto_rede["location"],
        "distancia_m": ponto_rede["distance"],
        "nome": ponto_rede.get("name") or "",
        "perfil": pedido.perfil,
        "proveniencia": _PROVENIENCIA,
    }


@router.post("/ajuste-de-trajeto", openapi_extra=X)
def calcular_ajuste_de_trajeto(pedido: PedidoAjusteTrajeto, auth=autenticado(escopo_token="rota:usar")):
    resposta = osrm.ajustar_trajeto(pedido.pontos, pedido.perfil, pedido.raio_m)
    ajuste = resposta["matchings"][0]
    passos = [s for leg in ajuste["legs"] for s in leg["steps"]]
    return {
        "distancia_m": ajuste["distance"],
        "duracao_s": ajuste["duration"],
        "confianca": ajuste.get("confidence"),
        "geometria": ajuste["geometry"],
        "instrucoes": resumir_rota(passos),
        "perfil": pedido.perfil,
        "proveniencia": _PROVENIENCIA,
    }


@router.post("/isocrona", openapi_extra=X)
def calcular_isocrona(pedido: PedidoIsocrona, auth=autenticado(escopo_token="rota:usar")):
    resultado = isocrona_mod.calcular(pedido.ponto, pedido.minutos, pedido.perfil, pedido.ratio_casco)
    if resultado["poligono"] is None:
        raise ErroAPI(
            422,
            "isocrona_vazia",
            "menos de 3 pontos alcançáveis no orçamento de tempo pedido (grade/rede insuficiente)",
            resultado["grade"],
        )
    return {
        "poligono": resultado["poligono"],
        "minutos": pedido.minutos,
        "ponto": pedido.ponto,
        "perfil": pedido.perfil,
        "metodo": "matriz OSRM sobre grade de pontos + casco côncavo (shapely.concave_hull)",
        "grade": resultado["grade"],
        "proveniencia": _PROVENIENCIA,
    }
