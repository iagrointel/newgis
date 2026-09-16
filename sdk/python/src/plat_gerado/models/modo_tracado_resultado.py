from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ModoTracadoResultado")


@_attrs_define
class ModoTracadoResultado:
    """
    Attributes:
        rede_id (str):
        modo (str):
    """

    rede_id: str
    modo: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rede_id = self.rede_id

        modo = self.modo

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rede_id": rede_id,
                "modo": modo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rede_id = d.pop("rede_id")

        modo = d.pop("modo")

        modo_tracado_resultado = cls(
            rede_id=rede_id,
            modo=modo,
        )

        modo_tracado_resultado.additional_properties = d
        return modo_tracado_resultado

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
