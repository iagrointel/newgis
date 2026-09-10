from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="LoginEntrada")


@_attrs_define
class LoginEntrada:
    """
    Attributes:
        inquilino (str):
        login (str):
        senha (str):
    """

    inquilino: str
    login: str
    senha: str

    def to_dict(self) -> dict[str, Any]:
        inquilino = self.inquilino

        login = self.login

        senha = self.senha

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "inquilino": inquilino,
                "login": login,
                "senha": senha,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        inquilino = d.pop("inquilino")

        login = d.pop("login")

        senha = d.pop("senha")

        login_entrada = cls(
            inquilino=inquilino,
            login=login,
            senha=senha,
        )

        return login_entrada
