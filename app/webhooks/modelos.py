"""Modelos de entrada/saída das rotas de webhook (item L7-08-a). O segredo SÓ aparece na saída de
criação e de rotação (`WebhookSegredo`), uma única vez — nunca na listagem nem no detalhe."""

from pydantic import BaseModel, ConfigDict, Field

from app import limites


class WebhookEntrada(BaseModel):
    nome: str = Field(min_length=3, max_length=limites.WEBHOOK_NOME_MAX)
    url: str = Field(min_length=8, max_length=limites.WEBHOOK_URL_MAX)
    eventos: list[str] = Field(min_length=1, max_length=limites.WEBHOOK_EVENTOS_MAX)


class WebhookEditar(BaseModel):
    nome: str | None = Field(default=None, min_length=3, max_length=limites.WEBHOOK_NOME_MAX)
    url: str | None = Field(default=None, min_length=8, max_length=limites.WEBHOOK_URL_MAX)
    eventos: list[str] | None = Field(default=None, min_length=1, max_length=limites.WEBHOOK_EVENTOS_MAX)


class Webhook(BaseModel):
    """Saída de listagem/detalhe: NUNCA traz segredo (nem cifrado, em nenhum caminho)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    url: str
    eventos: list[str]
    ativo: bool
    falhas_consecutivas: int
    desativada_em: str | None = None
    desativada_motivo: str | None = None
    criado_em: str
    criado_por: str | None = None
    criado_por_login: str | None = None


class WebhookSegredo(Webhook):
    """Criar/rotacionar: o campo extra `segredo` viaja UMA vez; quem perder, rotaciona."""

    segredo: str


class WebhookPagina(BaseModel):
    total: int
    itens: list[Webhook]


class Entrega(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    webhook_id: str
    evento_id: int
    tipo_evento: str
    payload: dict
    estado: str
    tentativas: int
    reenvios: int
    ultima_status: int | None = None
    ultima_erro: str | None = None
    criado_em: str
    entregue_em: str | None = None


class EntregaPagina(BaseModel):
    total: int
    itens: list[Entrega]
