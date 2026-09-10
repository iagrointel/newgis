from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="CodigoEntrada")


@_attrs_define
class CodigoEntrada:
    """
    Attributes:
        codigo (str):
    """

    codigo: str

    def to_dict(self) -> dict[str, Any]:
        codigo = self.codigo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "codigo": codigo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        codigo = d.pop("codigo")

        codigo_entrada = cls(
            codigo=codigo,
        )

        return codigo_entrada
