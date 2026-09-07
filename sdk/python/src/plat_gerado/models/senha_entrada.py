from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="SenhaEntrada")


@_attrs_define
class SenhaEntrada:
    """
    Attributes:
        atual (str):
        nova (str):
    """

    atual: str
    nova: str

    def to_dict(self) -> dict[str, Any]:
        atual = self.atual

        nova = self.nova

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "atual": atual,
                "nova": nova,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        atual = d.pop("atual")

        nova = d.pop("nova")

        senha_entrada = cls(
            atual=atual,
            nova=nova,
        )

        return senha_entrada
