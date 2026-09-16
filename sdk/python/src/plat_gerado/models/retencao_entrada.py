from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="RetencaoEntrada")


@_attrs_define
class RetencaoEntrada:
    """
    Attributes:
        retencao_dias (int):
    """

    retencao_dias: int

    def to_dict(self) -> dict[str, Any]:
        retencao_dias = self.retencao_dias

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "retencao_dias": retencao_dias,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        retencao_dias = d.pop("retencao_dias")

        retencao_entrada = cls(
            retencao_dias=retencao_dias,
        )

        return retencao_entrada
