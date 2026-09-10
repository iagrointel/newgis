from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="RedefinicaoSolicitarEntrada")


@_attrs_define
class RedefinicaoSolicitarEntrada:
    """
    Attributes:
        inquilino (str):
        email (str):
    """

    inquilino: str
    email: str

    def to_dict(self) -> dict[str, Any]:
        inquilino = self.inquilino

        email = self.email

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "inquilino": inquilino,
                "email": email,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        inquilino = d.pop("inquilino")

        email = d.pop("email")

        redefinicao_solicitar_entrada = cls(
            inquilino=inquilino,
            email=email,
        )

        return redefinicao_solicitar_entrada
