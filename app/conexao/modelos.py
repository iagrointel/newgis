"""Modelos pydantic de `plat.conexao` (item L6-02-a-modelo-conexao-e-seguranca). `credencial` é ENTRADA
apenas — nenhum modelo de SAÍDA carrega a credencial, cifrada ou não; `ConexaoSaida.tem_credencial` diz só se
existe, nunca o valor."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class ConexaoEntrada(Modelo):
    tipo: str = Field(pattern="^(" + "|".join(limites.CONEXAO_TIPOS) + ")$")
    nome: str = Field(min_length=1, max_length=limites.CONEXAO_NOME_MAX)
    url: str = Field(min_length=1, max_length=limites.CONEXAO_URL_MAX)
    modo: str = Field(default="referenciada", pattern="^(" + "|".join(limites.CONEXAO_MODOS) + ")$")
    config: dict[str, Any] = Field(default_factory=dict)
    credencial: str | None = Field(default=None, max_length=4096)


class ConexaoEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=limites.CONEXAO_NOME_MAX)
    url: str | None = Field(default=None, min_length=1, max_length=limites.CONEXAO_URL_MAX)
    modo: str | None = Field(default=None, pattern="^(" + "|".join(limites.CONEXAO_MODOS) + ")$")
    config: dict[str, Any] | None = None
    credencial: str | None = Field(default=None, max_length=4096)
    remover_credencial: bool = False


class Dono(Saida):
    id: int
    login: str
    nome: str | None = None


class ConexaoCartao(Saida):
    id: str
    tipo: str
    modo: str
    nome: str
    url: str
    saude: str
    saude_verificada_em: str | None = None


class Conexao(ConexaoCartao):
    config: dict[str, Any]
    tem_credencial: bool
    saude_mensagem: str | None = None
    saude_latencia_ms: int | None = None
    dono: Dono
    criado_em: str
    atualizado_em: str


class ConexaoPagina(Saida):
    total: int
    itens: list[ConexaoCartao]


class ConexaoTeste(Saida):
    ok: bool
    status: int | None = None
    mensagem: str
    latencia_ms: int
    saude: str
    saude_verificada_em: str
