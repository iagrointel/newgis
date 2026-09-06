"""Modelos de entrada e saída das rotas de identidade e numeração de ativos
(item L4-28-identificadores-e-numeracao)."""

from pydantic import BaseModel, Field


class AtivoEntrada(BaseModel):
    tipo_id: str = Field(min_length=36, max_length=36)
    codigo_externo: str | None = Field(default=None, min_length=1, max_length=100)
    numero: int | None = Field(default=None, ge=1)


class Ativo(BaseModel):
    global_id: str
    rede_id: str
    tipo_id: str
    tipo_chave: str
    numero: int
    codigo: str
    codigo_externo: str | None
    criado_por: dict
    criado_em: str
    atualizado_em: str


class AtivoPagina(BaseModel):
    total: int
    itens: list[Ativo]


class RenomeacaoEntrada(BaseModel):
    codigo_externo: str = Field(min_length=1, max_length=100)


class Renomeacao(BaseModel):
    codigo_externo_anterior: str | None
    codigo_externo_novo: str
    renomeado_por: dict
    renomeado_em: str


class RenomeacaoLista(BaseModel):
    total: int
    itens: list[Renomeacao]


class FaixaEntrada(BaseModel):
    tipo_id: str = Field(min_length=36, max_length=36)
    quantidade: int = Field(ge=1, le=100_000)


class Faixa(BaseModel):
    id: str
    tipo_id: str
    inicio: int
    fim: int
    tamanho: int
    consumidos: int
    estado: str
    criado_em: str
    liberada_em: str | None
    usuario_id: int | None = None
    dono: str | None = None


class FaixaPagina(BaseModel):
    total: int
    itens: list[Faixa]
