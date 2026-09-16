from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.backup_saida import BackupSaida


T = TypeVar("T", bound="BackupsPagina")


@_attrs_define
class BackupsPagina:
    """
    Attributes:
        itens (list[BackupSaida]):
        total (int):
    """

    itens: list[BackupSaida]
    total: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        total = self.total

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "itens": itens,
                "total": total,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.backup_saida import BackupSaida  # noqa: PLC0415

        d = dict(src_dict)
        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = BackupSaida.from_dict(itens_item_data)

            itens.append(itens_item)

        total = d.pop("total")

        backups_pagina = cls(
            itens=itens,
            total=total,
        )

        backups_pagina.additional_properties = d
        return backups_pagina

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
