from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.agenda import Agenda


T = TypeVar("T", bound="ListaAgendas")


@_attrs_define
class ListaAgendas:
    """
    Attributes:
        itens (list[Agenda]):
        total (int):
    """

    itens: list[Agenda]
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
        from ..models.agenda import Agenda  # noqa: PLC0415

        d = dict(src_dict)
        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = Agenda.from_dict(itens_item_data)

            itens.append(itens_item)

        total = d.pop("total")

        lista_agendas = cls(
            itens=itens,
            total=total,
        )

        lista_agendas.additional_properties = d
        return lista_agendas

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
