from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.leitura_entrada import LeituraEntrada


T = TypeVar("T", bound="LeiturasLote")


@_attrs_define
class LeiturasLote:
    """
    Attributes:
        leituras (list[LeituraEntrada]):
    """

    leituras: list[LeituraEntrada]

    def to_dict(self) -> dict[str, Any]:
        leituras = []
        for leituras_item_data in self.leituras:
            leituras_item = leituras_item_data.to_dict()
            leituras.append(leituras_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "leituras": leituras,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.leitura_entrada import LeituraEntrada  # noqa: PLC0415

        d = dict(src_dict)
        leituras = []
        _leituras = d.pop("leituras")
        for leituras_item_data in _leituras:
            leituras_item = LeituraEntrada.from_dict(leituras_item_data)

            leituras.append(leituras_item)

        leituras_lote = cls(
            leituras=leituras,
        )

        return leituras_lote
