from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AmostrasResultado")


@_attrs_define
class AmostrasResultado:
    """
    Attributes:
        fator_id (str):
        gravadas (int):
    """

    fator_id: str
    gravadas: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fator_id = self.fator_id

        gravadas = self.gravadas

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fator_id": fator_id,
                "gravadas": gravadas,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fator_id = d.pop("fator_id")

        gravadas = d.pop("gravadas")

        amostras_resultado = cls(
            fator_id=fator_id,
            gravadas=gravadas,
        )

        amostras_resultado.additional_properties = d
        return amostras_resultado

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
