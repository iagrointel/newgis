"""Modelos pydantic do inventário de Portal/AGOL (item L2-08-a-leitor-portal-inventario). Nenhum modelo de
saída carrega token, senha ou e-mail: o que existe na entrada (`usuario`/`senha` para `generateToken`) nunca
volta em nenhuma resposta e nunca é gravado."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class InventarioEntrada(Modelo):
    conexao_id: str = Field(min_length=36, max_length=36)
    # credencial por usuário/senha: o backend chama generateToken e guarda SÓ o token cifrado na conexão.
    # Ausente = usa o token já registrado na conexão (ou nenhum, para portal público).
    usuario: str | None = Field(default=None, max_length=200)
    senha: str | None = Field(default=None, max_length=200)


class InventarioCartao(Saida):
    id: str
    conexao_id: str
    estado: str
    portal_url: str
    portal_nome: str | None = None
    portal_versao: str | None = None
    totais: dict[str, Any] = {}
    job_id: str | None = None
    mensagem: str | None = None
    criado_em: str
    atualizado_em: str


class InventarioDetalhe(InventarioCartao):
    portal_id: str | None = None
    retomada: dict[str, Any] = {}
    por_tipo: list[dict[str, Any]] = []
    por_classificacao: dict[str, int] = {}
    grupos: int = 0
    usuarios: int = 0


class InventarioPagina(Saida):
    total: int
    itens: list[InventarioCartao]


class ItemPagina(Saida):
    total: int
    itens: list[dict[str, Any]]


# ------------------------------------------------------------------ clonagem (item L2-08-b)
class CloneEntrada(Modelo):
    conexao_id: str = Field(min_length=36, max_length=36)
    url_servico: str = Field(min_length=12, max_length=2048)  # .../rest/services/<nome>/FeatureServer
    camadas: list[int] | None = Field(default=None, max_length=200)  # ausente = todas as camadas e tabelas


class CloneCartao(Saida):
    id: str
    conexao_id: str
    url_servico: str
    estado: str
    camadas_pedidas: list[int] | None = None
    job_id: str | None = None
    mensagem: str | None = None
    camadas: list[dict[str, Any]] = []
    relatorio: dict[str, Any] = {}
    criado_em: str
    atualizado_em: str


class ClonePagina(Saida):
    total: int
    itens: list[CloneCartao]
