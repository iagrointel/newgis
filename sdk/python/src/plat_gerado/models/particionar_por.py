from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ParticionarPor")


@_attrs_define
class ParticionarPor:
    """
    Attributes:
        coluna (str):
        grao (str | Unset):  Default: 'valor'.
    """

    coluna: str
    grao: str | Unset = "valor"

    def to_dict(self) -> dict[str, Any]:
        coluna = self.coluna

        grao = self.grao

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "coluna": coluna,
            }
        )
        if grao is not UNSET:
            field_dict["grao"] = grao

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        coluna = d.pop("coluna")

        grao = d.pop("grao", UNSET)

        particionar_por = cls(
            coluna=coluna,
            grao=grao,
        )

        return particionar_por
