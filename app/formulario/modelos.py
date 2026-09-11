"""Modelos pydantic do módulo formulário (item L5-03-form-builder). Mesmo padrão de
`app/edicao/modelos.py`: entrada com `extra="forbid"`, saída com `extra="allow"`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class FormularioCriar(Modelo):
    nome: str = Field(default="Formulário", min_length=1, max_length=250)


class VersaoSalvar(Modelo):
    # o desenho inteiro (grupos -> campos); ver app/formulario/motor.py para o formato e o limite de
    # tamanho é o mesmo de app/limites.py usado pelo resto do catálogo de item (ITEM_DESCRICAO_MAX),
    # generoso o bastante para um formulário com muitos campos sem abrir uma porta de negação de serviço
    desenho: dict[str, Any]


class FormularioSaida(Saida):
    id: str
    camada_id: str
    nome: str
    publicado_versao: int | None = None
    criado_em: str
    atualizado_em: str


class VersaoSaida(Saida):
    id: str
    versao: int
    publicado: bool
    criado_em: str
    desenho: dict[str, Any] | None = None
