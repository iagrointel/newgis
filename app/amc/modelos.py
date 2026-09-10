"""Modelos pydantic dos presets do motor multicritério (item L3-01-h-presets).

Entrada e saída do CRUD, da aplicação síncrona (sem job) e da importação. O conteúdo do preset é
um `dict` aqui e é validado por `app.amc.presets.validar_conteudo` (que devolve códigos de erro
estáveis com a lista do que falta) — a recusa fina é do módulo puro, não do esquema.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class PresetEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=200)
    descricao: str = Field("", max_length=limites.AMC_PRESET_DESCRICAO_MAX)
    escopo: Literal["usuario", "inquilino"] = "usuario"
    conteudo: dict = Field(..., description="pesos e vetos por fator; ver app/amc/presets.py")


class PresetEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = Field(None, min_length=1, max_length=200)
    descricao: str | None = Field(None, max_length=limites.AMC_PRESET_DESCRICAO_MAX)
    escopo: Literal["usuario", "inquilino"] | None = None
    conteudo: dict | None = None


class Preset(Saida):
    id: str
    nome: str
    descricao: str
    escopo: str
    integrado: bool
    conteudo: dict
    dono_id: str | None = None
    dono_login: str | None = None
    criado_em: str | None = None
    atualizado_em: str | None = None


class PresetPagina(Saida):
    total: int
    itens: list[Preset]


class PresetAplicar(BaseModel):
    """Matriz de fatores (unidade × fator, escala 0-100, `null` = sem dado) na ordem de
    `ids_fatores`. Tudo que é escolha do modelo (peso, veto, combinador, política) vem do PRESET —
    a chamada só traz dado."""

    model_config = ConfigDict(extra="forbid")

    fatores: list[list]
    ids_fatores: list[str] = Field(..., min_length=1)


class PresetImportar(BaseModel):
    """Documento gerado por GET .../exportar. `fatores_modelo` é OPCIONAL: quando informado, preset
    que declara fator fora dessa lista é recusado com a lista do que falta (refutação do item)."""

    model_config = ConfigDict(extra="forbid")

    formato: str
    versao: int
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: str = Field("", max_length=limites.AMC_PRESET_DESCRICAO_MAX)
    escopo: Literal["usuario", "inquilino"] = "usuario"
    conteudo: dict
    # o documento exportado carrega "integrado"; na importação ele é ACEITO e ignorado — o importado
    # nasce sempre como preset comum do inquilino (a rota nunca persiste o campo)
    integrado: bool | None = None
    fatores_modelo: list[str] | None = None


class PresetImportado(Saida):
    id: str
    nome: str
    escopo: str
    integrado: bool = False
    faltando: list[str] = []


class AplicacaoFeita(Saida):
    preset_id: str
    preset_nome: str
    pesos_iguais: bool
    resultado: dict
