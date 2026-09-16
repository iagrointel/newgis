from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ModoTracadoEntrada")


@_attrs_define
class ModoTracadoEntrada:
    """
    Attributes:
        modo (str):
    """

    modo: str

    def to_dict(self) -> dict[str, Any]:
        modo = self.modo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "modo": modo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        modo = d.pop("modo")

        modo_tracado_entrada = cls(
            modo=modo,
        )

        return modo_tracado_entrada
