"""Modelos pydantic do módulo campo (item L2-07-campo). Entrada com extra=forbid (mesmo padrão de
app/edicao/modelos.py e app/rede_utilidades/modelos.py); saída com extra=allow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import limites

UUID_PADRAO = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


class FilaCriar(Modelo):
    titulo: str = Field(min_length=1, max_length=limites.ITEM_TITULO_MAX)
    camada_id: str = Field(pattern=UUID_PADRAO)
    # globalid das feições a acrescentar já na criação (opcional — uma fila pode nascer vazia e ganhar alvos
    # depois por POST /api/campo/filas/{id}/alvos)
    globalids: list[str] = Field(default_factory=list, max_length=limites.CAMPO_FILA_ALVOS_MAX)


class FilaAlvosAdicionar(Modelo):
    globalids: list[str] = Field(min_length=1, max_length=limites.CAMPO_FILA_ALVOS_MAX)


class FilaOrdem(Modelo):
    alvo_ids: list[str] = Field(min_length=1, max_length=limites.CAMPO_FILA_ALVOS_MAX)


class RoteiroOrigem(Modelo):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    rotulo: str | None = Field(default=None, max_length=200)


class RoteiroCriar(Modelo):
    fila_id: str = Field(pattern=UUID_PADRAO)
    origem: RoteiroOrigem
    titulo: str | None = Field(default=None, max_length=250)
    # sem alvo_ids: todos os alvos PENDENTES da fila (na ordem da fila), até o teto abaixo
    alvo_ids: list[str] = Field(default_factory=list, max_length=limites.CAMPO_ROTEIRO_PARADAS_MAX)
    maximo: int = Field(default=40, ge=1, le=limites.CAMPO_ROTEIRO_PARADAS_MAX)


class VisitaCriar(Modelo):
    # chave de idempotência gerada pelo dispositivo NO MOMENTO DA COLETA (crypto.randomUUID() no navegador);
    # reenviar o mesmo valor (retry de sincronização) nunca cria uma segunda visita — ver migração, UNIQUE
    # (tenant_id, cliente_uuid). Obrigatório: é o mecanismo inteiro da refutação "sincroniza duas vezes".
    cliente_uuid: str = Field(pattern=UUID_PADRAO)
    camada_id: str = Field(pattern=UUID_PADRAO)
    globalid: str = Field(pattern=UUID_PADRAO)
    alvo_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    fila_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    roteiro_id: str | None = Field(default=None, pattern=UUID_PADRAO)
    status: str = Field(pattern="^(visitado|confirmado|nao_confirmado|inconclusivo)$")
    texto: str | None = Field(default=None, max_length=8000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    gps_acc_m: float | None = Field(default=None, ge=0, le=100_000)
    # relógio do APARELHO no momento da coleta — nunca usado para ordenar nem para decidir duplicata no
    # servidor (refutação "muda relógio"): é só o que a tela mostra como "coletado em". `recebido_em` (relógio
    # do servidor) é gravado à parte e é a hora que manda.
    capturado_em: str = Field(min_length=1, max_length=40)
    dados: dict[str, Any] = Field(default_factory=dict)


class VisitaFotoEntrada(Modelo):
    """Imagem em base64 (mesmo contrato de app/catalogo/modelos.py::MiniaturaEntrada — o CSRF sob cookie
    exige application/json; a PWA de campo roda sob a MESMA sessão do navegador, nunca token)."""

    conteudo: str = Field(min_length=1, max_length=limites.CAMPO_FOTO_BYTES_MAX * 4 // 3 + 16)


class AlvoSaida(Saida):
    id: str
    globalid: str
    ordem: int
    nota: str | None = None
    status: str


class FilaSaida(Saida):
    id: str
    titulo: str
    camada_id: str
    status: str


__all__ = [
    "FilaCriar", "FilaAlvosAdicionar", "FilaOrdem", "RoteiroCriar", "RoteiroOrigem", "VisitaCriar",
    "VisitaFotoEntrada", "AlvoSaida", "FilaSaida",
]
