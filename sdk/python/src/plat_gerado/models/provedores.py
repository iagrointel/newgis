from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.provedores_inquilino import ProvedoresInquilino
    from ..models.provedores_provedores_item import ProvedoresProvedoresItem


T = TypeVar("T", bound="Provedores")


@_attrs_define
class Provedores:
    """
    Attributes:
        inquilino (ProvedoresInquilino):
        provedores (list[ProvedoresProvedoresItem]):
        login_local (bool):
    """

    inquilino: ProvedoresInquilino
    provedores: list[ProvedoresProvedoresItem]
    login_local: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        inquilino = self.inquilino.to_dict()

        provedores = []
        for provedores_item_data in self.provedores:
            provedores_item = provedores_item_data.to_dict()
            provedores.append(provedores_item)

        login_local = self.login_local

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "inquilino": inquilino,
                "provedores": provedores,
                "login_local": login_local,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.provedores_inquilino import ProvedoresInquilino  # noqa: PLC0415
        from ..models.provedores_provedores_item import ProvedoresProvedoresItem  # noqa: PLC0415

        d = dict(src_dict)
        inquilino = ProvedoresInquilino.from_dict(d.pop("inquilino"))

        provedores = []
        _provedores = d.pop("provedores")
        for provedores_item_data in _provedores:
            provedores_item = ProvedoresProvedoresItem.from_dict(provedores_item_data)

            provedores.append(provedores_item)

        login_local = d.pop("login_local")

        provedores = cls(
            inquilino=inquilino,
            provedores=provedores,
            login_local=login_local,
        )

        provedores.additional_properties = d
        return provedores

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
