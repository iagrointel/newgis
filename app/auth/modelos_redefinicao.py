"""Modelos pydantic da redefinição de senha por e-mail (item L0-07-d-smtp-convites). Arquivo separado de
`app/auth/modelos.py` pelo mesmo motivo de `modelos_convite.py` (menos colisão de commit entre trilhas)."""

from pydantic import Field

from app.auth.modelos import Modelo, Saida


class RedefinicaoSolicitarEntrada(Modelo):
    inquilino: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=254)


class RedefinicaoSolicitarSaida(Saida):
    ok: bool


class RedefinicaoResolvida(Saida):
    motivo: str


class RedefinicaoAplicarEntrada(Modelo):
    token: str = Field(min_length=10, max_length=200)
    senha: str = Field(min_length=1, max_length=4096)


class RedefinicaoAplicada(Saida):
    ok: bool
