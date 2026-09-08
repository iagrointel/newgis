"""Rota `/api/amc/similaridade` (item L3-17-similaridade): "localização semelhante"/"Find Similar Locations".
Sem tabela `plat.*` própria e sem estado — o pedido traz a matriz fator×unidade inteira e a API devolve o
ranking na hora (mesmo padrão de `app/rede/rotas.py`: cálculo sobre o que chegou, não sobre linha de banco do
inquilino; por isso não há RLS aqui, P6 não se aplica). Privilégio `analise.amc` (o mesmo do resto do motor
multicritério, `app/auth/privilegios.py`), leitura ou escrita — o pedido não muda estado nenhum, mas ainda
assim exige o privilégio de analista para não abrir cálculo de graça a qualquer sessão autenticada."""

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from app import limites
from app.amc import similaridade as motor
from app.auth.sessao import autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api/amc", tags=["amc"])
X = {"x-auth": "S/T", "x-privilegio": "analise.amc"}


class PedidoSimilaridade(BaseModel):
    unidades: dict[str, dict[str, float | None]] = Field(
        ..., min_length=1,
        description="{unidade_id: {campo: valor|null}} — a matriz fator×unidade já extraída (execução do "
                    "motor AMC, upload, ou qualquer outra fonte).",
    )
    referencias: list[str] = Field(..., min_length=1, description="ids de unidade que 'deram certo' (1-N).")
    campos: list[str] | None = Field(
        None, description="subconjunto de fatores a comparar (escolha de campos); omitido = todos os vistos.",
    )
    metrica: Literal["cosseno", "euclidiana"] = "cosseno"

    @field_validator("unidades")
    @classmethod
    def _v_unidades(cls, v):
        if len(v) > limites.SIMILARIDADE_UNIDADES_MAX:
            raise ValueError(f"no máximo {limites.SIMILARIDADE_UNIDADES_MAX} unidades por pedido; vieram {len(v)}")
        return v

    @field_validator("referencias")
    @classmethod
    def _v_referencias(cls, v):
        if len(v) > limites.SIMILARIDADE_REFERENCIAS_MAX:
            raise ValueError(f"no máximo {limites.SIMILARIDADE_REFERENCIAS_MAX} referências; vieram {len(v)}")
        return v

    @field_validator("campos")
    @classmethod
    def _v_campos(cls, v):
        if v is not None and len(v) > limites.SIMILARIDADE_CAMPOS_MAX:
            raise ValueError(f"no máximo {limites.SIMILARIDADE_CAMPOS_MAX} campos; vieram {len(v)}")
        return v


def _resultado_json(r: motor.ResultadoSimilaridade) -> dict:
    return {
        "campos": r.campos,
        "metrica": r.metrica,
        "referencias": r.referencias,
        "ranking": r.ranking,
        "excluidas": r.excluidas,
        "estatisticas": r.estatisticas,
    }


def _calcular_ou_422(pedido: PedidoSimilaridade) -> motor.ResultadoSimilaridade:
    try:
        return motor.calcular(pedido.unidades, pedido.referencias, pedido.campos, pedido.metrica)
    except motor.ErroSimilaridade as e:
        raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e


@router.post("/similaridade", openapi_extra=X)
def calcular_similaridade(pedido: PedidoSimilaridade, auth=autenticado("analise.amc")):
    """Ranking por parecença com 1-N unidades de referência, sobre fatores padronizados por z-score. Devolve
    JSON; `/api/amc/similaridade/exportar` devolve o mesmo cálculo em CSV ou GeoJSON."""
    return _resultado_json(_calcular_ou_422(pedido))


@router.post("/similaridade/exportar", openapi_extra=X)
def exportar_similaridade(
    pedido: PedidoSimilaridade,
    auth=autenticado("analise.amc"),
    formato: Literal["csv", "geojson"] = Query("csv"),
):
    """Mesmo cálculo de `/api/amc/similaridade`, exportado (item L3-17, cláusula 'export'). `formato=csv`
    (default) devolve texto CSV (posição, unidade, índice); `formato=geojson` devolve FeatureCollection sem
    geometria (o item não guarda geometria própria — quem tiver, sobrepõe no cliente pelo `unidade_id`)."""
    resultado = _calcular_ou_422(pedido)
    if formato == "geojson":
        return motor.exportar_geojson(resultado)
    return PlainTextResponse(motor.exportar_csv(resultado), media_type="text/csv; charset=utf-8")
