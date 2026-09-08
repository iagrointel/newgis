"""Modelos pydantic da configuração de SMTP por inquilino (item L0-07-d-smtp-convites)."""

from pydantic import Field

from app import limites
from app.auth.modelos import Modelo, Saida


class SMTPEntrada(Modelo):
    """PUT /api/org/smtp. `senha` ausente preserva a cifra atual; `senha=""` (string vazia) apaga a senha
    guardada sem apagar o resto; `host=""` some com o override do inquilino inteiro (volta a usar a
    instalação, se houver, ou o caminho manual)."""

    host: str = Field(default="", max_length=limites.SMTP_HOST_MAX)
    porta: int = Field(default=587, ge=limites.SMTP_PORTA_MIN, le=limites.SMTP_PORTA_MAX)
    tls: bool = True
    usuario: str = Field(default="", max_length=limites.SMTP_USUARIO_MAX)
    senha: str | None = Field(default=None, max_length=limites.SMTP_SENHA_MAX)
    remetente: str = Field(default="", max_length=limites.SMTP_REMETENTE_MAX)
    rotulo: str = Field(default="", max_length=limites.SMTP_ROTULO_MAX)


class SMTPSaida(Saida):
    configurado: bool
    origem: str  # 'inquilino' | 'instalacao' | 'nenhum'
    host: str | None = None
    porta: int | None = None
    tls: bool | None = None
    usuario: str | None = None
    remetente: str | None = None
    rotulo: str | None = None
    senha_configurada: bool = False


class SMTPTestarEntrada(Modelo):
    destinatario: str | None = Field(default=None, max_length=320)


class SMTPTestarSaida(Saida):
    ok: bool
    destinatario: str
