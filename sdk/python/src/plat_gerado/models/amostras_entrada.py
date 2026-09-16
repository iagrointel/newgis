from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.amostra_entrada import AmostraEntrada


T = TypeVar("T", bound="AmostrasEntrada")


@_attrs_define
class AmostrasEntrada:
    """
    Attributes:
        amostras (list[AmostraEntrada]):
    """

    amostras: list[AmostraEntrada]

    def to_dict(self) -> dict[str, Any]:
        amostras = []
        for amostras_item_data in self.amostras:
            amostras_item = amostras_item_data.to_dict()
            amostras.append(amostras_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "amostras": amostras,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.amostra_entrada import AmostraEntrada  # noqa: PLC0415

        d = dict(src_dict)
        amostras = []
        _amostras = d.pop("amostras")
        for amostras_item_data in _amostras:
            amostras_item = AmostraEntrada.from_dict(amostras_item_data)

            amostras.append(amostras_item)

        amostras_entrada = cls(
            amostras=amostras,
        )

        return amostras_entrada
