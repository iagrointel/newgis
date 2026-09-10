"""Modelos de entrada e saída das rotas de rede de utilidades. O PACOTE em si não passa por pydantic: entra e
sai como bytes, validado pelo esquema JSON (`app/rede_utilidades/esquema.py`), porque a mensagem de erro
precisa apontar a linha do arquivo que a pessoa enviou. O mesmo vale para o CSV de regras (mensagem com a
linha da planilha). O applyEdits, ao contrário, é JSON de API e passa por pydantic com extra="forbid":
campo a mais no corpo (por exemplo um hipotético "ignorar_regras") é 422 na entrada, não silêncio."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.rede_utilidades.esquema import DISCIPLINAS


class RedeEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    disciplina: str = Field(pattern="^(" + "|".join(DISCIPLINAS) + ")$")
    descricao: str | None = Field(default=None, max_length=2000)


class Rede(BaseModel):
    id: str
    nome: str
    disciplina: str
    descricao: str | None
    pacote: dict | None
    regras_ativas: bool
    contagens: dict
    dono: dict
    criado_em: str
    atualizado_em: str


class RedePagina(BaseModel):
    total: int
    itens: list[Rede]


class PacoteInstalado(BaseModel):
    codigo: str
    nome: str
    versao: str
    disciplina: str
    descricao: str | None = None
    fonte: str | None = None
    bytes: int
    sha256: str
    contagens: dict


class PacoteInstaladoLista(BaseModel):
    total: int
    itens: list[PacoteInstalado]


class ImportacaoResultado(BaseModel):
    rede_id: str
    codigo: str
    versao: str
    esquema_versao: int
    sha256: str
    bytes: int
    contagens: dict


# --- applyEdits e ativação de regras (item L4-03-a-regras-de-conectividade) ---------------------------------

MAX_POR_LOTE = 1000  # teto declarado de operações de cada tipo num applyEdits


class FeicaoAdicionar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grupo: str = Field(min_length=1, max_length=62)
    tipo: int = Field(ge=1, le=32767)
    geometria: dict[str, Any] | None = None  # GeoJSON da geometria (Point/LineString, WGS84)
    atributos: dict[str, Any] = Field(default_factory=dict)
    terminal_inicio: str | None = Field(default=None, min_length=1, max_length=62)
    terminal_fim: str | None = Field(default=None, min_length=1, max_length=62)


class FeicaoAtualizar(BaseModel):
    """Grupo e tipo NÃO mudam (mudança de classe é apagar + adicionar); só geometria, atributos e os
    terminais declarados nas pontas."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=36, max_length=36)
    geometria: dict[str, Any] | None = None
    atributos: dict[str, Any] | None = None
    terminal_inicio: str | None = Field(default=None, min_length=1, max_length=62)
    terminal_fim: str | None = Field(default=None, min_length=1, max_length=62)


class AssociacaoAdicionar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(pattern="^(contencao|estrutura)$")
    de: str = Field(min_length=36, max_length=36)
    para: str = Field(min_length=36, max_length=36)


class AssociacoesLote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adicionar: list[AssociacaoAdicionar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    apagar: list[str] = Field(default_factory=list, max_length=MAX_POR_LOTE)


class ApplyEditsEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adicionar: list[FeicaoAdicionar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    atualizar: list[FeicaoAtualizar] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    apagar: list[str] = Field(default_factory=list, max_length=MAX_POR_LOTE)
    associacoes: AssociacoesLote = Field(default_factory=AssociacoesLote)


class AtivacaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ativa: bool


class ApplyEditsResultado(BaseModel):
    rede_id: str
    regras_ativas: bool
    adicionadas: list[str]
    atualizadas: int
    apagadas: int
    associacoes_adicionadas: int
    associacoes_apagadas: int
    conexoes: int  # conexões derivadas novas (jj + je) gravadas neste lote
    area_sujas_criadas: int = 0  # item L4-03-d-areas-sujas-e-validacao: 1 por feição tocada com geometria


class ValidacaoResultado(BaseModel):
    rede_id: str
    regras_ativas: bool
    conexoes_avaliadas: int
    associacoes_avaliadas: int
    total_erros: int
    erros: list[dict]  # cada erro traz codigo, mensagem e a lista de feições envolvidas


class AtivacaoResultado(BaseModel):
    rede_id: str
    regras_ativas: bool


class ImportacaoRegrasResultado(BaseModel):
    rede_id: str
    total: int
    sha256: str
    bytes: int


# --- áreas sujas e validação incremental (item L4-03-d-areas-sujas-e-validacao) -----------------------------

class ValidacaoExtensaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extensao: dict[str, Any] | None = None  # GeoJSON de polígono; None = todas as áreas sujas ativas ("tudo")


class ValidacaoExtensaoResultado(BaseModel):
    rede_id: str
    versao_edicao: int
    areas_processadas: int
    areas_ativas_restantes: int
    feicoes_em_escopo: int
    feicoes_total: int
    total_erros: int
    erros: list[dict]
    tempo_ms: float
    carga_1min: float
    ram_livre_gb: float
    medido_em: str


class TracadoResultado(BaseModel):
    rede_id: str
    cruza_area_suja: bool
    bloqueado: bool
    modo: str
    area_suja: dict | None = None


class ModoTracadoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modo: str = Field(pattern="^(avisar|bloquear)$")


class ModoTracadoResultado(BaseModel):
    rede_id: str
    modo: str
