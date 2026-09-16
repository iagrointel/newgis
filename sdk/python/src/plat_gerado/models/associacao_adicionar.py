from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AssociacaoAdicionar")


@_attrs_define
class AssociacaoAdicionar:
    """
    Attributes:
        tipo (str):
        de (str):
        para (str):
    """

    tipo: str
    de: str
    para: str

    def to_dict(self) -> dict[str, Any]:
        tipo = self.tipo

        de = self.de

        para = self.para

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "tipo": tipo,
                "de": de,
                "para": para,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        tipo = d.pop("tipo")

        de = d.pop("de")

        para = d.pop("para")

        associacao_adicionar = cls(
            tipo=tipo,
            de=de,
            para=para,
        )

        return associacao_adicionar
