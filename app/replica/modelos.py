"""Modelos pydantic das rotas de réplica (item L2-13-b). Entrada com extra=forbid, saída com extra=allow —
mesmo padrão de app/edicao/modelos.py."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites
from app.edicao.modelos import UUID_PADRAO, FeicaoAdicionar, FeicaoApagar, FeicaoAtualizar

POLITICAS = ("servidor_vence", "cliente_vence", "pergunta")
NOME_GPKG_PADRAO = r"^[a-z][a-z0-9_]{0,58}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class CamadaEntrada(Modelo):
    camada_id: str = Field(pattern=UUID_PADRAO)
    # nome da tabela dentro do GeoPackage; ausente = derivado do título do item (app/replica/servico.py)
    nome_gpkg: str | None = Field(default=None, pattern=NOME_GPKG_PADRAO)
    # subconjunto declarado, na MESMA linguagem `where` do FeatureServer (app/consulta/where_ast.py):
    # analisada em AST e compilada com parâmetro, nunca concatenada
    filtro: str | None = Field(default=None, max_length=limites.REPLICA_FILTRO_MAX)


class ReplicaEntrada(Modelo):
    nome: str = Field(min_length=1, max_length=limites.REPLICA_NOME_MAX)
    camadas: list[CamadaEntrada] = Field(min_length=1, max_length=limites.REPLICA_CAMADAS_MAX)
    dispositivo: str | None = Field(default=None, max_length=200)
    politica_conflito: str = Field(default="servidor_vence", pattern="^(servidor_vence|cliente_vence|pergunta)$")
    extensao: dict[str, Any] | None = None  # GeoJSON Polygon em EPSG:4326; ausente = camada inteira
    anexos: bool = False


class CamadaMudancas(Modelo):
    camada_id: str = Field(pattern=UUID_PADRAO)
    adicionar: list[FeicaoAdicionar] = Field(
        default_factory=list, max_length=limites.REPLICA_SINCRONIZAR_LOTE_MAX
    )
    atualizar: list[FeicaoAtualizar] = Field(
        default_factory=list, max_length=limites.REPLICA_SINCRONIZAR_LOTE_MAX
    )
    apagar: list[FeicaoApagar] = Field(default_factory=list, max_length=limites.REPLICA_SINCRONIZAR_LOTE_MAX)


class SincronizarEntrada(Modelo):
    # chave de idempotência do LOTE: o cliente a gera uma vez e repete a MESMA em toda retentativa do mesmo
    # lote. Sem ela não há defesa contra duplicar `adicionar` quando a rede cai depois de aplicar.
    idempotencia: str = Field(min_length=8, max_length=200)
    camadas: list[CamadaMudancas] = Field(default_factory=list, max_length=limites.REPLICA_CAMADAS_MAX)
    baixar: bool = True  # false = só sobe (útil quando o dispositivo está sem espaço)


class Conflito(Saida):
    camada_id: str
    id: str
    operacao: str
    versao_cliente: int | None = None
    versao_servidor: int | None = None
    resolucao: str  # servidor | cliente | pendente
    atual: dict[str, Any] | None = None


class MudancaServidor(Saida):
    operacao: str  # inserir | atualizar | apagar
    id: str
    fid: int | None = None
    versao: int | None = None
    atributos: dict[str, Any] | None = None
    geometria: dict[str, Any] | None = None


class CamadaBaixada(Saida):
    camada_id: str
    nome_gpkg: str
    desde: int
    ate: int
    truncado: bool = False
    mudancas: list[MudancaServidor] = Field(default_factory=list)


class SincronizarSaida(Saida):
    replica_id: str
    geracao: int
    repetida: bool = False
    subidas: dict[str, int] = Field(default_factory=dict)
    conflitos: list[Conflito] = Field(default_factory=list)
    baixadas: list[CamadaBaixada] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
