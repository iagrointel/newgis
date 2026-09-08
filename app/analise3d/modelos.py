"""Modelos pydantic da análise 3D (item L2-09-d): entrada das quatro rotas e blocos de resposta.

`salvar_item` presente na entrada = o resultado vira item `analise_3d` do catálogo, criado pela MESMA
rota de criação de item do L0-03 (`app/catalogo/rotas_itens.criar`), que já leva cota de itens, validação
do JSON Schema do tipo, evento `itens/adicionar` e RLS; a resposta da análise devolve o `item_id`.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.analise3d.terreno import Terreno


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SalvarItemEntrada(Modelo):
    """O que o usuário escolhe para o item do catálogo; o `dados` do item é montado pelo servidor."""

    titulo: str = Field(..., min_length=1, max_length=250)
    resumo: str | None = Field(default=None, max_length=2048)
    tags: list[str] = Field(default_factory=list, max_length=50)


class VisadaEntrada(Modelo):
    terreno: Terreno
    observador: tuple[float, float]
    alvo: tuple[float, float]
    altura_observador_m: float = Field(
        2.0, ge=-1e6, le=1e6, description="altura do observador SOBRE o terreno; negativa = abaixo (422)"
    )
    altura_alvo_m: float = Field(0.0, ge=-1e6, le=1e6)
    passo_m: float | None = Field(None, gt=0, description="passo máximo da amostragem; padrão = metade da célula")
    salvar_item: SalvarItemEntrada | None = None


class ViewshedEntrada(Modelo):
    terreno: Terreno
    observador: tuple[float, float]
    altura_observador_m: float = Field(2.0, ge=-1e6, le=1e6)
    altura_alvo_m: float = Field(0.0, ge=0, le=1e6, description="altura do objeto a ver (gdal_viewshed -tz)")
    distancia_max_m: float | None = Field(
        None, gt=0, description="gdal_viewshed -md; o raster sai recortado à janela"
    )
    coef_curvatura: float = Field(
        0.85714, gt=0, le=1.0, description="gdal_viewshed -cc; 0.85714 = refração atmosférica padrão"
    )
    modo: Literal["normal", "dem", "ground"] = "normal"
    visivel_valor: int = Field(255, ge=0, le=255)
    invisivel_valor: int = Field(128, ge=0, le=255)
    fora_de_alcance_valor: int = Field(0, ge=0, le=255)
    salvar_item: SalvarItemEntrada | None = None


class PerfilEntrada(Modelo):
    terreno: Terreno
    ponto_a: tuple[float, float]
    ponto_b: tuple[float, float]
    n_amostras: int = Field(..., ge=2, le=20_000)
    salvar_item: SalvarItemEntrada | None = None


class SolidoEntrada(Modelo):
    poligono: dict = Field(..., description="GeoJSON Polygon no SRID declarado")
    altura_m: float = Field(..., gt=0, le=10_000)


class SombraEntrada(Modelo):
    srid: int = Field(..., description="SIRGAS 2000 UTM sul (31965-31985), a mesma faixa do terreno")
    data_hora: str = Field(..., description="instante ISO 8601 com fuso (ex.: 2026-12-21T12:00:00-03:00)")
    solidos: list[SolidoEntrada] = Field(..., min_length=1, max_length=500)
    salvar_item: SalvarItemEntrada | None = None


class ProcedenciaAnalise(Modelo):
    model_config = ConfigDict(extra="allow")

    analise: str
    ferramenta: str
    aproximacao: str
    sha256_terreno: str | None = None
    comando: list[str] | None = None
    versao_gdal: str | None = None


def dados_do_item(
    analise: str, parametros: dict[str, Any], resultado: dict[str, Any], procedencia: dict[str, Any]
) -> dict:
    """`dados` do item analise_3d: os quatro blocos que o JSON Schema do tipo EXIGE."""
    return {
        "analise": analise,
        "parametros": parametros,
        "resultado": resultado,
        "procedencia": procedencia,
    }
