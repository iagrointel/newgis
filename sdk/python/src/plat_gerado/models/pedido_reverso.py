from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PedidoReverso")


@_attrs_define
class PedidoReverso:
    """
    Attributes:
        lon (float):
        lat (float):
        raio_m (float | Unset):  Default: 2000.0.
    """

    lon: float
    lat: float
    raio_m: float | Unset = 2000.0
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lon = self.lon

        lat = self.lat

        raio_m = self.raio_m

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "lon": lon,
                "lat": lat,
            }
        )
        if raio_m is not UNSET:
            field_dict["raio_m"] = raio_m

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        lon = d.pop("lon")

        lat = d.pop("lat")

        raio_m = d.pop("raio_m", UNSET)

        pedido_reverso = cls(
            lon=lon,
            lat=lat,
            raio_m=raio_m,
        )

        pedido_reverso.additional_properties = d
        return pedido_reverso

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
