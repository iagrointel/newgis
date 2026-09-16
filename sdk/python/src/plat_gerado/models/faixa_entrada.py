from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FaixaEntrada")


@_attrs_define
class FaixaEntrada:
    """
    Attributes:
        tipo_id (str):
        quantidade (int):
    """

    tipo_id: str
    quantidade: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tipo_id = self.tipo_id

        quantidade = self.quantidade

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tipo_id": tipo_id,
                "quantidade": quantidade,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo_id = d.pop("tipo_id")

        quantidade = d.pop("quantidade")

        faixa_entrada = cls(
            tipo_id=tipo_id,
            quantidade=quantidade,
        )

        faixa_entrada.additional_properties = d
        return faixa_entrada

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
