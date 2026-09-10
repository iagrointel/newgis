"""Modelos pydantic do módulo rede_medicao (item L4-13). Entrada com extra=forbid (mesmo padrão de
app/campo/modelos.py); saída com extra=allow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class LeituraEntrada(Modelo):
    ativo: str = Field(pattern=UUID_PADRAO)
    cod_id: str | None = Field(default=None, max_length=80)
    ts: str = Field(min_length=1, max_length=40, description="ISO-8601, relógio do sensor")
    fonte: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="ex.: simulador, sonda, conector")
    grandeza: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    valor: float
    unidade: str = Field(min_length=1, max_length=10)
    bruta: dict[str, Any] = Field(default_factory=dict, description="leitura crua do sensor, nunca interpretada")


class LeiturasLote(Modelo):
    leituras: list[LeituraEntrada] = Field(min_length=1, max_length=limites.REDE_MEDICAO_LOTE_MAX)


class AtivoConfigEntrada(Modelo):
    cod_id: str | None = Field(default=None, max_length=80)
    kva_nominal: float | None = Field(default=None, gt=0, le=1_000_000)
    tensao_nominal_v: float | None = Field(default=None, gt=0, le=1_000_000)


class LeituraSaida(Saida):
    grandeza: str
    valor: float
    unidade: str
    ts: str
    fonte: str


__all__ = ["LeituraEntrada", "LeiturasLote", "AtivoConfigEntrada", "LeituraSaida"]
