from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.evento_saida import EventoSaida


T = TypeVar("T", bound="EventoPagina")


@_attrs_define
class EventoPagina:
    """
    Attributes:
        total (int):
        itens (list[EventoSaida]):
        limite (int | Unset):  Default: 1000.
    """

    total: int
    itens: list[EventoSaida]
    limite: int | Unset = 1000
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        total = self.total

        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        limite = self.limite

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "total": total,
                "itens": itens,
            }
        )
        if limite is not UNSET:
            field_dict["limite"] = limite

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.evento_saida import EventoSaida  # noqa: PLC0415

        d = dict(src_dict)
        total = d.pop("total")

        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = EventoSaida.from_dict(itens_item_data)

            itens.append(itens_item)

        limite = d.pop("limite", UNSET)

        evento_pagina = cls(
            total=total,
            itens=itens,
            limite=limite,
        )

        evento_pagina.additional_properties = d
        return evento_pagina

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
