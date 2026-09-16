from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="PreencherPendentesEntrada")


@_attrs_define
class PreencherPendentesEntrada:
    """
    Attributes:
        limite (int | Unset):  Default: 200.
    """

    limite: int | Unset = 200

    def to_dict(self) -> dict[str, Any]:
        limite = self.limite

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if limite is not UNSET:
            field_dict["limite"] = limite

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        limite = d.pop("limite", UNSET)

        preencher_pendentes_entrada = cls(
            limite=limite,
        )

        return preencher_pendentes_entrada
