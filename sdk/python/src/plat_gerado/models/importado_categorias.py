from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ImportadoCategorias")


@_attrs_define
class ImportadoCategorias:
    """
    Attributes:
        criadas (int):
        existentes (int):
    """

    criadas: int
    existentes: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        criadas = self.criadas

        existentes = self.existentes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "criadas": criadas,
                "existentes": existentes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        criadas = d.pop("criadas")

        existentes = d.pop("existentes")

        importado_categorias = cls(
            criadas=criadas,
            existentes=existentes,
        )

        importado_categorias.additional_properties = d
        return importado_categorias

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
