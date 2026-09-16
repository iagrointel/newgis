from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.subtipo_valor import SubtipoValor


T = TypeVar("T", bound="SubtipoEntrada")


@_attrs_define
class SubtipoEntrada:
    """
    Attributes:
        campo (str):
        valores (list[SubtipoValor]):
    """

    campo: str
    valores: list[SubtipoValor]

    def to_dict(self) -> dict[str, Any]:
        campo = self.campo

        valores = []
        for valores_item_data in self.valores:
            valores_item = valores_item_data.to_dict()
            valores.append(valores_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "campo": campo,
                "valores": valores,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.subtipo_valor import SubtipoValor  # noqa: PLC0415

        d = dict(src_dict)
        campo = d.pop("campo")

        valores = []
        _valores = d.pop("valores")
        for valores_item_data in _valores:
            valores_item = SubtipoValor.from_dict(valores_item_data)

            valores.append(valores_item)

        subtipo_entrada = cls(
            campo=campo,
            valores=valores,
        )

        return subtipo_entrada
