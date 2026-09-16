from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="AtivacaoEntrada")


@_attrs_define
class AtivacaoEntrada:
    """
    Attributes:
        ativa (bool):
    """

    ativa: bool

    def to_dict(self) -> dict[str, Any]:
        ativa = self.ativa

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "ativa": ativa,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ativa = d.pop("ativa")

        ativacao_entrada = cls(
            ativa=ativa,
        )

        return ativacao_entrada
