from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="FatorPesoEntrada")


@_attrs_define
class FatorPesoEntrada:
    """
    Attributes:
        fator_id (str):
        peso (float):
    """

    fator_id: str
    peso: float

    def to_dict(self) -> dict[str, Any]:
        fator_id = self.fator_id

        peso = self.peso

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "fator_id": fator_id,
                "peso": peso,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fator_id = d.pop("fator_id")

        peso = d.pop("peso")

        fator_peso_entrada = cls(
            fator_id=fator_id,
            peso=peso,
        )

        return fator_peso_entrada
