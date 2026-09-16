from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="EstadoCriar")


@_attrs_define
class EstadoCriar:
    """
    Attributes:
        estado (str):
    """

    estado: str

    def to_dict(self) -> dict[str, Any]:
        estado = self.estado

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "estado": estado,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        estado = d.pop("estado")

        estado_criar = cls(
            estado=estado,
        )

        return estado_criar
