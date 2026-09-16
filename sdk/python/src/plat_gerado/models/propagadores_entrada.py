from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PropagadoresEntrada")


@_attrs_define
class PropagadoresEntrada:
    """Atributos que um tier propaga do controlador para os elementos da subrede (item L4-04-b). Lista vazia
    é legítima: significa "este tier não propaga nada".

        Attributes:
            propagadores (list[str] | Unset):
    """

    propagadores: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        propagadores: list[str] | Unset = UNSET
        if not isinstance(self.propagadores, Unset):
            propagadores = self.propagadores

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if propagadores is not UNSET:
            field_dict["propagadores"] = propagadores

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        propagadores = cast(list[str], d.pop("propagadores", UNSET))

        propagadores_entrada = cls(
            propagadores=propagadores,
        )

        propagadores_entrada.additional_properties = d
        return propagadores_entrada

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
