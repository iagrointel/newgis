"""Modelos de entrada e saída do traçado de custo mínimo (item L3-10-corredor-custo-minimo)."""

from pydantic import BaseModel, ConfigDict, Field

from app import limites
from app.amc import corredor as motor
from app.amc.corredor_execucao import SEM_DADO


class Saida(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ponto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)


class CorredorEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origem: Ponto
    destino: Ponto
    custo_maximo: float = Field(
        10.0, gt=1.0, le=1000.0,
        description="custo da pior nota (a melhor custa 1); a regra é linear e sai no manifesto")
    sem_dado: str = Field("veto", description=f"célula sem nota: um de {SEM_DADO}")
    veto_abaixo_de: float | None = Field(None, ge=0.0, le=100.0, description="nota abaixo da qual a célula é veto")
    veto_nao_aprovadas: bool = Field(False, description="célula não aprovada pela execução vira veto")
    vizinhanca: int = Field(16, description=f"um de {motor.VIZINHANCAS}")
    epsilon: float | None = Field(0.05, ge=0.0, le=1.0,
                                  description="folga do corredor (0,05 = +5 %); nulo devolve só a linha")


class Manifesto(Saida):
    superficie: dict
    parametros: dict
    medidas: dict


class CorredorSaida(Saida):
    execucao_id: str
    linha: dict = Field(..., description="LineString GeoJSON em EPSG:4326 pelo centro das células")
    corredor: dict | None = Field(None, description="MultiPolygon GeoJSON do corredor-epsilon, quando cabe")
    corredor_celulas: int
    corredor_geometria_omitida: bool = Field(
        False, description=f"corredor acima de {limites.CORREDOR_CELULAS_GEOJSON_MAX} células: só a contagem")
    manifesto: Manifesto
    duracao_ms: int
