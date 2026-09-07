from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ConviteAceitarEntrada")


@_attrs_define
class ConviteAceitarEntrada:
    """
    Attributes:
        token (str):
        login (str):
        nome (str):
        senha (str):
    """

    token: str
    login: str
    nome: str
    senha: str

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        login = self.login

        nome = self.nome

        senha = self.senha

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "token": token,
                "login": login,
                "nome": nome,
                "senha": senha,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        login = d.pop("login")

        nome = d.pop("nome")

        senha = d.pop("senha")

        convite_aceitar_entrada = cls(
            token=token,
            login=login,
            nome=nome,
            senha=senha,
        )

        return convite_aceitar_entrada
