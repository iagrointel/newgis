from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SenhaSoEntrada")


@_attrs_define
class SenhaSoEntrada:
    """
    Attributes:
        senha (str):
    """

    senha: str

    def to_dict(self) -> dict[str, Any]:
        senha = self.senha

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "senha": senha,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        senha = d.pop("senha")

        senha_so_entrada = cls(
            senha=senha,
        )

        return senha_so_entrada
