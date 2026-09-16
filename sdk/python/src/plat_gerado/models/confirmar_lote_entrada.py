from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.confirmar_lote_item import ConfirmarLoteItem


T = TypeVar("T", bound="ConfirmarLoteEntrada")


@_attrs_define
class ConfirmarLoteEntrada:
    """
    Attributes:
        itens (list[ConfirmarLoteItem]):
    """

    itens: list[ConfirmarLoteItem]

    def to_dict(self) -> dict[str, Any]:
        itens = []
        for itens_item_data in self.itens:
            itens_item = itens_item_data.to_dict()
            itens.append(itens_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "itens": itens,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.confirmar_lote_item import ConfirmarLoteItem  # noqa: PLC0415

        d = dict(src_dict)
        itens = []
        _itens = d.pop("itens")
        for itens_item_data in _itens:
            itens_item = ConfirmarLoteItem.from_dict(itens_item_data)

            itens.append(itens_item)

        confirmar_lote_entrada = cls(
            itens=itens,
        )

        return confirmar_lote_entrada
