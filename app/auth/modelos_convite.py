"""Modelos pydantic do convite de membro (item L0-07-d-smtp-convites). Arquivo separado de `app/auth/modelos.py`
de propósito (T3: `git commit` sempre por pathspec, e `modelos.py` é editado por outras trilhas no mesmo turno;
menos superfície de colisão)."""

from pydantic import Field

from app import limites
from app.auth.modelos import PERFIL, Modelo, Saida


class ConviteEntrada(Modelo):
    email: str = Field(min_length=3, max_length=254)
    nome_sugerido: str | None = Field(default=None, max_length=limites.CONVITE_NOME_MAX)
    perfil: str = PERFIL
    papel_id: int | None = None


class Convite(Saida):
    id: str
    email: str
    nome_sugerido: str | None = None
    perfil: str
    papel: dict | None = None
    criado_por: dict | None = None
    criado_em: str
    expira_em: str
    usado_em: str | None = None
    cancelado_em: str | None = None


class ConviteResolvido(Saida):
    motivo: str
    tenant_nome: str | None = None
    email: str | None = None
    perfil: str | None = None
    expira_em: str | None = None


class ConviteAceitarEntrada(Modelo):
    token: str = Field(min_length=10, max_length=200)
    login: str = Field(min_length=1, max_length=limites.CONVITE_LOGIN_MAX, pattern=r"^[a-z0-9][a-z0-9._@-]*$")
    nome: str = Field(min_length=1, max_length=200)
    senha: str = Field(min_length=1, max_length=4096)


class ConviteAceito(Saida):
    ok: bool
    tenant_slug: str
    login: str
