from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="FotoEntrada")


@_attrs_define
class FotoEntrada:
    """
    Attributes:
        conteudo (str):
    """

    conteudo: str

    def to_dict(self) -> dict[str, Any]:
        conteudo = self.conteudo

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "conteudo": conteudo,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        conteudo = d.pop("conteudo")

        foto_entrada = cls(
            conteudo=conteudo,
        )

        return foto_entrada
