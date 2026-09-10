"""Modelos pydantic da API de gestão de fonte de fluxo (item L2-14-a-ingestao-de-fluxos). `credencial` é
ENTRADA apenas — nenhum modelo de saída a carrega, cifrada ou não; `tem_credencial` diz só se existe."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites
from app.fluxo.tipos import TIPOS


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class FonteEntrada(Modelo):
    tipo: str = Field(pattern="^(" + "|".join(TIPOS) + ")$")
    nome: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    mapeamento: dict[str, Any] = Field(default_factory=dict)
    filtro: str | None = Field(default=None, max_length=20_000)
    limite_eventos_s: int = Field(default=1_000, ge=1, le=100_000)
    credencial: str | None = Field(default=None, max_length=4_096)


class FonteEditar(Modelo):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    estado: str | None = Field(default=None, pattern="^(ativa|pausada)$")
    config: dict[str, Any] | None = None
    mapeamento: dict[str, Any] | None = None
    filtro: str | None = Field(default=None, max_length=20_000)
    remover_filtro: bool = False
    limite_eventos_s: int | None = Field(default=None, ge=1, le=100_000)
    credencial: str | None = Field(default=None, max_length=4_096)
    remover_credencial: bool = False


class Dono(Saida):
    id: int
    login: str
    nome: str | None = None


class Metrica(Saida):
    recebidos: int = 0
    aceitos: int = 0
    descartados_filtro: int = 0
    descartados_limite: int = 0
    descartados_invalido: int = 0
    atraso_ms_ultimo: int | None = None
    atraso_ms_p50: int | None = None
    ultimo_evento_em: str | None = None
    atualizado_em: str | None = None


class Fonte(Saida):
    id: str
    tipo: str
    nome: str
    estado: str
    config: dict[str, Any]
    mapeamento: dict[str, Any]
    esquema_destino: list[dict[str, Any]]
    filtro: str | None = None
    limite_eventos_s: int
    tem_credencial: bool = False
    endereco_receptor: str | None = None
    dono: Dono
    metrica: Metrica
    criado_em: str | None = None
    atualizado_em: str | None = None


class FontePagina(Saida):
    total: int
    itens: list[Fonte]


class EventoSaida(Saida):
    rastro_id: str | None = None
    tempo_evento: str
    recebido_em: str
    lon: float | None = None
    lat: float | None = None
    atributos: dict[str, Any]


class EventoPagina(Saida):
    total: int
    itens: list[EventoSaida]
    limite: int = limites.FLUXO_EVENTOS_LISTA_MAX


class Expurgo(Saida):
    apagados: int


class Simulacao(Saida):
    """Resultado de POST /api/fluxos/{id}/simular: o que o mapeamento e o filtro fazem com um registro de
    exemplo, SEM gravar nada. É como se confere fuso e filtro antes de ligar a fonte."""

    aceito: bool
    motivo: str | None = None
    rastro_id: str | None = None
    tempo_evento: str | None = None
    lon: float | None = None
    lat: float | None = None
    atributos: dict[str, Any] = Field(default_factory=dict)
