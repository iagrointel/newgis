from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.ordem_exclusao_ordem_item import OrdemExclusaoOrdemItem


T = TypeVar("T", bound="OrdemExclusao")


@_attrs_define
class OrdemExclusao:
    """
    Attributes:
        ordem (list[OrdemExclusaoOrdemItem]):
        ocultos (int):
    """

    ordem: list[OrdemExclusaoOrdemItem]
    ocultos: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ordem = []
        for ordem_item_data in self.ordem:
            ordem_item = ordem_item_data.to_dict()
            ordem.append(ordem_item)

        ocultos = self.ocultos

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ordem": ordem,
                "ocultos": ocultos,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ordem_exclusao_ordem_item import OrdemExclusaoOrdemItem  # noqa: PLC0415

        d = dict(src_dict)
        ordem = []
        _ordem = d.pop("ordem")
        for ordem_item_data in _ordem:
            ordem_item = OrdemExclusaoOrdemItem.from_dict(ordem_item_data)

            ordem.append(ordem_item)

        ocultos = d.pop("ocultos")

        ordem_exclusao = cls(
            ordem=ordem,
            ocultos=ocultos,
        )

        ordem_exclusao.additional_properties = d
        return ordem_exclusao

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
