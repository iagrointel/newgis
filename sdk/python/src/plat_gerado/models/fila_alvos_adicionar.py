from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

T = TypeVar("T", bound="FilaAlvosAdicionar")


@_attrs_define
class FilaAlvosAdicionar:
    """
    Attributes:
        globalids (list[str]):
    """

    globalids: list[str]

    def to_dict(self) -> dict[str, Any]:
        globalids = self.globalids

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "globalids": globalids,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        globalids = cast(list[str], d.pop("globalids"))

        fila_alvos_adicionar = cls(
            globalids=globalids,
        )

        return fila_alvos_adicionar
