from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.subtipo_saida_valores_item import SubtipoSaidaValoresItem


T = TypeVar("T", bound="SubtipoSaida")


@_attrs_define
class SubtipoSaida:
    """
    Attributes:
        item_id (str):
        campo (str):
        valores (list[SubtipoSaidaValoresItem]):
    """

    item_id: str
    campo: str
    valores: list[SubtipoSaidaValoresItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item_id = self.item_id

        campo = self.campo

        valores = []
        for valores_item_data in self.valores:
            valores_item = valores_item_data.to_dict()
            valores.append(valores_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "item_id": item_id,
                "campo": campo,
                "valores": valores,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subtipo_saida_valores_item import SubtipoSaidaValoresItem  # noqa: PLC0415

        d = dict(src_dict)
        item_id = d.pop("item_id")

        campo = d.pop("campo")

        valores = []
        _valores = d.pop("valores")
        for valores_item_data in _valores:
            valores_item = SubtipoSaidaValoresItem.from_dict(valores_item_data)

            valores.append(valores_item)

        subtipo_saida = cls(
            item_id=item_id,
            campo=campo,
            valores=valores,
        )

        subtipo_saida.additional_properties = d
        return subtipo_saida

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
