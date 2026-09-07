"""Modelos pydantic de classe de relacionamento entre camadas (item L2-10-b-relacionamentos)."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.catalogo.modelos import UUID_PADRAO, Modelo, Saida
from app.dominios.modelos import CAMPO_PADRAO

CARDINALIDADES = ("1:1", "1:N", "N:M")


class RelacionamentoEntrada(Modelo):
    origem_item_id: str = Field(pattern=UUID_PADRAO)
    destino_item_id: str = Field(pattern=UUID_PADRAO)
    cardinalidade: str = Field(pattern="^(1:1|1:N|N:M)$")
    chave_origem: str = Field(default="globalid", pattern=CAMPO_PADRAO)
    chave_destino: str = Field(default="globalid", pattern=CAMPO_PADRAO)
    composto: bool = False
    nome_direto: str = Field(min_length=1, max_length=120)
    nome_inverso: str = Field(min_length=1, max_length=120)
    cardinalidade_min: int | None = Field(default=None, ge=0)
    cardinalidade_max: int | None = Field(default=None, ge=1)
    limite_relacionados: int = Field(default=2000, ge=1, le=100000)

    @model_validator(mode="after")
    def _coerente(self):
        if self.composto and self.cardinalidade not in ("1:1", "1:N"):
            raise ValueError("composto só se aplica a 1:1 ou 1:N (N:M não tem chave estrangeira)")
        if (self.cardinalidade_min is not None and self.cardinalidade_max is not None
                and self.cardinalidade_min > self.cardinalidade_max):
            raise ValueError("cardinalidade_min maior que cardinalidade_max")
        return self


class RelacionamentoSaida(Saida):
    id: str
    origem_item_id: str
    destino_item_id: str
    cardinalidade: str
    chave_origem: str
    chave_destino: str
    composto: bool
    nome_direto: str
    nome_inverso: str
    cardinalidade_min: int | None
    cardinalidade_max: int | None
    limite_relacionados: int
    criado_em: str | None = None


class ParEntrada(Modelo):
    origem_valor: str = Field(min_length=1, max_length=200)
    destino_valor: str = Field(min_length=1, max_length=200)
