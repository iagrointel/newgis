"""Rotas do serviço transversal de CRS (item L2-17-crs-transformacoes): `GET /api/crs` (lista, curada
primeiro), `GET /api/crs/{epsg}` (detalhe), `GET /api/crs/{epsg}.proj4` (definição para proj4js no
navegador — as mesmas definições que o backend usa, para nunca divergir) e `POST /api/crs/transformar`
(ponto ou bbox, com a transformação usada declarada na resposta — nunca silenciosa).

Sem tabela `plat.*` própria e sem RLS (mesmo padrão de `app/rede/rotas.py`, L2-11-c): não há linha de
banco por inquilino aqui, só cálculo sobre o registro EPSG do PROJ e as grades do IBGE."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, field_validator

from app.auth.sessao import autenticado
from app.crs import registro, servico
from app.erros import ErroAPI

router = APIRouter(prefix="/api/crs", tags=["crs"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}


def _json_descritor(d) -> dict:
    return {
        "epsg": d.epsg,
        "nome": d.nome,
        "tipo": d.tipo,
        "area_nome": d.area_nome,
        "bounds": list(d.bounds) if d.bounds else None,
        "curada": d.curada,
        "motivo_curada": d.motivo_curada,
    }


@router.get("", openapi_extra=X)
def listar_crs(auth=autenticado(escopo_token="crs:usar")):
    lista = registro.listar()
    return {
        "total": len(lista),
        "curados": sum(1 for d in lista if d.curada),
        # ordem preservada de propósito (curada primeiro) — é a cláusula "lista curada aparece
        # primeiro nos seletores"; o seletor do navegador (web/js/crs/crs.js) não reordena.
        "itens": [_json_descritor(d) for d in lista],
    }


# ORDEM IMPORTA: Starlette casa rotas na ordem de registro, e "{epsg}" (sem sufixo) é `[^/]+` — casaria
# "31982.proj4" inteiro como epsg="31982.proj4" se viesse ANTES. `/{epsg}.proj4` tem de ser declarada
# primeiro (achado ao testar: sem isto, GET /api/crs/31982.proj4 caía em detalhar_crs com epsg inválido).
@router.get("/{epsg}.proj4", openapi_extra=X)
def proj4_crs(epsg: int, auth=autenticado(escopo_token="crs:usar")):
    texto = registro.proj4(epsg)
    if texto is None:
        raise ErroAPI(422, "crs_inexistente", f"EPSG:{epsg} não existe no registro do PROJ desta máquina")
    return Response(content=texto, media_type="text/plain; charset=utf-8")


@router.get("/{epsg}", openapi_extra=X)
def detalhar_crs(epsg: int, auth=autenticado(escopo_token="crs:usar")):
    d = registro.obter(epsg)
    if d is None:
        raise ErroAPI(422, "crs_inexistente", f"EPSG:{epsg} não existe no registro do PROJ desta máquina")
    return _json_descritor(d)


class PedidoTransformar(BaseModel):
    origem: int = Field(..., description="código EPSG de origem")
    destino: int = Field(..., description="código EPSG de destino")
    tipo: Literal["ponto", "bbox"] = "ponto"
    coordenadas: list[float] = Field(
        ..., description="[lon, lat] para ponto; [xmin, ymin, xmax, ymax] para bbox (na ordem do CRS de origem)"
    )

    @field_validator("coordenadas")
    @classmethod
    def _v_coordenadas(cls, v, info):
        esperado = 4 if info.data.get("tipo") == "bbox" else 2
        if len(v) != esperado:
            raise ValueError(f"'coordenadas' precisa de {esperado} números para tipo={info.data.get('tipo')}")
        return v


@router.post("/transformar", openapi_extra=X)
def transformar(pedido: PedidoTransformar, auth=autenticado(escopo_token="crs:usar")):
    if registro.obter(pedido.origem) is None:
        raise ErroAPI(422, "crs_inexistente", f"EPSG:{pedido.origem} (origem) não existe no registro do PROJ")
    if registro.obter(pedido.destino) is None:
        raise ErroAPI(422, "crs_inexistente", f"EPSG:{pedido.destino} (destino) não existe no registro do PROJ")
    try:
        if pedido.tipo == "ponto":
            lon, lat = pedido.coordenadas
            r = servico.transformar_ponto(lon, lat, pedido.origem, pedido.destino)
            return {
                "tipo": "ponto",
                "coordenadas": [r.lon, r.lat],
                "transformacao_usada": r.transformacao_usada,
                "cobertura": r.cobertura,
            }
        xmin, ymin, xmax, ymax = pedido.coordenadas
        if xmin > xmax or ymin > ymax:
            raise ErroAPI(422, "bbox_invalido", "bbox exige xmin<=xmax e ymin<=ymax", pedido.coordenadas)
        r = servico.transformar_bbox((xmin, ymin, xmax, ymax), pedido.origem, pedido.destino)
        return {
            "tipo": "bbox",
            "coordenadas": list(r["bbox"]),
            "transformacoes_usadas": r["transformacoes_usadas"],
            "cobertura_uniforme": r["cobertura_uniforme"],
        }
    except servico.EixoSuspeitoErro as e:
        raise ErroAPI(422, "eixos_suspeitos", str(e)) from e
    except servico.CRSInexistenteErro as e:
        raise ErroAPI(422, "transformacao_indisponivel", str(e)) from e
