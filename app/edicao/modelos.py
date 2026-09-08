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


# ---------------------------------------------------------------- edição em lote (item L2-03-f)
OPERACOES_LOTE = ("calcular", "atribuir", "apagar", "corrigir_geometria", "copiar", "mover")


class LoteSelecao(Modelo):
    """Exatamente uma das três formas: `ids` (globalids), `onde` (expressão booleana da linguagem L2-10-c sobre
    os campos da camada) ou `todas`."""

    ids: list[str] | None = Field(default=None, max_length=limites.LOTE_IDS_MAX)
    onde: str | None = Field(default=None, max_length=20_000)
    todas: bool = False


class LoteDestino(Modelo):
    camada: str = Field(pattern=UUID_PADRAO)
    mapeamento: dict[str, str] = Field(default_factory=dict, max_length=limites.LOTE_MAPEAMENTO_MAX)


class LoteEntrada(Modelo):
    operacao: str = Field(pattern="^(calcular|atribuir|apagar|corrigir_geometria|copiar|mover)$")
    selecao: LoteSelecao
    campo: str | None = Field(default=None, max_length=63)
    expressao: str | None = Field(default=None, max_length=20_000)
    valor: Any = None
    destino: LoteDestino | None = None
    modo: str = Field(default="transacao", pattern="^(transacao|parcial)$")
    previa: bool = False
    avaliacao: str = Field(default="auto", pattern="^(auto|sql|linha_a_linha)$")


class LoteFalha(Saida):
    id: str | None = None
    erro: str
    mensagem: str
    detalhe: Any = None


class LotePrevia(Saida):
    id: str
    antes: Any = None
    depois: Any = None
    erro: str | None = None
    mensagem: str | None = None


class LoteSaida(Saida):
    execucao: str  # sincrono | job | previa
    operacao: str
    total: int
    alteradas: int = 0
    apagadas: int = 0
    criadas: int = 0
    corrigidas: int = 0
    falhas: list[LoteFalha] = Field(default_factory=list)
    falhas_total: int = 0
    avisos: list[str] = Field(default_factory=list)
    traducao: str | None = None  # sql | linha_a_linha (só calcular/onde)
    traducao_motivo: str | None = None
    job_id: str | None = None
    previa: list[LotePrevia] | None = None
    duracao_ms: int | None = None
