from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.categoria_no import CategoriaNo


T = TypeVar("T", bound="CategoriasEntrada")


@_attrs_define
class CategoriasEntrada:
    """
    Attributes:
        arvore (list[CategoriaNo]):
    """

    arvore: list[CategoriaNo]

    def to_dict(self) -> dict[str, Any]:
        arvore = []
        for arvore_item_data in self.arvore:
            arvore_item = arvore_item_data.to_dict()
            arvore.append(arvore_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "arvore": arvore,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.categoria_no import CategoriaNo  # noqa: PLC0415

        d = dict(src_dict)
        arvore = []
        _arvore = d.pop("arvore")
        for arvore_item_data in _arvore:
            arvore_item = CategoriaNo.from_dict(arvore_item_data)

            arvore.append(arvore_item)

        categorias_entrada = cls(
            arvore=arvore,
        )

        return categorias_entrada
