"""Camada Esri-compatível (NAServer) sobre o serviço de rota do item L2-11-c-rota-matriz-isocrona.

Subconjunto SÍNCRONO do contrato REST de Network Analysis da Esri
(`.../NAServer/Route/solve`, `.../NAServer/ServiceArea/solveServiceArea`,
`.../NAServer/ClosestFacility/solveClosestFacility`, `.../NAServer/ODCostMatrix/solveODCostMatrix`),
no formato que JS (ArcGIS API 4.x `RouteTask`/etc.) e QGIS/Pro consomem: corpo JSON com os parâmetros
do serviço (`stops`, `facilities`, `incidents`, `origins`, `destinations` como feature sets
`{"features": [{"geometry": {"x": lon, "y": lat}}]}`, igual ao parâmetro `f=json` da Esri) e resposta
com `routes`/`directions`/`saPolygons`/`odCostMatrix` no desenho de feature set dela (geometria em
`paths`/`rings` + `attributes`). O cálculo é o MESMO do /api/rota|matriz|isocrona (OSRM do recorte) —
esta camada só traduz o envelope, nunca tem motor próprio.

Sem parâmetros de job assíncrono nem `token` da Esri: a autenticação é a da plataforma (escopo
`rota:usar`), e o teto de matriz é o declarado em /api/matriz (PLAT_ROTA_MATRIZ_JOB_MAX)."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import limites
from app.auth.sessao import autenticado
from app.erros import ErroAPI
from app.rede import isocrona as isocrona_mod
from app.rede import osrm
from app.rede.instrucoes import resumir_rota
from app.rede.rotas import _ponto_valido
from app.settings import settings

log = logging.getLogger("plat.rede.naserver")
router = APIRouter(prefix="/api/naserver/NAServer", tags=["rede-naserver"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

_PROVENIENCIA = osrm.PROVENIENCIA


class _FeatureSet(BaseModel):
    features: list[dict] = Field(..., min_length=1)


def _pontos_de(conjunto: _FeatureSet, nome: str) -> list[list[float]]:
    pontos = []
    for f in conjunto.features:
        geo = f.get("geometry") or {}
        try:
            pontos.append(_ponto_valido([float(geo["x"]), float(geo["y"])]))
        except (KeyError, TypeError, ValueError) as e:
            raise ErroAPI(422, "geometria_invalida", f"{nome}: feature sem geometry.x/y válido") from e
    return pontos


def _paths_da_geometria(geometria: dict) -> dict:
    return {"paths": [geometria["coordinates"]]}


def _rings_do_poligono(poligono: dict) -> dict:
    aneis = poligono["coordinates"] if poligono["type"] == "Polygon" else poligono["coordinates"][0]
    return {"rings": aneis}


def _direcoes(passos_resumo: list[dict]) -> dict:
    return {
        "features": [
            {
                "attributes": {
                    "text": p["texto"],
                    "length": p["distancia_m"],
                    "time": p["duracao_s"] / 60.0,
                    "maneuverType": "esriDMTUnknown",
                }
            }
            for p in passos_resumo
        ]
    }


def _resposta_rota(resposta_osrm: dict) -> dict:
    rota_osrm = resposta_osrm["routes"][0]
    passos = [s for leg in rota_osrm["legs"] for s in leg["steps"]]
    resumo = resumir_rota(passos)
    return {
        "routes": {
            "features": [
                {
                    "geometry": _paths_da_geometria(rota_osrm["geometry"]),
                    "attributes": {
                        "Total_Length": rota_osrm["distance"],
                        "Total_Time": rota_osrm["duration"] / 60.0,
                    },
                }
            ]
        },
        "directions": [_direcoes(resumo)],
    }


class PedidoSolveRoute(BaseModel):
    stops: _FeatureSet
    returnDirections: bool = True
    perfil: str = "carro"


@router.post("/Route/solve", openapi_extra=X)
def solve_rota(pedido: PedidoSolveRoute, auth=autenticado(escopo_token="rota:usar")):
    paradas = _pontos_de(pedido.stops, "stops")
    if len(paradas) < 2:
        raise ErroAPI(422, "paradas_insuficientes", "Route/solve precisa de ao menos 2 stops")
    resposta = osrm.rota_por_pontos(paradas, pedido.perfil)
    corpo = _resposta_rota(resposta)
    if not pedido.returnDirections:
        corpo.pop("directions")
    corpo["proveniencia"] = _PROVENIENCIA
    return corpo


class PedidoSolveServiceArea(BaseModel):
    facilities: _FeatureSet
    defaultBreaks: list[float] = Field(..., min_length=1)
    perfil: str = "carro"


@router.post("/ServiceArea/solveServiceArea", openapi_extra=X)
def solve_area_servico(pedido: PedidoSolveServiceArea, auth=autenticado(escopo_token="rota:usar")):
    facilidades = _pontos_de(pedido.facilities, "facilities")
    if len(facilidades) > 1:
        raise ErroAPI(
            422, "facilidades_demais", "solveServiceArea síncrono aceita 1 facility por chamada nesta instância"
        )
    feições = []
    for corte in pedido.defaultBreaks:
        if not (0 < corte <= limites.ROTA_MINUTOS_MAX):
            raise ErroAPI(422, "quebra_invalida", f"break {corte} fora de (0, {limites.ROTA_MINUTOS_MAX}] min")
        resultado = isocrona_mod.calcular(facilidades[0], corte, pedido.perfil)
        if resultado["poligono"] is None:
            continue
        feições.append(
            {"geometry": _rings_do_poligono(resultado["poligono"]), "attributes": {"ToBreak": corte, "FromBreak": 0}}
        )
    return {"saPolygons": {"features": feições}, "proveniencia": _PROVENIENCIA}


class PedidoSolveClosestFacility(BaseModel):
    facilities: _FeatureSet
    incidents: _FeatureSet
    defaultTargetFacilityCount: int = Field(1, ge=1)
    perfil: str = "carro"


@router.post("/ClosestFacility/solveClosestFacility", openapi_extra=X)
def solve_facilidade_mais_proxima(pedido: PedidoSolveClosestFacility, auth=autenticado(escopo_token="rota:usar")):
    facilidades = _pontos_de(pedido.facilities, "facilities")
    incidentes = _pontos_de(pedido.incidents, "incidents")
    k = min(pedido.defaultTargetFacilityCount, len(facilidades))
    matriz = osrm.matriz(incidentes, facilidades, pedido.perfil)
    duracoes = matriz.get("durations") or []
    feições = []
    for i, incidente in enumerate(incidentes):
        ordem = sorted(
            ((d, j) for j, d in enumerate(duracoes[i]) if d is not None), key=lambda t: t[0]
        )[:k]
        for d, j in ordem:
            resposta = osrm.rota(incidente, facilidades[j], pedido.perfil)
            rota_osrm = resposta["routes"][0]
            feições.append(
                {
                    "geometry": _paths_da_geometria(rota_osrm["geometry"]),
                    "attributes": {
                        "IncidentID": i + 1,
                        "FacilityID": j + 1,
                        "FacilityRank": len([f for f in feições if f["attributes"]["IncidentID"] == i + 1]) + 1,
                        "Total_Time": d / 60.0,
                        "Total_Length": rota_osrm["distance"],
                    },
                }
            )
    return {"routes": {"features": feições}, "proveniencia": _PROVENIENCIA}


class PedidoSolveODCostMatrix(BaseModel):
    origins: _FeatureSet
    destinations: _FeatureSet
    perfil: str = "carro"


@router.post("/ODCostMatrix/solveODCostMatrix", openapi_extra=X)
def solve_matriz_custo_od(pedido: PedidoSolveODCostMatrix, auth=autenticado(escopo_token="rota:usar")):
    origens = _pontos_de(pedido.origins, "origins")
    destinos = _pontos_de(pedido.destinations, "destinations")
    n, m = len(origens), len(destinos)
    if n * m > settings.PLAT_ROTA_MATRIZ_JOB_MAX:
        raise ErroAPI(
            422,
            "matriz_grande_demais",
            f"{n}×{m} excede o teto de {settings.PLAT_ROTA_MATRIZ_JOB_MAX} células por job",
            {"origens": n, "destinos": m, "teto": settings.PLAT_ROTA_MATRIZ_JOB_MAX},
        )
    if n * m > settings.PLAT_ROTA_MATRIZ_MAX:
        resposta = osrm.matriz_grande(origens, destinos, pedido.perfil)
    else:
        resposta = osrm.matriz(origens, destinos, pedido.perfil)
    duracoes = resposta.get("durations") or []
    distancias = resposta.get("distances") or []
    feições = [
        {
            "attributes": {
                "OriginID": i + 1,
                "DestinationID": j + 1,
                "Total_Time": (duracoes[i][j] or 0) / 60.0,
                "Total_Length": distancias[i][j] or 0,
            }
        }
        for i in range(n)
        for j in range(m)
        if duracoes[i][j] is not None
    ]
    return {"odCostMatrix": {"features": feições}, "proveniencia": _PROVENIENCIA}
