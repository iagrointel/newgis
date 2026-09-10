"""Modelos pydantic das rotas de versionamento por ramo (item L2-13-a). Entrada com extra=forbid, como o
resto do repositório."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionarEntrada(Modelo):
    ramos_max: int | None = Field(default=None, ge=1, le=limites.VERSOES_POR_CAMADA_MAX)


class VersaoEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.VERSAO_NOME_MAX)
    descricao: str | None = Field(default=None, max_length=2048)
    acesso: str = Field(default="protegido", pattern="^(privado|protegido|publico)$")


class ResolverEntrada(Modelo):
    decisao: str = Field(pattern="^(ramo|padrao|manual)$")
    atributos: dict[str, Any] | None = Field(default=None, max_length=limites.EDICAO_ATRIBUTOS_MAX)
    geometria: dict[str, Any] | None = None


class PublicarEntrada(Modelo):
    modo: str = Field(default="fechar", pattern="^(fechar|rebasear)$")
