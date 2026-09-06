"""Modelos pydantic do motor AMC (item L3-01-a-modelo-dado). Mesma disciplina de app/catalogo/modelos.py:
entrada com extra=forbid, saída com extra=allow. `definicao` é `dict` solto de propósito — a validação real
é em duas camadas por app/amc/esquema.py (JSON Schema + semântica), não pelo pydantic."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import limites

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---- modelo
class ModeloEntrada(Entrada):
    nome: str = Field(min_length=1, max_length=limites.AMC_NOME_MAX)
    definicao: dict[str, Any]


class ModeloEditar(Entrada):
    nome: str | None = Field(default=None, min_length=1, max_length=limites.AMC_NOME_MAX)
    definicao: dict[str, Any] | None = None


class ValidarEntrada(Entrada):
    definicao: dict[str, Any]


class Modelo(Saida):
    id: str
    nome: str
    definicao: dict
    versao_hash: str
    executado: bool
    criado_em: str | None
    atualizado_em: str | None


class ModeloValidado(Saida):
    valido: bool
    versao_hash: str | None = None
    erros: list[dict] = []


class ModeloPagina(Saida):
    total: int
    itens: list[Any]


# ---- conjunto de unidades
class ConjuntoEntrada(Entrada):
    nome: str = Field(min_length=1, max_length=limites.AMC_NOME_MAX)
    tipo: str = Field(pattern="^(hexagonal|quadrada|feicoes)$")
    lado_m: float | None = Field(default=None, gt=0)
    n_unidades: int | None = Field(default=None, ge=0)
    config: dict[str, Any] = Field(default_factory=dict)


class Conjunto(Saida):
    id: str
    nome: str
    tipo: str
    lado_m: float | None
    n_unidades: int | None
    config: dict
    criado_em: str | None


class ConjuntoPagina(Saida):
    total: int
    itens: list[Any]


# ---- execução
class CamadaEntrada(Entrada):
    """Proveniência DECLARADA de uma camada de entrada (A10): id do item/fonte, sha256 ou 'nao_registrado',
    contagem ou null. A resolução automática (medir de verdade a camada hospedada) é do item de extração
    (L3-01-c); aqui a execução só CONGELA o que foi declarado no momento em que rodou."""

    id: str = Field(min_length=1, max_length=200)
    papel: str | None = Field(default=None, max_length=100)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    contagem: int | None = Field(default=None, ge=0)


class ExecucaoEntrada(Entrada):
    modelo_id: str = Field(pattern=UUID_PADRAO)
    conjunto_id: str = Field(pattern=UUID_PADRAO)
    pesos: dict[str, float] = Field(default_factory=dict, max_length=limites.AMC_FATORES_MAX)
    camadas: list[CamadaEntrada] = Field(default_factory=list, max_length=limites.AMC_CAMADAS_MAX)
    semente: int | None = Field(default=None, ge=0, le=2**63 - 1)

    @field_validator("pesos")
    @classmethod
    def _pesos_nao_negativos(cls, v: dict[str, float]) -> dict[str, float]:
        negativos = sorted(k for k, p in v.items() if p < 0)
        if negativos:
            raise ValueError(f"pesos negativos: {negativos}")
        return v


class Execucao(Saida):
    id: str
    modelo_id: str
    modelo_versao_hash: str
    conjunto_id: str
    pesos: dict
    camadas: list
    motor_versao: str
    semente: int
    estado: str
    criado_em: str | None
    atualizado_em: str | None


class ExecucaoPagina(Saida):
    total: int
    itens: list[Any]


class Resultado(Saida):
    unidade_id: str
    favorabilidade: float | None
    vetado: bool
    motivo: str | None
    cobertura: float | None


class ResultadoPagina(Saida):
    total: int
    itens: list[Any]
