from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.compartilhado_item import CompartilhadoItem
    from ..models.compartilhado_itens_incluidos_item import CompartilhadoItensIncluidosItem


T = TypeVar("T", bound="Compartilhado")


@_attrs_define
class Compartilhado:
    """
    Attributes:
        item (CompartilhadoItem):
        itens_incluidos (list[CompartilhadoItensIncluidosItem]):
        permite_download (bool):
    """

    item: CompartilhadoItem
    itens_incluidos: list[CompartilhadoItensIncluidosItem]
    permite_download: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item = self.item.to_dict()

        itens_incluidos = []
        for itens_incluidos_item_data in self.itens_incluidos:
            itens_incluidos_item = itens_incluidos_item_data.to_dict()
            itens_incluidos.append(itens_incluidos_item)

        permite_download = self.permite_download

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item": item,
                "itens_incluidos": itens_incluidos,
                "permite_download": permite_download,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.compartilhado_item import CompartilhadoItem  # noqa: PLC0415
        from ..models.compartilhado_itens_incluidos_item import CompartilhadoItensIncluidosItem  # noqa: PLC0415

        d = dict(src_dict)
        item = CompartilhadoItem.from_dict(d.pop("item"))

        itens_incluidos = []
        _itens_incluidos = d.pop("itens_incluidos")
        for itens_incluidos_item_data in _itens_incluidos:
            itens_incluidos_item = CompartilhadoItensIncluidosItem.from_dict(itens_incluidos_item_data)

            itens_incluidos.append(itens_incluidos_item)

        permite_download = d.pop("permite_download")

        compartilhado = cls(
            item=item,
            itens_incluidos=itens_incluidos,
            permite_download=permite_download,
        )

        compartilhado.additional_properties = d
        return compartilhado

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
