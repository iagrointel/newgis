from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ImportarCategorias")


@_attrs_define
class ImportarCategorias:
    """
    Attributes:
        modelo (str):
    """

    modelo: str

    def to_dict(self) -> dict[str, Any]:
        modelo = self.modelo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "modelo": modelo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        modelo = d.pop("modelo")

        importar_categorias = cls(
            modelo=modelo,
        )

        return importar_categorias
