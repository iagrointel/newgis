from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="PapelMembroEntrada")


@_attrs_define
class PapelMembroEntrada:
    """
    Attributes:
        papel (str):
    """

    papel: str

    def to_dict(self) -> dict[str, Any]:
        papel = self.papel

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "papel": papel,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        papel = d.pop("papel")

        papel_membro_entrada = cls(
            papel=papel,
        )

        return papel_membro_entrada
