"""Modelos pydantic do motor de grades aninhadas (item L3-19-multiescala).

Entrada e saída das quatro peças do fluxo: conjunto (área de estudo + CRS resolvido), fator (com a escala
nativa DECLARADA), amostra (ponto + valor bruto do fator) e execução (macro ou micro, com o relatório por
fator que marca `escala_grosseira` — a refutação do item)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------ conjunto (área de estudo)


class ConjuntoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=limites.ESCALA_NOME_MAX)
    area: dict = Field(..., description="polígono GeoJSON (Polygon) em EPSG:4326")


class Conjunto(Saida):
    id: str
    nome: str
    srid_trabalho: int
    srid_nome: str
    origem_x_m: float
    origem_y_m: float
    largura_m: float
    altura_m: float
    criado_em: str


class ConjuntoPagina(Saida):
    total: int
    itens: list[Conjunto]


# ------------------------------------------------------------------ fator


class FatorEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=limites.ESCALA_NOME_MAX)
    resolucao_fonte_m: float = Field(..., gt=0, description="escala nativa DECLARADA da fonte, em metros")
    papel: Literal["atrai", "custo"]
    unidade: str = Field("", max_length=limites.ESCALA_UNIDADE_MAX)
    fonte: str = Field("", max_length=limites.ESCALA_FONTE_MAX)


class Fator(Saida):
    id: str
    nome: str
    resolucao_fonte_m: float
    papel: str
    unidade: str
    fonte: str
    criado_em: str


class FatorPagina(Saida):
    total: int
    itens: list[Fator]


# ------------------------------------------------------------------ amostra


class AmostraEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    valor: float


class AmostrasEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amostras: list[AmostraEntrada] = Field(..., min_length=1, max_length=limites.ESCALA_AMOSTRAS_LOTE_MAX)


class AmostrasResultado(Saida):
    fator_id: str
    gravadas: int


# ------------------------------------------------------------------ execução (macro e micro)


class FatorPesoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fator_id: str
    peso: float = Field(..., gt=0)


class ExecucaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolucao_m: float = Field(..., gt=0)
    fatores: list[FatorPesoEntrada] = Field(..., min_length=1, max_length=limites.ESCALA_FATORES_MAX)
    aprovacao_tipo: Literal["limiar", "top_pct"]
    aprovacao_valor: float = Field(..., ge=0)


class GradeSaida(Saida):
    id: str
    nivel: str
    resolucao_m: float
    fator_aninhamento: int | None = None
    colunas: int
    linhas: int
    celulas: int
    celulas_possiveis: int


class ExecucaoFatorSaida(Saida):
    fator_id: str
    nome: str
    peso: float
    resolucao_fonte_m: float
    resolucao_grade_m: float
    razao_escala: float
    escala: str
    escala_grosseira: bool
    blocos_usados: int
    blocos_calculados: int
    celulas_com_dado: int
    valor_min: float | None = None
    valor_max: float | None = None


class Execucao(Saida):
    id: str
    conjunto_id: str
    nivel: str
    execucao_pai_id: str | None = None
    aprovacao_tipo: str
    aprovacao_valor: float
    celulas: int
    celulas_possiveis: int
    celulas_com_nota: int
    celulas_aprovadas: int
    duracao_ms: int
    criado_em: str
    grade: GradeSaida
    fatores: list[ExecucaoFatorSaida]


class ExecucaoPagina(Saida):
    total: int
    itens: list[Execucao]
