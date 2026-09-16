from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoGerar")


@_attrs_define
class PedidoGerar:
    """
    Attributes:
        raio_rede_m (float | Unset):  Default: 700.0.
        raio_bt_m (float | Unset):  Default: 135.0.
    """

    raio_rede_m: float | Unset = 700.0
    raio_bt_m: float | Unset = 135.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raio_rede_m = self.raio_rede_m

        raio_bt_m = self.raio_bt_m

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if raio_rede_m is not UNSET:
            field_dict["raio_rede_m"] = raio_rede_m
        if raio_bt_m is not UNSET:
            field_dict["raio_bt_m"] = raio_bt_m

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        raio_rede_m = d.pop("raio_rede_m", UNSET)

        raio_bt_m = d.pop("raio_bt_m", UNSET)

        pedido_gerar = cls(
            raio_rede_m=raio_rede_m,
            raio_bt_m=raio_bt_m,
        )

        pedido_gerar.additional_properties = d
        return pedido_gerar

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
