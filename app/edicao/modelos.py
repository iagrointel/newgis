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
    # ramo de versão em que a edição entra (item L2-13-a): identificador ou nome do ramo. Ausente = a
    # edição vai para o PADRÃO, que é o comportamento de sempre desta rota.
    versao: str | None = Field(default=None, min_length=1, max_length=128)
    crs: Crs | None = None  # ausente = geometria já está no SRID da camada
    corrigir_geometria: bool = False  # ST_MakeValid + relatório; sem isto, polígono inválido é 422 (portão cl.5)
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


class AnexoEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    conteudo: str = Field(min_length=1)  # base64


class RestaurarSaida(Saida):
    sucesso: bool
    id: str
    fid: int | None = None
    versao: int | None = None
    recriada: bool
    avisos: list[str] = Field(default_factory=list)


class UniaoEntrada(Modelo):
    # `versoes` é OBRIGATÓRIO (achado do adversário 07/09: com default {}, a checagem de concorrência
    # de `_conferir_versao` só roda para os ids presentes no dict — mandar {} pulava a detecção por
    # completo, silenciosamente descartando uma edição concorrente da feição de origem).
    ids: list[str] = Field(min_length=2, max_length=200)
    versoes: dict[str, int]
    atributos: dict[str, Any] | None = None


class DivisaoEntrada(Modelo):
    # `versao` OBRIGATÓRIO pelo mesmo motivo (achado do adversário): opcional pulava a concorrência.
    id: str = Field(pattern=UUID_PADRAO)
    versao: int = Field(ge=1)
    ponto: list[float] = Field(min_length=2, max_length=2)
