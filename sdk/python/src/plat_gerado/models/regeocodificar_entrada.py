from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RegeocodificarEntrada")


@_attrs_define
class RegeocodificarEntrada:
    """
    Attributes:
        limiar_pendente (float | None | Unset):
    """

    limiar_pendente: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        limiar_pendente: float | None | Unset
        if isinstance(self.limiar_pendente, Unset):
            limiar_pendente = UNSET
        else:
            limiar_pendente = self.limiar_pendente

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if limiar_pendente is not UNSET:
            field_dict["limiar_pendente"] = limiar_pendente

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_limiar_pendente(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        limiar_pendente = _parse_limiar_pendente(d.pop("limiar_pendente", UNSET))

        regeocodificar_entrada = cls(
            limiar_pendente=limiar_pendente,
        )

        regeocodificar_entrada.additional_properties = d
        return regeocodificar_entrada

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
