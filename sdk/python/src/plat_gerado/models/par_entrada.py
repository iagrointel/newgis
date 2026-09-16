from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ParEntrada")


@_attrs_define
class ParEntrada:
    """
    Attributes:
        origem_valor (str):
        destino_valor (str):
    """

    origem_valor: str
    destino_valor: str

    def to_dict(self) -> dict[str, Any]:
        origem_valor = self.origem_valor

        destino_valor = self.destino_valor

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "origem_valor": origem_valor,
                "destino_valor": destino_valor,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        origem_valor = d.pop("origem_valor")

        destino_valor = d.pop("destino_valor")

        par_entrada = cls(
            origem_valor=origem_valor,
            destino_valor=destino_valor,
        )

        return par_entrada
