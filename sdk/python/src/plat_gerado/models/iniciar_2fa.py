from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Iniciar2FA")


@_attrs_define
class Iniciar2FA:
    """
    Attributes:
        segredo (str):
        uri (str):
        qr_svg (str):
    """

    segredo: str
    uri: str
    qr_svg: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        segredo = self.segredo

        uri = self.uri

        qr_svg = self.qr_svg

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "segredo": segredo,
                "uri": uri,
                "qr_svg": qr_svg,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        segredo = d.pop("segredo")

        uri = d.pop("uri")

        qr_svg = d.pop("qr_svg")

        iniciar_2fa = cls(
            segredo=segredo,
            uri=uri,
            qr_svg=qr_svg,
        )

        iniciar_2fa.additional_properties = d
        return iniciar_2fa

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
