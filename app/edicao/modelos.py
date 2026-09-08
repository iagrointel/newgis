"""Modelos pydantic de `POST /api/camadas/{id}/edicoes` (item L2-03-a). Entrada com extra=forbid (mesmo padrão
de app/catalogo/modelos.py e app/conexao/modelos.py); saída com extra=allow."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class Crs(Modelo):
    srid: int = Field(ge=1, le=limites.EDICAO_SRID_MAX)


class FeicaoAdicionar(Modelo):
    atributos: dict[str, Any] = Field(default_factory=dict, max_length=limites.EDICAO_ATRIBUTOS_MAX)
    geometria: dict[str, Any] | None = None


class FeicaoAtualizar(Modelo):
    id: str = Field(pattern=UUID_PADRAO)
    versao: int = Field(ge=1)  # concorrência otimista: exigida em toda atualização (hipótese do item)
    atributos: dict[str, Any] | None = Field(default=None, max_length=limites.EDICAO_ATRIBUTOS_MAX)
    geometria: dict[str, Any] | None = None


class FeicaoApagar(Modelo):
    id: str = Field(pattern=UUID_PADRAO)
    versao: int | None = Field(default=None, ge=1)  # opcional: quando vem, é conferida como na atualização


class EdicoesEntrada(Modelo):
    modo: str = Field(default="transacao", pattern="^(transacao|parcial)$")
    crs: Crs | None = None  # ausente = geometria já está no SRID da camada
    corrigir_geometria: bool = False  # ST_MakeValid + relatório; sem isto, polígono inválido é 422 (portão cl.5)
    em_massa: bool = False  # L2-10-d: lote de importação em massa — regras com excluir_em_massa não rodam
    adicionar: list[FeicaoAdicionar] = Field(default_factory=list, max_length=limites.EDICAO_LOTE_MAX)
    atualizar: list[FeicaoAtualizar] = Field(default_factory=list, max_length=limites.EDICAO_LOTE_MAX)
    apagar: list[FeicaoApagar] = Field(default_factory=list, max_length=limites.EDICAO_LOTE_MAX)


class ResultadoFeicao(Saida):
    sucesso: bool
    id: str | None = None
    fid: int | None = None
    versao: int | None = None
    atributos: dict[str, Any] | None = None
    erro: str | None = None
    mensagem: str | None = None
    detalhe: Any = None


class EdicoesSaida(Saida):
    modo: str
    adicionar: list[ResultadoFeicao]
    atualizar: list[ResultadoFeicao]
    apagar: list[ResultadoFeicao]
    avisos: list[str] = Field(default_factory=list)
