"""Modelos de `/api/camadas/{id}/regras`, `/validar`, `/feicoes` e `/erros` (item L2-10-d-regras-de-atributo).
Entrada com extra=forbid (padrão de app/edicao/modelos.py); a forma fina das regras é validada pelo esquema JSON
do tipo `camada_vetorial` (v4) e pelo motor (expressão, campos, ciclo)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class RegraEntrada(Modelo):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    tipo: str = Field(pattern=r"^(calculo|restricao|validacao)$")
    expressao: str = Field(min_length=1, max_length=limites.REGRAS_EXPRESSAO_TEXTO_MAX)
    nome: str | None = Field(default=None, max_length=200)
    campo: str | None = Field(default=None, max_length=63)
    gatilhos: list[str] | None = Field(default=None, max_length=500)
    eventos: list[str] | None = Field(default=None, max_length=2)
    ordem: int = Field(default=0, ge=0, le=100_000)
    habilitada: bool = True
    mensagem: str | None = Field(default=None, max_length=limites.REGRAS_MENSAGEM_MAX)
    codigo: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,62}$")
    excluir_em_massa: bool = False


class CampoVirtualEntrada(Modelo):
    nome: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    expressao: str = Field(min_length=1, max_length=limites.REGRAS_EXPRESSAO_TEXTO_MAX)
    alias: str | None = Field(default=None, max_length=200)


class RegrasEntrada(Modelo):
    regras: list[RegraEntrada] = Field(default_factory=list, max_length=limites.REGRAS_POR_CAMADA_MAX)
    campos_virtuais: list[CampoVirtualEntrada] = Field(
        default_factory=list, max_length=limites.REGRAS_CAMPOS_VIRTUAIS_MAX
    )


class RegrasSaida(Saida):
    camada_id: str
    regras: list[dict[str, Any]]
    campos_virtuais: list[dict[str, Any]]
    validacao: dict[str, Any] | None = None
    ordem_de_avaliacao: list[str]


class ValidarSaida(Saida):
    job_id: str
    estado: str


class FeicoesSaida(Saida):
    total: int
    itens: list[dict[str, Any]]
    campos_virtuais: list[str]


class ErrosSaida(Saida):
    total: int
    itens: list[dict[str, Any]]
    validacao: dict[str, Any] | None = None
