from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ComentarioCriar")


@_attrs_define
class ComentarioCriar:
    """
    Attributes:
        texto (str):
    """

    texto: str

    def to_dict(self) -> dict[str, Any]:
        texto = self.texto

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "texto": texto,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        texto = d.pop("texto")

        comentario_criar = cls(
            texto=texto,
        )

        return comentario_criar
